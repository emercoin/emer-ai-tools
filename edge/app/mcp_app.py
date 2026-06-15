"""Remote MCP server (Streamable HTTP), mounted into the edge.

Exposes the edge's chain operations as MCP tools so an MCP client (Claude, etc.)
can use the Emercoin chain as an identity + memory layer without a local install.
Stateless HTTP with JSON responses.

Auth: OAuth 2.1 (DCR + authorization-code + PKCE + refresh) via `oauth_provider`,
delegating user login to GitHub. Discovery and read tools (`node_status`,
`read_record`, `whoami`) are open; write tools require a valid token. The issued
access token is our session JWT, so a token pasted from /login works as a Bearer
too. The authenticated caller is read from the SDK auth context; the User-Agent
(for stats) comes from the request Context. Tools carry parameter descriptions,
output schemas and behaviour annotations. Shared clients via `configure()`.
"""
from __future__ import annotations

import json
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


# Actionable, machine-readable payload returned (as the tool error text) when a
# write tool is called without a session. JSON so an agent can parse the reason and
# the remedy rather than scrape prose; `isError` stays true so it is never mistaken
# for a successful write.
_AUTH_REQUIRED = {
    "error": "authentication_required",
    "message": "This tool writes to the Emercoin chain under your identity, so it needs a signed-in session.",
    "how_to_fix": (
        "Connect over OAuth — your MCP client signs in with GitHub automatically "
        "(the server advertises the flow at /.well-known/oauth-protected-resource). "
        "Once the session carries a Bearer token, retry this call."
    ),
    "open_without_auth": ["node_status", "read_record", "whoami"],
    "docs": "https://ai.emercoin.com/docs/mcp.md",
}


def _principal() -> Principal:
    """The authenticated caller; raises a structured auth-required error if no valid
    token. Write tools require this (the error rides as `isError: true` tool text)."""
    p = _principal_optional()
    if p is None:
        raise ValueError(json.dumps(_AUTH_REQUIRED))
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


class WhoAmI(TypedDict, total=False):
    """The current session's identity. `authenticated` is always present; the
    GitHub-rooted fields are filled only when signed in, and `hint` only when not
    (nullable so the SDK may serialise the absent ones as null)."""
    authenticated: bool
    github_id: int | None
    github_login: str | None
    tariff: str | None
    hint: str | None


class WriteResult(TypedDict):
    """The on-chain write: the NVS name written and its transaction id."""
    name: str
    txid: str


mcp = FastMCP(
    "emercoin-agent",
    instructions=(
        "Use the Emercoin blockchain as an identity + memory layer for AI agents. "
        "Read tools (node_status, read_record, whoami) are open to everyone — no "
        "sign-in. Write tools (register_identity, store_memory) require a GitHub "
        "sign-in via OAuth, which your MCP client performs; on the FREE tier writes "
        "are rate-limited per minute. Typical flow: whoami → register_identity(address) "
        "→ store_memory(hash) → read_record(name). Records read back as `pending` and "
        "become `confirmed` after the next block (~10 min)."
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
    """Report the Emercoin node's version, block height, header height, peer
    connections and sync state (`synced` true once block == header height).
    Read-only, no sign-in required, no parameters. Call it first in a session to
    confirm the node is healthy and fully synced before trusting `read_record` or
    writing with `register_identity` / `store_memory`."""
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
        Field(description=(
            "Full NVS record name to read. Identity records are 'ai:gh:<github_id>' "
            "(e.g. 'ai:gh:3772563'); memory records are "
            "'ai:gh:<github_id>:mem:<sha256-hex>'. Any existing NVS name works."
        )),
    ],
) -> NvsRecord:
    """Read one Emercoin NVS (Name-Value Storage) record by its full name — an
    agent's identity (`ai:gh:<github_id>`) or a memory
    (`ai:gh:<github_id>:mem:<hash>`) written by `register_identity` / `store_memory`.
    Returns the confirmed on-chain record, or a `pending` one still in the mempool —
    the `status` field ('confirmed' | 'pending') distinguishes them. Read-only, no
    sign-in required; use `whoami` to find your own github_id. Returns null fields
    for a name that does not exist."""
    await _record(ctx, "read_record", _principal_optional())
    return await _adapter.read(name)  # type: ignore[return-value]


@mcp.tool(
    title="Who am I",
    annotations=ToolAnnotations(
        title="Who am I", readOnlyHint=True, idempotentHint=True, openWorldHint=False
    ),
    structured_output=True,
)
async def whoami(ctx: Context) -> WhoAmI:
    """Report the current session's identity. Read-only, no sign-in required: an
    anonymous session gets `{authenticated: false}` with a hint (not an error),
    a signed-in one gets `{authenticated: true}` plus the GitHub-rooted id, login
    and tariff. Call it to confirm who you are before `register_identity` /
    `store_memory`; an anonymous caller must sign in (GitHub OAuth) first."""
    p = _principal_optional()
    await _record(ctx, "whoami", p)
    if p is None:
        return {
            "authenticated": False,
            "hint": (
                "Anonymous session. Sign in with GitHub via your MCP client's OAuth flow "
                "to get an identity and use the write tools; read tools work without it."
            ),
        }
    return {
        "authenticated": True,
        "github_id": p.github_id,
        "github_login": p.github_login,
        "tariff": p.tariff,
    }


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
        Field(description=(
            "Emercoin address to bind to your GitHub identity, e.g. 'EVfAn...'. It is "
            "the anchor for later signature login — you must control its key (control "
            "is proven when you sign a challenge at login, not here)."
        )),
    ],
    metadata: Annotated[
        dict | None,
        Field(default=None, description=(
            "Optional JSON object stored verbatim in the identity record, "
            "e.g. {\"agent\": \"my-bot\", \"url\": \"https://...\"}. Omit if unused."
        )),
    ] = None,
) -> WriteResult:
    """Create or rotate your on-chain identity record `ai:gh:<github_id>`, binding an
    Emercoin address to your GitHub identity. Requires a signed-in session (OAuth)
    and counts against the FREE-tier per-minute write limit. Run `whoami` first to
    confirm you are signed in; anchor memories under this identity afterwards with
    `store_memory`. Writes one NVS transaction paid by the gateway (you need no EMC);
    the record reads back as `pending` at once and `confirmed` after the next block
    (~10 min on average). Idempotent — calling again rebinds the address. Returns the
    record name and the transaction id."""
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
        Field(description=(
            "Hash of the artifact/memory, e.g. a SHA-256 hex digest. It becomes the "
            "record's ':mem:<hash>' suffix; the content itself stays off-chain "
            "(e.g. IPFS) — only this fingerprint is anchored."
        )),
    ],
    metadata: Annotated[
        dict | None,
        Field(default=None, description=(
            "Optional JSON object stored with the record (note, source, tags, …). "
            "Omit if unused."
        )),
    ] = None,
) -> WriteResult:
    """Anchor a memory/artifact on-chain as the NVS record
    `ai:gh:<github_id>:mem:<content_hash>` — a tamper-evident fingerprint others can
    verify later. Requires a signed-in session (OAuth) and counts against the
    FREE-tier per-minute write limit. Writes one NVS transaction paid by the gateway;
    reads back `pending` at once, `confirmed` after the next block (~10 min). Not
    idempotent — each distinct hash is a new record. Register your identity first.
    Returns the record name and the transaction id."""
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
