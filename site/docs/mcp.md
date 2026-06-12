# Using the gateway over MCP

For agents that speak the **Model Context Protocol** (e.g. Claude Desktop / Claude
Code), the `emercoin-agent` MCP server wraps this gateway's HTTP API as tools, so
the agent never has to craft raw HTTP requests.

## Remote endpoint (hosted — no install)

The fastest path: connect directly to the **hosted** server over Streamable HTTP —
nothing to install.

- **URL:** `https://ai.emercoin.com/mcp`
- **Auth:** read tools (`node_status`, `read_record`) are open. Write tools need a
  session JWT in the `Authorization: Bearer <token>` header — get one at
  <https://ai.emercoin.com/login>.

```jsonc
// Claude Code / Desktop MCP config (HTTP transport)
{
  "mcpServers": {
    "emercoin-agent": {
      "url": "https://ai.emercoin.com/mcp",
      "headers": { "Authorization": "Bearer <your session token>" }
    }
  }
}
```

Prefer to run it yourself? Use the local stdio server below.

## Tools

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

1. `node_status` — confirm the chain is synced.
2. `login` — get a device code; the human authorizes it once at github.com/login/device.
3. `login_poll` — receive the session JWT (held by the server for subsequent calls).
4. `register_identity` (once) and `store_memory` / `store_memory_batch` (ongoing).
5. `read_record` — verify what's on-chain.

Prefer raw HTTP? Everything above is also available directly — see the
[Quickstart](https://ai.emercoin.com/docs/quickstart.md) and the
[OpenAPI spec](https://ai.emercoin.com/openapi.json).
