# Emercoin Agent Tools — Architecture (v1)

Status: draft, updated 2026-06-11. Seeds the future agent-facing docs on emercoin.com.

## Purpose
Let **AI agents** use the Emercoin blockchain as an identity + data layer: store
agent identity, hashes of research, memory pointers as NVS (name-value storage)
records. (For *why* this matters — the agent-identity problem — see `AGENTS.md`;
this document covers *how* it is built.)

## Two layers, one responsibility each
The earlier single "gateway" mixed two unrelated jobs — translating node RPC into
REST, and authorizing agents. They are now split so each can be developed, tested
and deployed on its own (e.g. wallet+adapter at home, edge on a VPS).

```
docker-compose (internal network):
  emc        Emercoin node. RPC 6662 — internal only, NOT exposed.
             No real auth (rpcuser/pass). Trusts the internal network.
  adapter    RPC↔REST. Turns node JSON-RPC into a plain REST surface so nothing
             above it speaks RPC. NO user auth — trusts its callers (internal
             network, or a shared X-Internal-Key cross-host). /docs in dev.   :8000
  edge       Agent-facing IAM: the ONLY authorization boundary. GitHub login,
             session JWTs, signature login, rate limit. HTTP client of adapter. :8000
  redis      Ephemeral edge state: rate-limit windows + login nonces.

external:
  exchanger  Separate service, own wallet, USDT->EMC — HTTP client of adapter.
  agent MCPs External agents with their own MCP servers -> call the edge HTTP API.
```
The node authorizes nothing; the **adapter** is policy-free RPC↔REST; all IAM lives
in **edge**. Internal services that just need NVS/wallet ops talk to the adapter
directly; external agents go through the edge. The two layers never share a
process — edge reaches the adapter only over HTTP, so it can move to another host.

## Authorization
- **Registration root = GitHub ID.** GitHub identity is the trust anchor. No
  persistent agent registry: we trust a valid GitHub identity and grant it the
  right to create its root NVS record and further NVS records. The identity record
  is JWT-gated to its own `ai:gh:<id>` name, so it can only *claim* an address;
  control of that address is proven later, at agent-login.
- **Login paths:**
  - *Human / bootstrap:* `POST /auth/login` with a GitHub token -> JWT. Used once
    to register the agent's identity record on-chain (`POST /nvs/identity` with the
    agent's Emercoin address).
  - *Agent (machine speed):* challenge-response signature, no GitHub round-trip:
    `POST /auth/challenge {github_id}` -> nonce; agent signs it with its address key;
    `POST /auth/agent-login {github_id, address, signature}` -> JWT. The node's
    `verifymessage` checks the signature (pure crypto, works while syncing); the
    address must match the one bound on-chain in `ai:gh:<github_id>`.
- **Credential = session JWT.** Self-contained: carries `github_id`, agent pubkey,
  tariff/scope. Gateway only verifies the signature — no DB lookup.
