"""Emercoin Agent Gateway — edge (agent-facing IAM).

The single authorization boundary for AI agents: GitHub-rooted login, session
JWTs, challenge-response agent login, and per-tier rate limiting. It owns no node
access of its own — every chain operation is delegated over HTTP to the node
adapter. Agents use the chain as an identity + memory layer through this API.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import names
from .auth import Principal, current_principal, issue_jwt, resolve_github_token
from .challenge import ChallengeStore
from .client import AdapterClient, AdapterError
from .config import settings
from .ratelimit import RateLimiter


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.adapter = AdapterClient(settings.adapter_url, settings.adapter_key)
    app.state.ratelimiter = RateLimiter(settings.redis_url)
    app.state.challenges = ChallengeStore(settings.redis_url)
    yield
    await app.state.adapter.aclose()
    await app.state.ratelimiter.aclose()
    await app.state.challenges.aclose()


app = FastAPI(title="Emercoin Agent Gateway (edge)", version="0.0.1", lifespan=lifespan)


@app.exception_handler(AdapterError)
async def _adapter_error(request: Request, exc: AdapterError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


def get_adapter(request: Request) -> AdapterClient:
    return request.app.state.adapter


def get_ratelimiter(request: Request) -> RateLimiter:
    return request.app.state.ratelimiter


def get_challenges(request: Request) -> ChallengeStore:
    return request.app.state.challenges


# --- schemas ---------------------------------------------------------------

class LoginRequest(BaseModel):
    github_token: str = Field(..., description="A GitHub token; resolved to a user via the API")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    github_id: int
    github_login: str
    tariff: str


class IdentityRequest(BaseModel):
    address: str = Field(..., description="Agent's Emercoin address; the anchor for signature login")
    metadata: dict = {}


class ChallengeRequest(BaseModel):
    github_id: int


class ChallengeResponse(BaseModel):
    github_id: int
    nonce: str = Field(..., description="Sign this exact string with the agent's address key")


class AgentLoginRequest(BaseModel):
    github_id: int
    address: str
    signature: str = Field(..., description="signmessage(address, nonce) from the challenge")


class MemRequest(BaseModel):
    content_hash: str = Field(..., description="Hash of the research/memory artifact (body stored off-chain)")
    metadata: dict = {}


class MemBatchRequest(BaseModel):
    records: list[MemRequest] = Field(..., min_length=1, max_length=100)


class BatchWriteResponse(BaseModel):
    txid: object
    count: int
    names: list[str]


class WriteResponse(BaseModel):
    name: str
    result: object


# --- health / status -------------------------------------------------------

@app.get("/")
async def root(
    adapter: AdapterClient = Depends(get_adapter), rl: RateLimiter = Depends(get_ratelimiter)
) -> dict:
    """Aggregated machine-readable state for agents: node + wallet (via adapter)
    and edge infra (redis). Never 500s — each component is probed independently."""
    redis_state: dict = {"ok": False}
    try:
        await rl.ping()
        redis_state["ok"] = True
    except Exception as exc:
        redis_state["error"] = str(exc) or exc.__class__.__name__

    adapter_state: dict = {"ok": False}
    node: dict = {"ok": False}
    wallet: dict = {"ok": False}
    try:
        state = await adapter.state()
        adapter_state["ok"] = True
        node = state.get("node", node)
        wallet = state.get("wallet", wallet)
    except Exception as exc:
        adapter_state["error"] = str(exc) or exc.__class__.__name__

    if not adapter_state["ok"] or not node.get("ok"):
        status = "down"
    elif not redis_state["ok"]:
        status = "degraded"
    elif node.get("synced"):
        status = "ok"
    else:
        status = "syncing"

    return {
        "service": "emercoin-agent-gateway",
        "description": "Emercoin gateway — on-chain identity & memory layer for AI agents",
        "version": app.version,
        "status": status,
        "node": node,
        "wallet": wallet,
        "adapter": adapter_state,
        "redis": redis_state,
        "docs": "/docs",
    }


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@app.get("/info")
async def info(adapter: AdapterClient = Depends(get_adapter)) -> dict:
    return await adapter.info()


@app.get("/status")
async def status(adapter: AdapterClient = Depends(get_adapter)) -> dict:
    """Node sync status — while syncing, `synced` is false and progress < 1."""
    return await adapter.status()


# --- auth ------------------------------------------------------------------

@app.post("/auth/login", response_model=TokenResponse)
async def login(req: LoginRequest) -> TokenResponse:
    """Bootstrap login via GitHub identity (human / first-time registration)."""
    github_id, github_login = await resolve_github_token(req.github_token)
    token = issue_jwt(github_id, github_login)
    return TokenResponse(
        access_token=token, github_id=github_id, github_login=github_login, tariff="free"
    )


@app.post("/auth/challenge", response_model=ChallengeResponse)
async def auth_challenge(
    req: ChallengeRequest, challenges: ChallengeStore = Depends(get_challenges)
) -> ChallengeResponse:
    nonce = await challenges.issue(str(req.github_id))
    return ChallengeResponse(github_id=req.github_id, nonce=nonce)


@app.post("/auth/agent-login", response_model=TokenResponse)
async def agent_login(
    req: AgentLoginRequest,
    adapter: AdapterClient = Depends(get_adapter),
    challenges: ChallengeStore = Depends(get_challenges),
) -> TokenResponse:
    """Machine-speed login: agent signs the challenge nonce with its address key.

    Signature is verified by the node (`verifymessage` via the adapter); the
    address must match the one bound to this GitHub identity on-chain.
    """
    nonce = await challenges.consume(str(req.github_id))
    if not nonce:
        raise HTTPException(status_code=401, detail="no active challenge; request /auth/challenge")
    if not await adapter.verify(req.address, req.signature, nonce):
        raise HTTPException(status_code=401, detail="bad signature")

    record = await adapter.get_identity(names.root_name(req.github_id))
    identity = names.parse_identity(record) if record else {}
    if not identity:
        raise HTTPException(status_code=404, detail="no on-chain identity; register via /nvs/identity")
    if identity.get("address") != req.address:
        raise HTTPException(status_code=403, detail="address not bound to this GitHub identity")

    github_login = identity.get("github_login", str(req.github_id))
    token = issue_jwt(req.github_id, github_login)
    return TokenResponse(
        access_token=token, github_id=req.github_id, github_login=github_login, tariff="free"
    )


@app.get("/me", response_model=Principal)
async def me(principal: Principal = Depends(current_principal)) -> Principal:
    return principal


# --- NVS -------------------------------------------------------------------

@app.post("/nvs/identity", response_model=WriteResponse)
async def create_identity(
    req: IdentityRequest,
    principal: Principal = Depends(current_principal),
    adapter: AdapterClient = Depends(get_adapter),
    rl: RateLimiter = Depends(get_ratelimiter),
) -> WriteResponse:
    await rl.check_and_incr(principal.github_id, settings.free_tier_writes_per_min)
    name = names.root_name(principal.github_id)
    value = {
        "github_id": principal.github_id,
        "github_login": principal.github_login,
        "address": req.address,
        "metadata": req.metadata,
    }
    res = await adapter.write(name, value, settings.nvs_default_days)
    return WriteResponse(name=res["name"], result=res["result"])


@app.post("/nvs/mem", response_model=WriteResponse)
async def create_mem(
    req: MemRequest,
    principal: Principal = Depends(current_principal),
    adapter: AdapterClient = Depends(get_adapter),
    rl: RateLimiter = Depends(get_ratelimiter),
) -> WriteResponse:
    await rl.check_and_incr(principal.github_id, settings.free_tier_writes_per_min)
    name = names.mem_name(principal.github_id, req.content_hash)
    value = {
        "github_id": principal.github_id,
        "content_hash": req.content_hash,
        "metadata": req.metadata,
    }
    res = await adapter.write(name, value, settings.nvs_default_days)
    return WriteResponse(name=res["name"], result=res["result"])


@app.post("/nvs/mem/batch", response_model=BatchWriteResponse)
async def create_mem_batch(
    req: MemBatchRequest,
    principal: Principal = Depends(current_principal),
    adapter: AdapterClient = Depends(get_adapter),
    rl: RateLimiter = Depends(get_ratelimiter),
) -> BatchWriteResponse:
    """Atomically store many memory records in one transaction (name_updatemany)."""
    await rl.check_and_incr(principal.github_id, settings.free_tier_writes_per_min, len(req.records))
    ops = [
        {
            "name": names.mem_name(principal.github_id, r.content_hash),
            "value": {
                "github_id": principal.github_id,
                "content_hash": r.content_hash,
                "metadata": r.metadata,
            },
            "days": settings.nvs_default_days,
        }
        for r in req.records
    ]
    res = await adapter.write_batch(ops)
    return BatchWriteResponse(txid=res["txid"], count=res["count"], names=res["names"])


@app.get("/history/{name:path}")
async def name_history(name: str, adapter: AdapterClient = Depends(get_adapter)) -> dict:
    """Value history of an NVS name (name_history)."""
    return await adapter.history(name)


@app.get("/addresses/{address}/names")
async def address_names(address: str, adapter: AdapterClient = Depends(get_adapter)) -> dict:
    """All names owned by an address (name_scan_address) — basis for record export."""
    return await adapter.address_names(address)


@app.get("/nvs/{name:path}")
async def read_nvs(name: str, adapter: AdapterClient = Depends(get_adapter)) -> dict:
    """Read an NVS record (confirmed from the name DB, or `pending` from mempool)."""
    return await adapter.read(name)
