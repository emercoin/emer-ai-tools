![](https://github.com/emercoin/emer-ai-tools/blob/main/docs/docker.png)
[![smithery badge](https://smithery.ai/badge/mechnotech/emer-ai)](https://smithery.ai/servers/mechnotech/emer-ai)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

# Emercoin + AI agent tools (`emer-ai-tools`)

A runnable Docker stack: an **Emercoin node** plus an **agent gateway** that turns
the chain's Name-Value Storage (NVS) into an **on-chain identity & memory layer for
AI agents**. An agent can prove who it is and anchor what it has learned on a public
blockchain — **without holding any cryptocurrency**. Hosted at
**[ai.emercoin.com](https://ai.emercoin.com)**; exposed to agents as the
`emercoin-agent` MCP server.

> **🤖 Building with an AI agent?** Read **[AGENTS.md](AGENTS.md)** — the problem it
> solves, the trust model, the tools, and a first-flow quickstart. A ready-to-use
> Claude Code skill ships at `.claude/skills/emercoin-identity/` (invoke with
> `/emercoin-identity`). Design notes: **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

The repo was originally just a Dockerized Emercoin node; it is now a full
application built on top of that node. You can run the **whole stack**, use the
**hosted service**, or run **just the node** — see the sections below.

## What's in here

```
 AI agent ──MCP tools──▶ edge (auth boundary) ──HTTP──▶ adapter ──JSON-RPC──▶ node
                              │                       (RPC↔REST)        (NVS on-chain)
                              └── Redis (rate limit + login nonces)
```

| Component | Path | Role |
|-----------|------|------|
| **node** (`emc`) | `node/` | Emercoin core — holds the chain + hot-wallet; internal-only, authorizes nothing. |
| **adapter** (`emer-adapter`) | `adapter/` | RPC↔REST: a plain REST surface over the node's JSON-RPC. Internal, gated by `X-Internal-Key`. |
| **edge** (`emer-edge`) | `edge/` | The trust boundary: authenticates agents (GitHub → JWT / signature login), rate-limits writes, builds NVS records, mounts the `emercoin-agent` MCP at `/mcp`. |
| **mcp_server** | `mcp_server/` | A thin stdio MCP client of the edge, distributed via Docker / Smithery for local use. |
| **site** | `site/` | The public `ai.emercoin.com` front-end (landing, login, stats). |

## Use it as an agent (hosted)

The `emercoin-agent` MCP server is live — no self-hosting needed:

- **Streamable HTTP:** `https://ai.emercoin.com/mcp` (read tools open; write tools need
  a GitHub sign-in via OAuth, performed by your MCP client).
- **Smithery / stdio Docker image:** see the [Smithery listing](https://smithery.ai/servers/mechnotech/emer-ai)
  and `mcp_server/README.md`.

Tools: `node_status`, `read_record` (open) and `register_identity`, `store_memory`,
`store_memory_batch` (after login). Full reference + first-flow in **[AGENTS.md](AGENTS.md)**.

## Run the full stack (self-host)

Node (mainnet) + adapter + edge + redis, dev profile:
```bash
git clone https://github.com/emercoin/emer-ai-tools && cd emer-ai-tools
cp node/emercoin.conf.example node/emercoin.conf      # set rpcpassword
docker compose -f deploy/docker-compose.yaml --profile dev up -d --build
```
Edge API on `:8000`; the adapter's RPC↔REST docs are browsable at
`http://localhost:8001/docs` (dev profile). Wire the MCP server into your agent and
run the first flow — see the [AGENTS.md quickstart](AGENTS.md#quickstart).
(Use `--profile prod` to gate the adapter behind a shared `X-Internal-Key`.)

## Run just the Emercoin node

The node alone (no agent tools) is the default stack — no profile needed. It is a
classic Emercoin wallet in a container with a separate volume for the blockchain:
cross-platform, one-click version bumps, usable from your own projects over JSON-RPC.

```bash
cp node/emercoin.conf.example node/emercoin.conf
docker compose -f deploy/docker-compose.yaml up -d --build
```

Initial sync takes a few hours, but the RPC is usable right away. By default port
**6662** connects to the container:
- address: **127.0.0.1** · user: **emcrpc** · password: **emcpass**
- method: **POST**, e.g. body `{"method": "getinfo"}`

**Change the RPC password:**
```bash
docker compose -f deploy/docker-compose.yaml exec emc bash changepass.sh
docker compose -f deploy/docker-compose.yaml restart emc
```

**Health check** — POST to `http://emcrpc:emcpass@127.0.0.1:6662` with `{"method":"getinfo"}`:
```bash
curl --location --request POST 'emcrpc:emcpass@127.0.0.1:6662' \
  --header 'Content-Type: application/json' \
  --data-raw '{"method": "getinfo"}'
```
A healthy node replies with JSON (`fullversion`, `version`, `balance`, …).

**Manage the build:**
```bash
docker compose -f deploy/docker-compose.yaml stop emc    # stop
docker compose -f deploy/docker-compose.yaml down        # remove containers (keeps the volume)
docker volume rm emer_data                               # delete the chain DB — also deletes wallet.dat!
```

## Status

MVP, verified end-to-end on mainnet: identity registration, signature login, single
+ atomic batch memory writes, reads, history, names-by-address. Not yet
production-hardened (GitHub App/OAuth login, ≥32-byte JWT secret, hot-wallet split);
the `prod` compose profile already gates the adapter behind `X-Internal-Key`. Details
in **[AGENTS.md](AGENTS.md)** and **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

## License

MIT — see [LICENSE](LICENSE).
