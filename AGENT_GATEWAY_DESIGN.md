# Emercoin Agent Gateway — Design (v0)

Status: draft, 2026-06-10. Seeds the future agent-facing docs on emercoin.com.

## Purpose
A unified HTTP API that lets **AI agents** use the Emercoin blockchain as an
identity + data layer: store agent identity, hashes of research, memory pointers
as NVS (name-value storage) records. Fits the thesis that **agent identity** is
the foundational security problem — agents spawn sub-agents and delegate rights
at machine speed.

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
- **Registration root = GitHub ID.** GitHub identity is the trust anchor.
  Stateless: we trust a valid GitHub identity and grant it the right to create
  its root NVS record and further NVS records. No persistent agent registry.
- **Login paths:**
  - *Agent (target):* agent with granted rights authenticates with a **signature**
    (its keypair), bound to a GitHub identity.
  - *Human (for tests / bootstrap):* manual login flow so a person can verify the
    system works.
- **Credential = session JWT.** Self-contained: carries `github_id`, agent pubkey,
  tariff/scope. Gateway only verifies the signature — no DB lookup.
- **Tariffs / rate limit:** free tier = **10 NVS writes / minute**. Enforced via an
  in-memory **token bucket keyed by `github_id`** (Redis-ready for scale). This is
  the only state — ephemeral counters, not an agent registry.

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
- `POST /auth/login` — GitHub identity (dev: GitHub token; later: agent signature) -> JWT
- `GET  /info` — node `getinfo` passthrough (read, sanity check)
- `POST /nvs` — create NVS record (rate-limited by tariff)
- `GET  /nvs/{name}` — read NVS record (`name_show`)

## Out of scope (separate services)
- USDT->EMC exchanger — own wallet, own logic, HTTP client of gateway.
- Wallet/coin spend operations — later phase, behind scope + limits.

## Open points
- A. "Stateless" reconciled with rate-limit = no agent DB, but ephemeral per-id
  counters. (recommended above)
- B. On-chain owner = gateway wallet; agent ownership asserted in value. (recommended above)
- GitHub mechanism for agents (App vs OAuth App vs signed artifact) — TBD.
- Repo placement: currently alongside node infra; may split into own repo.
