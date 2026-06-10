"""Emercoin Agent Gateway — unified HTTP API.

The single authorization boundary in front of an (internal, unauthenticated)
Emercoin node. Lets AI agents use the chain as an identity + data layer via NVS.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from . import nvs
from .auth import Principal, current_principal, issue_jwt, resolve_github_token
from .challenge import ChallengeStore
from .config import settings
from .ratelimit import RateLimiter
from .rpc import EmercoinRPC, RPCError


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.rpc = EmercoinRPC(settings.rpc_url, settings.rpc_user, settings.rpc_password)
    app.state.ratelimiter = RateLimiter(settings.redis_url)
    app.state.challenges = ChallengeStore(settings.redis_url)
    yield
    await app.state.rpc.aclose()
    await app.state.ratelimiter.aclose()
    await app.state.challenges.aclose()


app = FastAPI(title="Emercoin Agent Gateway", version="0.0.1", lifespan=lifespan)


def get_rpc(request: Request) -> EmercoinRPC:
    return request.app.state.rpc


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
    rpc: EmercoinRPC = Depends(get_rpc), rl: RateLimiter = Depends(get_ratelimiter)
) -> dict:
    """Aggregated machine-readable state for agents: node, wallet, infra, sync.

    Never 500s — each component is probed independently and reported as ok/down.
    """
    node: dict = {"ok": False}
    wallet: dict = {"ok": False}
    redis_state: dict = {"ok": False}

    try:
        info = await rpc.call("getinfo")
        node["ok"] = True
        node["version"] = info.get("fullversion")
        node["connections"] = info.get("connections")
        try:
            chain = await rpc.call("getblockchaininfo")
            progress = chain.get("verificationprogress")
            node["blocks"] = chain.get("blocks")
            node["headers"] = chain.get("headers")
            node["verificationprogress"] = progress
            node["synced"] = bool(progress is not None and progress > 0.9999)
        except Exception:
            node["blocks"] = info.get("blocks")
            node["synced"] = None

        # Wallet lives inside the node; if getinfo worked, the wallet is loaded.
        wallet["ok"] = True
        wallet["encrypted"] = info.get("encrypted")
        wallet["balance"] = info.get("balance")
        try:
            winfo = await rpc.call("getwalletinfo")
            wallet["unconfirmed"] = winfo.get("unconfirmed_balance")
            if not info.get("encrypted"):
                wallet["locked"] = None  # not applicable to an unencrypted wallet
            else:
                wallet["locked"] = winfo.get("unlocked_until", 0) == 0
        except Exception:
            wallet["locked"] = None
    except Exception as exc:
        node["error"] = str(exc) or exc.__class__.__name__

    try:
        await rl.ping()
        redis_state["ok"] = True
    except Exception as exc:
        redis_state["error"] = str(exc) or exc.__class__.__name__

    if not node["ok"]:
        status = "down"
    elif not redis_state["ok"]:
        status = "degraded"
    elif node.get("synced"):
        status = "ok"
    else:
        status = "syncing"

    return {
        "service": "emercoin-agent-gateway",
        "description": "Emercoin wallet gateway — on-chain identity & memory layer for AI agents",
        "version": app.version,
        "status": status,
        "node": node,
        "wallet": wallet,
        "redis": redis_state,
        "docs": "/docs",
    }


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@app.get("/info")
async def info(rpc: EmercoinRPC = Depends(get_rpc)) -> dict:
    try:
        return await rpc.call("getinfo")
    except RPCError as exc:
        raise HTTPException(status_code=502, detail=f"node rpc error: {exc.message}")


@app.get("/status")
async def status(rpc: EmercoinRPC = Depends(get_rpc)) -> dict:
    """Node sync status — while syncing, `synced` is false and progress < 1."""
    try:
        info_res = await rpc.call("getinfo")
        chain = await rpc.call("getblockchaininfo")
    except RPCError as exc:
        raise HTTPException(status_code=502, detail=f"node rpc error: {exc.message}")
    progress = chain.get("verificationprogress")
    return {
        "version": info_res.get("fullversion"),
        "blocks": chain.get("blocks"),
        "headers": chain.get("headers"),
        "verificationprogress": progress,
        "connections": info_res.get("connections"),
        "synced": bool(progress is not None and progress > 0.9999),
    }


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
    rpc: EmercoinRPC = Depends(get_rpc),
    challenges: ChallengeStore = Depends(get_challenges),
) -> TokenResponse:
    """Machine-speed login: agent signs the challenge nonce with its address key.

    Signature is verified by the node (`verifymessage`); the address must match
    the one bound to this GitHub identity in its on-chain identity record.
    """
    nonce = await challenges.consume(str(req.github_id))
    if not nonce:
        raise HTTPException(status_code=401, detail="no active challenge; request /auth/challenge")
    try:
        valid = await rpc.call("verifymessage", req.address, req.signature, nonce)
    except RPCError as exc:
        raise HTTPException(status_code=502, detail=f"verify failed: {exc.message}")
    if not valid:
        raise HTTPException(status_code=401, detail="bad signature")

    identity = await nvs.get_identity(rpc, req.github_id)
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

async def _write(
    name: str,
    value: dict,
    principal: Principal,
    rpc: EmercoinRPC,
    rl: RateLimiter,
) -> WriteResponse:
    await rl.check_and_incr(principal.github_id, settings.free_tier_writes_per_min)
    try:
        result = await nvs.write_record(rpc, name, value, settings.nvs_default_days)
    except RPCError as exc:
        raise HTTPException(status_code=502, detail=f"nvs write failed: {exc.message}")
    return WriteResponse(name=name, result=result)


@app.post("/nvs/identity", response_model=WriteResponse)
async def create_identity(
    req: IdentityRequest,
    principal: Principal = Depends(current_principal),
    rpc: EmercoinRPC = Depends(get_rpc),
    rl: RateLimiter = Depends(get_ratelimiter),
) -> WriteResponse:
    name = nvs.root_name(principal.github_id)
    value = {
        "github_id": principal.github_id,
        "github_login": principal.github_login,
        "address": req.address,
        "metadata": req.metadata,
    }
    return await _write(name, value, principal, rpc, rl)


@app.post("/nvs/mem", response_model=WriteResponse)
async def create_mem(
    req: MemRequest,
    principal: Principal = Depends(current_principal),
    rpc: EmercoinRPC = Depends(get_rpc),
    rl: RateLimiter = Depends(get_ratelimiter),
) -> WriteResponse:
    name = nvs.mem_name(principal.github_id, req.content_hash)
    value = {
        "github_id": principal.github_id,
        "content_hash": req.content_hash,
        "metadata": req.metadata,
    }
    return await _write(name, value, principal, rpc, rl)


@app.post("/nvs/mem/batch", response_model=BatchWriteResponse)
async def create_mem_batch(
    req: MemBatchRequest,
    principal: Principal = Depends(current_principal),
    rpc: EmercoinRPC = Depends(get_rpc),
    rl: RateLimiter = Depends(get_ratelimiter),
) -> BatchWriteResponse:
    """Atomically store many memory records in one transaction (name_updatemany)."""
    await rl.check_and_incr(principal.github_id, settings.free_tier_writes_per_min, len(req.records))
    ops = [
        nvs.mem_operation(principal.github_id, r.content_hash, r.metadata, settings.nvs_default_days)
        for r in req.records
    ]
    try:
        txid = await nvs.write_batch(rpc, ops)
    except RPCError as exc:
        raise HTTPException(status_code=502, detail=f"batch write failed: {exc.message}")
    return BatchWriteResponse(txid=txid, count=len(ops), names=[op["NEW"] for op in ops])


@app.get("/history/{name:path}")
async def name_history(name: str, rpc: EmercoinRPC = Depends(get_rpc)) -> dict:
    """Value history of an NVS name (name_history)."""
    try:
        return {"name": name, "history": await nvs.show_history(rpc, name)}
    except RPCError as exc:
        raise HTTPException(status_code=404, detail=f"name not found: {exc.message}")


@app.get("/addresses/{address}/names")
async def address_names(address: str, rpc: EmercoinRPC = Depends(get_rpc)) -> dict:
    """All names owned by an address (name_scan_address) — basis for record export.

    Requires the node's name-address index (`nameaddress=1` in emercoin.conf,
    then a reindex); reported as 501 when it isn't enabled.
    """
    try:
        return {"address": address, "names": await nvs.names_for_address(rpc, address)}
    except RPCError as exc:
        if exc.code == -20 or "index is not available" in exc.message:
            raise HTTPException(
                status_code=501,
                detail=f"name-address index disabled on the node: {exc.message}",
            )
        raise HTTPException(status_code=502, detail=f"node rpc error: {exc.message}")


@app.get("/nvs/{name:path}")
async def read_nvs(name: str, rpc: EmercoinRPC = Depends(get_rpc)) -> dict:
    """Read an NVS record. Confirmed names come from the name DB; a name that was
    just written but not yet mined is reported as `pending` from the mempool."""
    try:
        record = await nvs.show_record(rpc, name)
        record["status"] = "confirmed"
        return record
    except RPCError:
        pending = await nvs.find_in_mempool(rpc, name)
        if pending is not None:
            return {"status": "pending", **pending}
        raise HTTPException(status_code=404, detail=f"name not found: {name}")


# --- wallet (dev/admin) ----------------------------------------------------
# The gateway hot-wallet pays for every NVS record, so agents need no coins.
# These are unauthenticated dev endpoints for funding it; gate behind admin auth
# before any public deployment.

@app.get("/wallet/address")
async def wallet_address(
    label: str = "gateway", rpc: EmercoinRPC = Depends(get_rpc)
) -> dict:
    """Fresh receive address for funding the gateway hot-wallet with EMC."""
    try:
        address = await rpc.call("getnewaddress", label)
    except RPCError as exc:
        raise HTTPException(status_code=502, detail=f"node rpc error: {exc.message}")
    return {"address": address, "label": label}


@app.get("/wallet/balance")
async def wallet_balance(rpc: EmercoinRPC = Depends(get_rpc)) -> dict:
    """Hot-wallet balance — confirm funds arrived before testing NVS writes."""
    try:
        return {
            "balance": await rpc.call("getbalance"),
            "unconfirmed": await rpc.call("getunconfirmedbalance"),
        }
    except RPCError as exc:
        raise HTTPException(status_code=502, detail=f"node rpc error: {exc.message}")
