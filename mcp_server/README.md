# Emercoin Agent — MCP server

Thin MCP adapter over the Agent Gateway HTTP API. Lets an AI agent use the
Emercoin chain as its identity + memory layer.

## Tools
| Tool | Auth | Maps to |
|------|------|---------|
| `node_status()` | no | `GET /status` |
| `login(github_token)` | no | `POST /auth/login` (caches JWT) |
| `register_identity(address, metadata?)` | yes | `POST /nvs/identity` |
| `store_memory(content_hash, metadata?)` | yes | `POST /nvs/mem` |
| `read_record(name)` | no | `GET /nvs/{name}` |

## Config (env)
- `GATEWAY_URL` — gateway base URL (default `http://gateway:8000`)
- `GATEWAY_JWT` — optional pre-issued token; otherwise use the `login` tool

## Run (stdio transport)
```bash
pip install -r requirements.txt
GATEWAY_URL=http://localhost:8000 python server.py
```

### Claude Code MCP config example
```json
{
  "mcpServers": {
    "emercoin-agent": {
      "command": "python",
      "args": ["/path/to/mcp_server/server.py"],
      "env": { "GATEWAY_URL": "http://localhost:8000" }
    }
  }
}
```
