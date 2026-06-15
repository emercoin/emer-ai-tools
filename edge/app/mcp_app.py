"""Remote MCP server (Streamable HTTP), mounted into the edge.

Exposes the edge's chain operations as MCP tools so an MCP client (Claude, etc.)
can use the Emercoin chain as an identity + memory layer without a local install.
Stateless HTTP with JSON responses.

Auth: OAuth 2.1 (DCR + authorization-code + PKCE + refresh) via `oauth_provider`,
delegating user login to GitHub. All tools require a valid token; the issued access
token is our session JWT, so a token pasted from /login works as a Bearer too. The
authenticated caller is read from the SDK auth context; the User-Agent (for stats)
comes from the request Context. Tools carry parameter descriptions, output schemas
and behaviour annotations. Shared clients are injected via `configure()`.
"""
from __future__ import annotations

import logging
from typing import Annotated, TypedDict

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.middleware.bearer_auth import RequireAuthMiddleware
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import AnyHttpUrl, Field
from starlette.applications import Starlette
from starlette.routing import Route

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
    oauth_provider.configure(github, settings.redis_url)


def _principal_optional() -> Principal | None:
    """The authenticated caller if a valid token was presented, else None.

    Read/discovery tools are open (no transport-level auth gate — see
    `streamable_app`); they tolerate None. Write tools require auth and call
    `_principal()` instead."""
    at = get_access_token()
    if at is None:
        return None
    claims = at.claims or {}
    return Principal(int(at.subject), claims.get("login", ""), claims.get("tariff", "free"))


def _principal() -> Principal:
    """The authenticated caller; raises if no valid token. Write tools require this."""
    p = _principal_optional()
    if p is None:
        raise ValueError(
            "authentication required: sign in with GitHub via OAuth to use write tools "
            "(read tools are open). Your MCP client handles the OAuth flow."
        )
    return p


async def _record(ctx: Context, tool: str, principal: Principal | None) -> None:
    ua = ""
    try:
        ua = ctx.request_context.request.headers.get("user-agent", "")
    except Exception:  # noqa: BLE001
        pass
    if _stats is not None:
        await _stats.record_call(tool, principal.github_id if principal else None, ua)


# --- output schemas (drive each tool's outputSchema) -----------------------

class NodeStatus(TypedDict, total=False):
    """Node sync status. Fields are nullable — the MCP SDK fills any absent field
    with null when serialising structured output, so the schema must allow it."""
    version: str | None
    blocks: int | None
    headers: int | None
    verificationprogress: float | None
    connections: int | None
    synced: bool | None


class NvsRecord(TypedDict, total=False):
    """An NVS record (confirmed from the name DB, or pending from the mempool).
    Fields are nullable: a pending record omits several, and the SDK serialises
    absent fields as null."""
    status: str | None
    name: str | None
    value: str | None
    txid: str | None
    time: int | None
    address: str | None
    address_is_mine: str | None
    operation: str | None
    days_added: int | None
    pending_update: bool | None
    pending: dict | None


class Identity(TypedDict):
    """A resolved GitHub-rooted agent identity."""
    github_id: int
    github_login: str
    tariff: str


class WriteResult(TypedDict):
    """The on-chain write: the NVS name written and its transaction id."""
    name: str
    txid: str


mcp = FastMCP(
    "emercoin-agent",
    instructions=(
        "Use the Emercoin blockchain as an identity + memory layer for AI agents. "
        "Read tools (node_status, read_record) are open to everyone — no sign-in. "
        "Write tools (register_identity, store_memory) and whoami require a GitHub "
        "sign-in via OAuth, which your MCP client performs; on the FREE tier writes "
        "are rate-limited per minute. Then register your identity and store "
        "verifiable hashes of your work as NVS records."
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
        # Advertise this server as its own resource (RFC 9728) so modern clients
        # discover the AS via /.well-known/oauth-protected-resource + the 401's
        # resource_metadata pointer. issuer == resource (combined AS+RS).
        resource_server_url=AnyHttpUrl(settings.public_url),
    ),
)

@mcp.tool(
    title="Node status",
    annotations=ToolAnnotations(
        title="Node status", readOnlyHint=True, idempotentHint=True, openWorldHint=True
    ),
    structured_output=True,
)
async def node_status(ctx: Context) -> NodeStatus:
    """Emercoin node version, block height and chain sync status. No sign-in required."""
    await _record(ctx, "node_status", _principal_optional())
    return await _adapter.status()  # type: ignore[return-value]


