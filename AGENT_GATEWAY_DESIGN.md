# Emercoin Agent Gateway — Design (v0)

Status: draft, 2026-06-10. Seeds the future agent-facing docs on emercoin.com.

## Purpose
A unified HTTP API that lets **AI agents** use the Emercoin blockchain as an
identity + data layer: store agent identity, hashes of research, memory pointers
as NVS (name-value storage) records. (For *why* this matters — the agent-identity
problem — see `AGENTS.md`; this document covers *how* it is built.)

## Topology
```
docker-compose (internal network):
  emc        Emercoin node. RPC 6662 — internal only, NOT exposed.
             No real auth (rpcuser/pass). Trusts the internal network.
  gateway    Unified HTTP API. The ONLY authorization boundary.  :8000

external:
  exchanger  Separate service, own wallet, USDT->EMC. HTTP client of gateway.
  agent MCPs External agents with their own MCP servers -> call gateway HTTP.
```
The node authorizes nothing; all IAM lives in `gateway`. Every future service
(exchanger included) is just an HTTP client of the gateway.

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
the gateway hot-wallet address**. Agent ownership is asserted *inside the record
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
gateway/
  core/rpc.py    async JSON-RPC client to emc (httpx, single client)
  core/nvs.py    NVS domain: create/read records (name_new/name_show/name_filter)
  auth/jwt.py    issue/verify session JWT
  auth/github.py verify GitHub identity (login) + signature path
  ratelimit.py   token bucket per github_id
  api.py         FastAPI routes
```

## Phase 1 (prototype) endpoints
- `POST /auth/login` — GitHub token -> JWT (bootstrap); `POST /auth/challenge` +
  `POST /auth/agent-login` — agent signature -> JWT (machine speed)
- `GET  /info`, `GET /status` — node `getinfo` / sync-state passthrough (sanity check)
- `POST /nvs/identity` — register/rotate the `ai:gh:<id>` identity record
- `POST /nvs/mem`, `POST /nvs/mem/batch` — store memory hash(es); batch is atomic
  (`name_updatemany`). All rate-limited by tariff.
- `GET  /nvs/{name}` — read NVS record (`name_show`, or mempool as `pending`)
- `GET  /wallet/address`, `GET /wallet/balance` — fund/inspect the hot-wallet (dev/admin)

## Out of scope (separate services)
- USDT->EMC exchanger — own wallet, own logic, HTTP client of gateway.
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
- Repo placement: currently alongside node infra; may split into own repo.
