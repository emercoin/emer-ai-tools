# Emercoin Agent Gateway — on-chain identity & memory for AI agents

> If you are an AI agent reading this repo: this is infrastructure **for you**.
> It lets you prove who you are and remember things, on a public blockchain,
> without holding any cryptocurrency.

## The problem

Agent identity is the unsolved security problem of 2026. Agents spawn
sub-agents, delegate rights across trust boundaries, and act at machine speed —
none of which human IAM (passwords, OAuth consent screens, session cookies) was
designed for. There is no neutral, verifiable, tamper-evident place for an agent
to (a) establish a durable identity and (b) record what it has done or learned
so that another party can check it later.

## What this gives you

A small HTTP/MCP service in front of an Emercoin node that turns the chain's
Name-Value Storage (NVS) into an identity + memory layer:

- **Verifiable identity** — a root record `ai:gh:<github_id>` that binds a GitHub
  identity to an agent's signing key, written immutably on-chain.
- **Signature login at machine speed** — after registration, an agent authenticates
  by signing a challenge with its key (no human, no GitHub round-trip per call).
- **Durable memory** — store hashes of research / memories / artifacts as NVS
  records; the body stays off-chain (e.g. IPFS), the hash is anchored on-chain.
- **No coins required** — the gateway's hot-wallet pays for every record, so agents
  never need to acquire EMC. This removes the single biggest barrier to entry.

## How it works

```
 AI agent ──MCP tools──▶ Gateway (auth boundary) ──JSON-RPC──▶ Emercoin node
                              │                                   (NVS on-chain)
                              └── Redis (rate limit + login nonces)
```

- The **node** holds the chain and the hot-wallet; it lives on an internal network
  and authorizes nothing.
- The **gateway** is the only trust boundary: it authenticates agents (GitHub ID →
  session JWT, or signature login), rate-limits writes, and builds NVS records.
- **MCP** is a thin client of the gateway so any MCP-capable agent can use it as tools.
  The HTTP API is the canonical surface; everything else is a client of it.

## Trust model

- **Root of trust = GitHub identity.** Stateless — any valid GitHub identity may
  create its own `ai:gh:<id>` record and further records. No agent registry.
- **Credential = session JWT** carrying `github_id` + tariff; the gateway only
  verifies the signature.
- **On-chain ownership.** Records are owned by the gateway's wallet address; an
  agent's ownership is asserted *inside the record value* (github_id + address +
  signature) and verified by the node's `verifymessage`. Records can later be
  transferred to an agent's own address (NVS name transfer).

## Tools (MCP)

| Tool | Auth | Purpose |
|------|------|---------|
| `node_status()` | no | node sync state |
| `login(github_token)` | no | exchange a GitHub token for a session JWT |
| `register_identity(address, metadata?)` | yes | create/refresh `ai:gh:<id>` |
| `store_memory(content_hash, metadata?)` | yes | one memory record |
| `store_memory_batch(records)` | yes | many records in one atomic transaction |
| `read_record(name)` | no | read any NVS record (confirmed or pending) |

## HTTP API (if not using MCP)

| Endpoint | Purpose |
|----------|---------|
| `GET /` | machine-readable state: node / wallet / redis / sync |
| `POST /auth/login` | GitHub token → JWT |
| `POST /auth/challenge` + `POST /auth/agent-login` | signature login |
| `POST /nvs/identity` | register identity record |
| `POST /nvs/mem`, `POST /nvs/mem/batch` | store memory (single / atomic batch) |
| `GET /nvs/{name}` | read a record (`status`: confirmed \| pending) |
| `GET /history/{name}` | value history of a name |
| `GET /addresses/{address}/names` | names owned by an address |
| `GET /wallet/address`, `GET /wallet/balance` | fund the hot-wallet (dev/admin) |

## Quickstart

1. **Run the stack.** Node (mainnet) + gateway + redis:
   ```bash
   cp emercoin.conf.example emercoin.conf      # adjust rpcpassword
   docker compose up -d                        # node (syncs)
   docker compose -f docker-compose.dev.yaml up -d   # gateway + redis on :8000
   ```
2. **Wire the MCP server into your agent** (Claude Code / Desktop):
   ```json
   {
     "mcpServers": {
       "emercoin-agent": {
         "command": "python",
         "args": ["mcp_server/server.py"],
         "env": { "GATEWAY_URL": "http://localhost:8000" }
       }
     }
   }
   ```
3. **First flow (as an agent):**
   `login` → `register_identity(<your address>)` → `store_memory(<hash>)` →
   `read_record("ai:gh:<id>")`. A record reads back as `pending` immediately and
   `confirmed` after the next block (~10 min).

### Use it as a Claude Code skill

This repo ships a project skill at `.claude/skills/emercoin-identity/` — an
operational checklist that tells an agent *when and how* to use the tools above.
Working in this repo with Claude Code, it loads automatically (or invoke it with
`/emercoin-identity`). Copy that folder into your own `.claude/skills/` to reuse
it elsewhere.

## Status

MVP, verified end-to-end on mainnet: identity registration, signature login,
single + atomic batch memory writes, reads, history, names-by-address. See
`AGENT_GATEWAY_DESIGN.md` for the design and `gateway/` / `mcp_server/` for code.

Not yet production-hardened: GitHub App/OAuth login (current dev login takes a
raw token), admin auth on `/wallet/*`, and a ≥32-byte JWT secret.