- **Tariffs / rate limit:** free tier = **10 NVS writes / minute**. Enforced via a
  **sliding 60s window keyed by `github_id`** (Redis sorted set of write
  timestamps + atomic Lua check, so the per-minute boundary can't be burst across).
  This plus login nonces are the only state — ephemeral, not an agent registry.

## On-chain ownership (consequence of internal wallet)
The node wallet is shared and internal, so on-chain **all NVS records are owned by
the hot-wallet address**. Agent ownership is asserted *inside the record
value* (`github_id` + agent pubkey + signature), anchored to GitHub and recorded
on-chain — not by the UTXO key. Acceptable for v1.

## NVS data model (proposed)
Namespace per identity to avoid collisions:
- `ai:gh:<github_id>` — root identity record. Value: agent pubkey(s), owner GitHub
  id, parent agent (for delegation chains), declared scopes, signature.
- `ai:gh:<github_id>:mem:<hash>` — research / memory record. Value: content hash
  (body in IPFS/external store), metadata, signature.
Delegation: a sub-agent record references its parent → verifiable trust chain.

## Components (Python / FastAPI)
```
adapter/app/         RPC↔REST, policy-free. Trusts callers (+ optional X-Internal-Key).
  rpc.py             async JSON-RPC client to emc (httpx, single client)
  nvs.py             NVS mechanics: name_new/update/show/history/mempool/updatemany
  main.py            REST routes (/nvs, /verify, /wallet, /info, /status)
  config.py          ADAPTER_* settings

edge/app/            agent-facing IAM. HTTP client of the adapter.
  auth.py            GitHub login + issue/verify session JWT
  challenge.py       single-use login nonces (Redis)
  ratelimit.py       sliding 60s window per github_id (Redis + Lua)
  names.py           the ai:gh:<id> naming policy (lives here, not in the adapter)
  client.py          httpx client to the adapter (carries X-Internal-Key)
  main.py            FastAPI routes; delegates chain ops to client.py
  config.py          EDGE_* settings

mcp_server/server.py thin MCP client of the edge HTTP API
```

## Published images (CI → Docker Hub)
Two independent images, each with its own release tag so one tag never triggers
both pipelines:

| Image | Source | Workflow | Release tag | Arch |
|-------|--------|----------|-------------|------|
| `emercoin/rest-api` | `adapter/` | `publish-rest-api.yml` | `rest-api-v*` (e.g. `rest-api-v0.0.1`) | amd64+arm64 |
| `emercoin/core` | `node/` | `publish-node.yml` | `node-v*` (e.g. `node-v0.8.5`) | amd64 |

- **`emercoin/rest-api`** — the generic RPC↔REST front for the wallet (nothing
  agent-specific), so other services pull it instead of vendoring source.
- **`emercoin/core`** — the wallet/node itself; `node-v*` publishes
  `emercoin/core:<EMER_DISTR_VERSION>` + `latest` (the tag is read from
  `node/Dockerfile`). amd64 only (the emercoind tarball is x86_64). A manual
  `workflow_dispatch` publishes only a `<ver>-test` tag for verification — it
  never overwrites `:latest`. **A `node-v*` release overwrites the official
  image; verify the `-test` build first.**

The USDT→EMC exchanger (separate repo) runs both:
```
image: emercoin/core:0.8.5      # the wallet/node
image: emercoin/rest-api:0.0.1  # RPC↔REST in front of it
```

## Adapter endpoints (internal REST, no user auth)
- `GET  /info`, `GET /status`, `GET /` — node info / sync / aggregated state
- `POST /nvs`, `POST /nvs/batch` — generic create/update (name chosen by caller)
- `GET  /nvs/{name}`, `GET /history/{name}`, `GET /addresses/{address}/names`
- `POST /verify` — `verifymessage` (used by edge agent-login)
- `GET  /wallet/address`, `GET /wallet/balance` — fund/inspect the hot-wallet

## Edge endpoints (agent-facing, authorized + rate-limited)
- `POST /auth/login` — GitHub token -> JWT (bootstrap); `POST /auth/challenge` +
  `POST /auth/agent-login` — agent signature -> JWT (machine speed)
- `GET  /info`, `GET /status` — proxied from the adapter
- `POST /nvs/identity` — register/rotate the `ai:gh:<id>` identity record
- `POST /nvs/mem`, `POST /nvs/mem/batch` — store memory hash(es); batch is atomic
  (`name_updatemany`). All rate-limited by tariff.
- `GET  /nvs/{name}` — read NVS record (confirmed, or mempool as `pending`)

## Out of scope (separate services)
- USDT->EMC exchanger — own wallet, own logic, HTTP client of the adapter.
- Wallet/coin spend operations — later phase, behind scope + limits.

## Open points
- A. "No agent registry" reconciled with rate-limit = no agent DB, but ephemeral
  per-id counters + login nonces. (recommended above)
- B. On-chain owner = gateway wallet; agent ownership asserted in value. (recommended above)
- GitHub mechanism for agents (App vs OAuth App vs signed artifact) — TBD.
- **Hot-wallet hardening.** Today one hot-wallet signs every write and its balance
  is RPC-visible. Plan the exchange pattern: a small spending wallet refilled
  periodically from a cold treasury, plus a spend rate cap (EMC/hour) and alerting
  on anomalous write rate. A public custody policy buys more trust than a legal
  entity (layer-2 "credible without a juridical person").
- **Namespace beyond GitHub.** `ai:gh:<id>` is a bootstrap root; design for
  `ai:dns:<domain>`, `ai:did:<method>:<id>`, etc. so the "neutral cross-org
  identity" claim isn't tied to a single provider (GitHub = Microsoft).
- **Adapter ↔ edge split (done, 2026-06-11).** Two FastAPI apps now; edge is an
  HTTP client of the adapter. Layout: `node/` (image build), `adapter/`, `edge/`,
  `mcp_server/`, `deploy/` (compose with dev|prod profiles). Next: the two layers
  could become separate repos / hosts (wallet+adapter at home, edge on a VPS) —
  the X-Internal-Key gate already supports that topology.
