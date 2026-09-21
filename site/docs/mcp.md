# Using the gateway over MCP

For agents that speak the **Model Context Protocol** (e.g. Claude Desktop / Claude
Code), the `emercoin-agent` MCP server wraps this gateway's HTTP API as tools, so
the agent never has to craft raw HTTP requests.

## Remote endpoint (hosted — no install)

Connect directly to the **hosted** server over Streamable HTTP — nothing to install.

- **URL:** `https://ai.emercoin.com/mcp`

### Getting started
1. **Add the server as a connector** — point your MCP client at the URL above and
   nothing else. Sign-in happens automatically: on first use of a write tool your
   client runs the OAuth flow (dynamic client registration + authorization code +
   PKCE) and redirects you to GitHub to authorize; the edge issues an access token
   good for the session plus a refresh token good for 30 days, so you stay signed
   in across reconnects. The **read tools** (`node_status`, `read_record`,
   `whoami`) work **immediately, with no sign-in at all**.

```jsonc
// Claude Code / Desktop MCP config (HTTP transport) — no token needed, OAuth handles it
{
  "mcpServers": {
    "emercoin-agent": {
      "url": "https://ai.emercoin.com/mcp"
    }
  }
}
```

2. **No OAuth in your client?** Fall back to a manual token: open
   <https://ai.emercoin.com/login>, sign in with GitHub, copy the token shown, and
   put it in the `Authorization: Bearer <token>` header. It's the same session JWT
   the OAuth flow issues, so both paths are fully interchangeable — but a manual
   token is short-lived and isn't refreshed for you, so OAuth is the path to prefer
   whenever your client supports it.

```jsonc
// Manual-token fallback
{
  "mcpServers": {
    "emercoin-agent": {
      "url": "https://ai.emercoin.com/mcp",
      "headers": { "Authorization": "Bearer <token from /login>" }
    }
  }
}
```

Prefer to run it yourself? Use the local stdio server below.

## Tools — remote (hosted, OAuth)

| Tool | Auth | What it does |
|------|------|--------------|
| `node_status` | open | node sync/height (`GET /status`) |
| `read_record` | open | read any NVS record |
| `whoami` | open | current session identity (`{authenticated: false}` with a sign-in hint until you're signed in) |
| `register_identity` | sign-in required | register the `ai:gh:<id>` identity record |
| `store_memory` | sign-in required | write one memory record (`ai:gh:<id>:mem:<hash>`) |

## Tools — local (stdio)

The local server swaps OAuth (no browser redirect to catch outside a browser) for
device-flow / manual-token login, and adds an atomic batch-write tool:

| Tool | What it does |
|------|--------------|
| `node_status` | node sync/height (`GET /status`) |
| `login` | start GitHub device-flow login → returns a user code + URL |
| `login_poll` | poll the device-flow until authorized → returns the session JWT |
| `login_with_token` | dev fallback: exchange a raw GitHub token for a JWT |
| `register_identity` | register the `ai:gh:<id>` identity record |
| `store_memory` | write one memory record (`ai:gh:<id>:mem:<hash>`) |
| `store_memory_batch` | write many memory records atomically |
| `read_record` | read any NVS record |

## Connect

The server is a small stdio MCP server (Python) in the
[emer-ai-tools repo](https://github.com/emercoin/emer-ai-tools) under `mcp_server/`.
Point it at the public gateway with the `GATEWAY_URL` environment variable:

```bash
# from a checkout of the repo
GATEWAY_URL=https://ai.emercoin.com

# register with Claude Code (stdio, local scope)
claude mcp add emercoin-agent -- \
  uv run --directory /path/to/emer-ai-tools/mcp_server python server.py
```

(Set `GATEWAY_URL=https://ai.emercoin.com` in the server's environment; it defaults
to `http://localhost:8000` for local development.)

## Typical flow

**Remote (hosted, OAuth):**
1. `node_status` — confirm the chain is synced.
2. `whoami` — check whether you're already signed in; if not, your client's OAuth
   flow runs on the first write call.
3. `register_identity` (once) and `store_memory` (ongoing).
4. `read_record` — verify what's on-chain.

**Local (stdio):**
1. `node_status` — confirm the chain is synced.
2. `login` — get a device code; the human authorizes it once at github.com/login/device.
3. `login_poll` — receive the session JWT (held by the server for subsequent calls).
4. `register_identity` (once) and `store_memory` / `store_memory_batch` (ongoing).
5. `read_record` — verify what's on-chain.

Prefer raw HTTP? Everything above is also available directly — see the
[Quickstart](https://ai.emercoin.com/docs/quickstart.md) and the
[OpenAPI spec](https://ai.emercoin.com/openapi.json).
