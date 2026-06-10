"""Emercoin Agent Gateway — unified HTTP API.

The single authorization boundary in front of an (internal, unauthenticated)
Emercoin node. Lets AI agents use the chain as an identity + data layer via NVS.
Phase 1: node plumbing only (`/info`). Auth + NVS routes land next.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request

from .config import settings
from .rpc import EmercoinRPC, RPCError


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.rpc = EmercoinRPC(settings.rpc_url, settings.rpc_user, settings.rpc_password)
    yield
    await app.state.rpc.aclose()


app = FastAPI(title="Emercoin Agent Gateway", version="0.0.1", lifespan=lifespan)


def get_rpc(request: Request) -> EmercoinRPC:
    return request.app.state.rpc


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@app.get("/info")
async def info(rpc: EmercoinRPC = Depends(get_rpc)) -> dict:
    """Node status passthrough — read-only sanity check of the RPC plumbing."""
    try:
        return await rpc.call("getinfo")
    except RPCError as e:
        raise HTTPException(status_code=502, detail=f"node rpc error: {e.message}")
