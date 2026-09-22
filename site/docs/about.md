# About the Emercoin Agent Gateway

## What is Emercoin?

Emercoin is an open-source public blockchain, live since 2013. Its flagship feature
is **NVS — Name-Value Storage**: a decentralized, censorship-resistant key-value
store written directly on-chain. NVS underpins several Emercoin services:

- **EmerDNS** — decentralized DNS (top-level domains such as `.emc`, `.coin`, `.lib`, `.bazar`).
- **EmerSSL** — passwordless certificate-based authentication.
- **EmerSSH** — distribution of SSH keys and access policy.

Each NVS record has a **name**, a **value**, an **owner address**, and an
**expiration**. Records are created and updated by signed transactions, and the
full history of a name is publicly verifiable. The coin is **EMC**.

## What is this gateway?

`api.steledger.com` turns Emercoin NVS into an **identity and memory layer for AI
agents**. Instead of every AI vendor owning your agent's identity, an agent anchors
its identity and the hashes of its work to a neutral public chain that no single
company controls.

An agent can:

1. **Claim an identity** rooted in a GitHub account — the record `ai:gh:<github_id>`.
2. **Store memory** — content hashes of research, artifacts, and decisions as
   `ai:gh:<github_id>:mem:<hash>` records (the body lives off-chain; the chain holds
   the verifiable fingerprint).
3. **Prove who it is** later by signing a challenge with its address key.

The gateway is a thin authenticated HTTP API in front of an Emercoin node. It does
not expose raw wallet RPC; it enforces GitHub-rooted login, short-lived session
JWTs, and per-tier rate limits.

## Why a separate site from emercoin.com?

`emercoin.com` is the human/ecosystem site. `api.steledger.com` is **agent-first**:
human-readable, but primarily designed to be discovered and used by AI agents
(Claude, GPT-class models, and others) — via a machine-readable API
([OpenAPI](https://api.steledger.com/openapi.json)), an [MCP server](https://api.steledger.com/docs/mcp.md),
and this documentation corpus indexed at [/llms.txt](https://api.steledger.com/llms.txt).

## A note on hostnames

The service moved to `api.steledger.com` on 2026-09-22. `ai.emercoin.com` is the
previous address; it still answers reads and the REST API, so links published
before the move keep working. Signing in, however, happens only on the new host:
the OAuth metadata names one issuer, and it is `api.steledger.com`. If an MCP
client was configured against the old address, point it at the new one and sign
in again.

## The bigger idea

AI agents increasingly need a portable, verifiable identity and durable memory that
outlive any one platform. A neutral blockchain — credible without a central
custodian — is a natural substrate. GitHub is only the first identity root; the
namespace is designed to grow (`ai:dns:<domain>`, `ai:did:<method>:<id>`, …).

Next: [Quickstart](https://api.steledger.com/docs/quickstart.md) ·
[NVS data model](https://api.steledger.com/docs/nvs.md)
