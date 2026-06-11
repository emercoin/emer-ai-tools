"""Emercoin node adapter — RPC↔REST.

Translates the node's JSON-RPC into a plain HTTP REST surface so other services
never have to speak RPC. It does NO user authorization: it trusts its callers
(the internal docker network, or the edge service). The only gate is an optional
shared `X-Internal-Key` for when the adapter is reachable beyond a trusted
network. Browse the surface at `/docs`.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from . import nvs
from .config import settings
from .rpc import EmercoinRPC, RPCError


def require_internal_key(
    request: Request, x_internal_key: str | None = Header(default=None)
) -> None:
    """Shared-secret gate. No-op when `internal_key` is unset (dev). `/healthz`
    stays open for liveness probes."""
    if not settings.internal_key or request.url.path == "/healthz":
        return
    if x_internal_key != settings.internal_key:
        raise HTTPException(status_code=401, detail="missing or invalid X-Internal-Key")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.rpc = EmercoinRPC(settings.rpc_url, settings.rpc_user, settings.rpc_password)
    yield
    await app.state.rpc.aclose()


app = FastAPI(
    title="Emercoin Node Adapter",
    version="0.0.1",
    lifespan=lifespan,
    dependencies=[Depends(require_internal_key)],
)


def get_rpc(request: Request) -> EmercoinRPC:
    return request.app.state.rpc


# --- schemas ---------------------------------------------------------------

class WriteRequest(BaseModel):
    name: str
    value: object = Field(..., description="dict (JSON-encoded for you) or a raw string")
    days: int | None = Field(default=None, description="lifetime; defaults to node policy")


class WriteOp(BaseModel):
    name: str
    value: object
    days: int | None = None


class BatchWriteRequest(BaseModel):
    operations: list[WriteOp] = Field(..., min_length=1, max_length=100)


class VerifyRequest(BaseModel):
    address: str
    signature: str
    message: str


# --- health / status -------------------------------------------------------

@app.get("/")
async def root(rpc: EmercoinRPC = Depends(get_rpc)) -> dict:
    """Aggregated node + wallet state. Never 500s — probed independently."""
    node: dict = {"ok": False}
    wallet: dict = {"ok": False}
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

        wallet["ok"] = True
        wallet["encrypted"] = info.get("encrypted")
        wallet["balance"] = info.get("balance")
        try:
            winfo = await rpc.call("getwalletinfo")
            wallet["unconfirmed"] = winfo.get("unconfirmed_balance")
            if not info.get("encrypted"):
                wallet["locked"] = None
            else:
                wallet["locked"] = winfo.get("unlocked_until", 0) == 0
        except Exception:
            wallet["locked"] = None
    except Exception as exc:
        node["error"] = str(exc) or exc.__class__.__name__

    status = "ok" if node.get("synced") else ("syncing" if node["ok"] else "down")
    return {
        "service": "emercoin-node-adapter",
        "version": app.version,
        "status": status,
        "node": node,
        "wallet": wallet,
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


# --- NVS (generic) ---------------------------------------------------------

@app.post("/nvs")
async def write(req: WriteRequest, rpc: EmercoinRPC = Depends(get_rpc)) -> dict:
    """Create or update one NVS name (name_new / name_update chosen for you)."""
    days = req.days if req.days is not None else settings.nvs_default_days
    try:
        result = await nvs.write_record(rpc, req.name, req.value, days)
    except RPCError as exc:
        raise HTTPException(status_code=502, detail=f"nvs write failed: {exc.message}")
    return {"name": req.name, "result": result}


@app.post("/nvs/batch")
async def write_batch(req: BatchWriteRequest, rpc: EmercoinRPC = Depends(get_rpc)) -> dict:
    """Atomically store many NVS records in one transaction (name_updatemany)."""
    ops = [
        {
            "name": op.name,
            "value": op.value,
            "days": op.days if op.days is not None else settings.nvs_default_days,
        }
        for op in req.operations
    ]
    try:
        txid = await nvs.write_batch(rpc, ops)
    except RPCError as exc:
        raise HTTPException(status_code=502, detail=f"batch write failed: {exc.message}")
    return {"txid": txid, "count": len(ops), "names": [op["name"] for op in ops]}


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

    Requires the node's name-address index (`nameaddress=1` in emercoin.conf);
    reported as 501 when it isn't enabled.
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
async def read(name: str, rpc: EmercoinRPC = Depends(get_rpc)) -> dict:
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


# --- crypto / wallet -------------------------------------------------------

@app.post("/verify")
async def verify(req: VerifyRequest, rpc: EmercoinRPC = Depends(get_rpc)) -> dict:
    """Verify a signed message (verifymessage) — pure crypto, works while syncing."""
    try:
        valid = await rpc.call("verifymessage", req.address, req.signature, req.message)
    except RPCError as exc:
        raise HTTPException(status_code=502, detail=f"verify failed: {exc.message}")
    return {"valid": bool(valid)}


@app.get("/wallet/address")
async def wallet_address(label: str = "gateway", rpc: EmercoinRPC = Depends(get_rpc)) -> dict:
    """Fresh receive address for funding the hot-wallet with EMC."""
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
