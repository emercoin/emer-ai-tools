"""Remote MCP server (Streamable HTTP), mounted into the edge at /mcp.

Exposes the same chain operations as the edge HTTP API as MCP tools, so an MCP
client (Claude, etc.) can use the Emercoin chain as an identity + memory layer
without a local install. Stateless HTTP with JSON responses.

Auth (v1): a session JWT in the `Authorization: Bearer <token>` header (get one at
https://ai.emercoin.com/login). Read tools are open; write tools require it. The
token is read per-call from the request via the MCP `Context`. The same
AdapterClient / RateLimiter / Stats as the edge are injected via `configure()`.
"""
from __future__ import annotations

import logging

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from . import names
from .auth import Principal, decode_token
from .client import AdapterClient
from .config import settings
from .ratelimit import RateLimiter
from .stats import Stats

log = logging.getLogger("edge.mcp")

_adapter: AdapterClient | None = None
_ratelimiter: RateLimiter | None = None
_stats: Stats | None = None


def configure(adapter: AdapterClient, ratelimiter: RateLimiter, stats: Stats) -> None:
    """Inject the edge's shared clients so tools reuse them (called in lifespan)."""
    global _adapter, _ratelimiter, _stats
    _adapter, _ratelimiter, _stats = adapter, ratelimiter, stats


def _request_info(ctx: Context) -> tuple[Principal | None, str]:
    """Best-effort (principal, user_agent) from the request behind this tool call."""
    principal, ua = None, ""
    try:
        headers = ctx.request_context.request.headers
        ua = headers.get("user-agent", "")
        auth = headers.get("authorization", "")
        if auth[:7].lower() == "bearer ":
            principal = decode_token(auth[7:].strip())
    except Exception:  # noqa: BLE001 — no request bound (shouldn't happen over HTTP)
        pass
    return principal, ua


async def _record(ctx: Context, tool: str) -> Principal | None:
    """Log a usage event and return the caller principal (if any)."""
    principal, ua = _request_info(ctx)
    if _stats is not None:
        await _stats.record_call(tool, principal.github_id if principal else None, ua)
    return principal


def _require(principal: Principal | None) -> Principal:
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
    # Edge sits behind trusted Caddy + Cloudflare (origin firewalled to CF), so the
    # incoming Host is ai.emercoin.com — disable the SDK's DNS-rebinding Host check
    # (meant for localhost browser scenarios) which would otherwise 421.
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


@mcp.tool()
async def node_status(ctx: Context) -> dict:
    """Emercoin node version, block height and sync status. No auth."""
    await _record(ctx, "node_status")
    return await _adapter.status()


@mcp.tool()
async def read_record(ctx: Context, name: str) -> dict:
    """Read an NVS record by its full name (e.g. ai:gh:<id>:mem:<hash>). No auth."""
    await _record(ctx, "read_record")
    return await _adapter.read(name)


@mcp.tool()
async def whoami(ctx: Context) -> dict:
    """Return the authenticated GitHub identity. Requires the Authorization header."""
    p = _require(await _record(ctx, "whoami"))
    return {"github_id": p.github_id, "github_login": p.github_login, "tariff": p.tariff}


@mcp.tool()
async def register_identity(ctx: Context, address: str, metadata: dict | None = None) -> dict:
    """Register/rotate your on-chain identity record ai:gh:<github_id>. Requires auth."""
    p = _require(await _record(ctx, "register_identity"))
    await _ratelimiter.check_and_incr(p.github_id, settings.free_tier_writes_per_min)
    name = names.root_name(p.github_id)
    value = {
        "github_id": p.github_id,
        "github_login": p.github_login,
        "address": address,
        "metadata": metadata or {},
    }
    res = await _adapter.write(name, value, settings.nvs_default_days)
    return {"name": res["name"], "txid": res["result"]}


@mcp.tool()
async def store_memory(ctx: Context, content_hash: str, metadata: dict | None = None) -> dict:
    """Store a memory record ai:gh:<github_id>:mem:<content_hash> on-chain. Requires auth."""
    p = _require(await _record(ctx, "store_memory"))
    await _ratelimiter.check_and_incr(p.github_id, settings.free_tier_writes_per_min)
    name = names.mem_name(p.github_id, content_hash)
    value = {"github_id": p.github_id, "content_hash": content_hash, "metadata": metadata or {}}
    res = await _adapter.write(name, value, settings.nvs_default_days)
    return {"name": res["name"], "txid": res["result"]}
