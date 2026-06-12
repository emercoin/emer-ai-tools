"""Remote MCP server (Streamable HTTP), mounted into the edge at /mcp.

Exposes the same chain operations as the edge HTTP API as MCP tools, so an MCP
client (Claude, etc.) can use the Emercoin chain as an identity + memory layer
without a local install. Stateless HTTP with JSON responses.

Auth (v1): a session JWT in the `Authorization: Bearer <token>` header (get one at
https://ai.emercoin.com/login). Read tools are open; write tools require it. The
token is read per-call from the request via the MCP `Context`. The same
AdapterClient / RateLimiter as the edge are injected via `configure()` in lifespan.
"""
from __future__ import annotations

import logging

from mcp.server.fastmcp import Context, FastMCP

from . import names
from .auth import Principal, decode_token
from .client import AdapterClient
from .config import settings
from .ratelimit import RateLimiter

log = logging.getLogger("edge.mcp")

_adapter: AdapterClient | None = None
_ratelimiter: RateLimiter | None = None


def configure(adapter: AdapterClient, ratelimiter: RateLimiter) -> None:
    """Inject the edge's shared clients so tools reuse them (called in lifespan)."""
    global _adapter, _ratelimiter
    _adapter, _ratelimiter = adapter, ratelimiter


def _principal(ctx: Context) -> Principal:
    """Resolve the caller from the request's Authorization header, or raise."""
    auth = ""
    try:
        auth = ctx.request_context.request.headers.get("authorization", "")
    except Exception:  # noqa: BLE001 — no request bound (shouldn't happen over HTTP)
        auth = ""
    token = auth[7:].strip() if auth[:7].lower() == "bearer " else ""
    principal = decode_token(token) if token else None
    if principal is None:
        raise ValueError(
            "authentication required: set 'Authorization: Bearer <token>' "
            "(get a session token at https://ai.emercoin.com/login)"
        )
    return principal


mcp = FastMCP(
    "emercoin-agent",
    instructions=(
        "Use the Emercoin blockchain as an identity + memory layer for AI agents. "
        "Read tools are open; write tools need a session JWT in the Authorization "
        "header — get one at https://ai.emercoin.com/login."
    ),
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
)


@mcp.tool()
async def node_status() -> dict:
    """Emercoin node version, block height and sync status. No auth."""
    return await _adapter.status()


@mcp.tool()
async def read_record(name: str) -> dict:
    """Read an NVS record by its full name (e.g. ai:gh:<id>:mem:<hash>). No auth."""
    return await _adapter.read(name)


@mcp.tool()
async def whoami(ctx: Context) -> dict:
    """Return the authenticated GitHub identity. Requires the Authorization header."""
    p = _principal(ctx)
    return {"github_id": p.github_id, "github_login": p.github_login, "tariff": p.tariff}


@mcp.tool()
async def register_identity(ctx: Context, address: str, metadata: dict | None = None) -> dict:
    """Register/rotate your on-chain identity record ai:gh:<github_id>. Requires auth."""
    p = _principal(ctx)
    await _ratelimiter.check_and_incr(p.github_id, settings.free_tier_writes_per_min)
    name = names.root_name(p.github_id)
    value = {
        "github_id": p.github_id,
        "github_login": p.github_login,
        "address": address,
        "metadata": metadata or {},
    }
    res = await _adapter.write(name, value, settings.nvs_default_days)
    log.info("mcp store register_identity gh=%s", p.github_id)
    return {"name": res["name"], "txid": res["result"]}


@mcp.tool()
async def store_memory(ctx: Context, content_hash: str, metadata: dict | None = None) -> dict:
    """Store a memory record ai:gh:<github_id>:mem:<content_hash> on-chain. Requires auth."""
    p = _principal(ctx)
    await _ratelimiter.check_and_incr(p.github_id, settings.free_tier_writes_per_min)
    name = names.mem_name(p.github_id, content_hash)
    value = {"github_id": p.github_id, "content_hash": content_hash, "metadata": metadata or {}}
    res = await _adapter.write(name, value, settings.nvs_default_days)
    log.info("mcp store store_memory gh=%s", p.github_id)
    return {"name": res["name"], "txid": res["result"]}
