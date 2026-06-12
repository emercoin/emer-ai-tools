"""Remote MCP server (Streamable HTTP), mounted into the edge.

Exposes the edge's chain operations as MCP tools so an MCP client (Claude, etc.)
can use the Emercoin chain as an identity + memory layer without a local install.
Stateless HTTP with JSON responses.

Auth: OAuth 2.1 (DCR + authorization-code + PKCE + refresh) via `oauth_provider`,
delegating user login to GitHub. All tools require a valid token; the issued access
token is our session JWT, so a token pasted from /login works as a Bearer too. The
authenticated caller is read from the SDK auth context; the User-Agent (for stats)
comes from the request Context. Shared clients are injected via `configure()`.
"""
from __future__ import annotations

import logging

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl

from . import names
from .auth import Principal
from .client import AdapterClient
from .config import settings
from .github import GitHubOAuth
from .oauth_provider import MCP_SCOPE, GitHubOAuthProvider
from .ratelimit import RateLimiter
from .stats import Stats

log = logging.getLogger("edge.mcp")

_adapter: AdapterClient | None = None
_ratelimiter: RateLimiter | None = None
_stats: Stats | None = None

oauth_provider = GitHubOAuthProvider()


def configure(adapter: AdapterClient, ratelimiter: RateLimiter, stats: Stats, github: GitHubOAuth) -> None:
    """Inject the edge's shared clients so tools/provider reuse them (in lifespan)."""
    global _adapter, _ratelimiter, _stats
    _adapter, _ratelimiter, _stats = adapter, ratelimiter, stats
    oauth_provider.configure(github)


def _principal() -> Principal:
    """The authenticated caller, from the SDK's validated access token."""
    at = get_access_token()
    if at is None:  # the auth middleware should have rejected — defensive
        raise ValueError("authentication required")
    claims = at.claims or {}
    return Principal(int(at.subject), claims.get("login", ""), claims.get("tariff", "free"))


async def _record(ctx: Context, tool: str, principal: Principal) -> None:
    ua = ""
    try:
        ua = ctx.request_context.request.headers.get("user-agent", "")
    except Exception:  # noqa: BLE001
        pass
    if _stats is not None:
        await _stats.record_call(tool, principal.github_id, ua)


mcp = FastMCP(
    "emercoin-agent",
    instructions=(
        "Use the Emercoin blockchain as an identity + memory layer for AI agents. "
        "Sign in with GitHub (your MCP client handles the OAuth flow). Then register "
        "your identity and store verifiable hashes of your work as NVS records."
    ),
    stateless_http=True,
    json_response=True,
    streamable_http_path="/mcp",
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    auth_server_provider=oauth_provider,
    auth=AuthSettings(
        issuer_url=AnyHttpUrl(settings.public_url),
        client_registration_options=ClientRegistrationOptions(
            enabled=True, valid_scopes=[MCP_SCOPE], default_scopes=[MCP_SCOPE]
        ),
        required_scopes=[MCP_SCOPE],
        resource_server_url=None,
    ),
)


@mcp.tool()
async def node_status(ctx: Context) -> dict:
    """Emercoin node version, block height and sync status."""
    await _record(ctx, "node_status", _principal())
    return await _adapter.status()


@mcp.tool()
async def read_record(ctx: Context, name: str) -> dict:
    """Read an NVS record by its full name (e.g. ai:gh:<id>:mem:<hash>)."""
    await _record(ctx, "read_record", _principal())
    return await _adapter.read(name)


@mcp.tool()
async def whoami(ctx: Context) -> dict:
    """Return your authenticated GitHub identity."""
    p = _principal()
    await _record(ctx, "whoami", p)
    return {"github_id": p.github_id, "github_login": p.github_login, "tariff": p.tariff}


@mcp.tool()
async def register_identity(ctx: Context, address: str, metadata: dict | None = None) -> dict:
    """Register/rotate your on-chain identity record ai:gh:<github_id>."""
    p = _principal()
    await _record(ctx, "register_identity", p)
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
    """Store a memory record ai:gh:<github_id>:mem:<content_hash> on-chain."""
    p = _principal()
    await _record(ctx, "store_memory", p)
    await _ratelimiter.check_and_incr(p.github_id, settings.free_tier_writes_per_min)
    name = names.mem_name(p.github_id, content_hash)
    value = {"github_id": p.github_id, "content_hash": content_hash, "metadata": metadata or {}}
    res = await _adapter.write(name, value, settings.nvs_default_days)
    return {"name": res["name"], "txid": res["result"]}