@mcp.tool(
    title="Read NVS record",
    annotations=ToolAnnotations(
        title="Read NVS record", readOnlyHint=True, idempotentHint=True, openWorldHint=True
    ),
    structured_output=True,
)
async def read_record(
    ctx: Context,
    name: Annotated[
        str,
        Field(description="Full NVS record name, e.g. 'ai:gh:<github_id>:mem:<sha256-hex>'."),
    ],
) -> NvsRecord:
    """Read an Emercoin NVS record by its full name. Returns the confirmed record,
    or a `pending` record if the write is still in the mempool. No sign-in required."""
    await _record(ctx, "read_record", _principal_optional())
    return await _adapter.read(name)  # type: ignore[return-value]


@mcp.tool(
    title="Who am I",
    annotations=ToolAnnotations(
        title="Who am I", readOnlyHint=True, idempotentHint=True, openWorldHint=False
    ),
    structured_output=True,
)
async def whoami(ctx: Context) -> Identity:
    """Return your authenticated GitHub-rooted identity (id, login, tariff)."""
    p = _principal()
    await _record(ctx, "whoami", p)
    return {"github_id": p.github_id, "github_login": p.github_login, "tariff": p.tariff}


@mcp.tool(
    title="Register identity",
    annotations=ToolAnnotations(
        title="Register identity",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
    structured_output=True,
)
async def register_identity(
    ctx: Context,
    address: Annotated[
        str,
        Field(description="Your Emercoin address to bind to your GitHub identity (the anchor for signature login)."),
    ],
    metadata: Annotated[
        dict | None,
        Field(default=None, description="Optional free-form JSON metadata to store with the identity record."),
    ] = None,
) -> WriteResult:
    """Register or rotate your on-chain identity record `ai:gh:<github_id>`, binding
    an Emercoin address to your GitHub identity. Returns the name and transaction id."""
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


@mcp.tool(
    title="Store memory",
    annotations=ToolAnnotations(
        title="Store memory",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
    structured_output=True,
)
async def store_memory(
    ctx: Context,
    content_hash: Annotated[
        str,
        Field(description="Content hash (e.g. SHA-256 hex) of the artifact/memory; the body itself is stored off-chain."),
    ],
    metadata: Annotated[
        dict | None,
        Field(default=None, description="Optional free-form JSON metadata (note, source, tags, …)."),
    ] = None,
) -> WriteResult:
    """Store a memory record `ai:gh:<github_id>:mem:<content_hash>` on-chain — a
    verifiable fingerprint of an artifact. Returns the name and transaction id."""
    p = _principal()
    await _record(ctx, "store_memory", p)
    await _ratelimiter.check_and_incr(p.github_id, settings.free_tier_writes_per_min)
    name = names.mem_name(p.github_id, content_hash)
    value = {"github_id": p.github_id, "content_hash": content_hash, "metadata": metadata or {}}
    res = await _adapter.write(name, value, settings.nvs_default_days)
    return {"name": res["name"], "txid": res["result"]}


def streamable_app() -> Starlette:
    """The MCP streamable-HTTP app with the transport-level auth gate removed.

    By default the SDK wraps the `/mcp` route in `RequireAuthMiddleware`, which 401s
    every unauthenticated request — including the `initialize`/`tools/list` handshake.
    That blocks open discovery and read access (and makes registry health-checks like
    Glama's headless prober report the connector as Unhealthy, since they can't
    complete an interactive OAuth flow).

    We unwrap that one middleware so anonymous callers reach the transport. The
    app-level `AuthenticationMiddleware` + `AuthContextMiddleware` stay, so a Bearer
    token is still validated and exposed via `get_access_token()` when present — which
    is how the write tools enforce auth per-call through `_principal()`. OAuth routes
    and protected-resource metadata are untouched."""
    app = mcp.streamable_http_app()
    for route in app.routes:
        if (
            isinstance(route, Route)
            and route.path == mcp.settings.streamable_http_path
            and isinstance(route.app, RequireAuthMiddleware)
        ):
            route.app = route.app.app  # drop the 401-for-anonymous gate
    return app
