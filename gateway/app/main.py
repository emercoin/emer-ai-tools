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
from .config import settings
from .ratelimit import RateLimiter
from .rpc import EmercoinRPC, RPCError


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.rpc = EmercoinRPC(settings.rpc_url, settings.rpc_user, settings.rpc_password)
    app.state.ratelimiter = RateLimiter(settings.redis_url)
    yield
    await app.state.rpc.aclose()
    await app.state.ratelimiter.aclose()


app = FastAPI(title="Emercoin Agent Gateway", version="0.0.1", lifespan=lifespan)


def get_rpc(request: Request) -> EmercoinRPC:
    return request.app.state.rpc


def get_ratelimiter(request: Request) -> RateLimiter:
    return request.app.state.ratelimiter


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
    pubkey: str = Field(..., description="Agent public key bound to this GitHub identity")
    metadata: dict = {}


class MemRequest(BaseModel):
    content_hash: str = Field(..., description="Hash of the research/memory artifact (body stored off-chain)")
    metadata: dict = {}


class WriteResponse(BaseModel):
    name: str
    result: object


# --- health / status -------------------------------------------------------

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
    github_id, github_login = await resolve_github_token(req.github_token)
    token = issue_jwt(github_id, github_login)
    return TokenResponse(
        access_token=token, github_id=github_id, github_login=github_login, tariff="free"
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
        "pubkey": req.pubkey,
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


@app.get("/nvs/{name:path}")
async def read_nvs(name: str, rpc: EmercoinRPC = Depends(get_rpc)) -> dict:
    try:
        return await nvs.show_record(rpc, name)
    except RPCError as exc:
        raise HTTPException(status_code=404, detail=f"name not found: {exc.message}")
