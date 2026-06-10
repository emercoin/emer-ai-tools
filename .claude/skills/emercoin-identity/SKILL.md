---
name: emercoin-identity
description: Give an AI agent a verifiable on-chain identity and durable memory on the Emercoin blockchain, via the emercoin-agent MCP tools. Use when an agent needs to register its identity, store hashes of research/memories/artifacts on-chain, prove who it is by signature, or read another agent's on-chain identity or records.
---

# Emercoin on-chain identity & memory for agents

This project (emer-ai-tools) exposes the Emercoin blockchain as an identity +
memory layer for AI agents through the **`emercoin-agent` MCP server**. Agents
need **no cryptocurrency** — the gateway's hot-wallet pays for every record.

Read `AGENTS.md` for the full rationale and trust model. This skill is the
operational checklist for *using* the tools.

## When to use

- An agent wants a durable, verifiable identity → register an identity record.
- An agent wants to remember something (research result, document, prior memory)
  in a tamper-evident way → store its **hash** on-chain (keep the body off-chain).
- You need to look up an agent's identity or a stored record → read it back.

## Prerequisites

The MCP server must be configured (see `AGENTS.md` → Quickstart). It needs the
gateway reachable at `GATEWAY_URL`. Auth is either a session JWT obtained with
`login(github_token)`, or a pre-set `GATEWAY_JWT` env var.

## Tools (emercoin-agent MCP)

| Tool | Use it to |
|------|-----------|
| `node_status()` | check the node is synced before relying on reads |
| `login(github_token)` | get a session JWT (GitHub identity = root of trust) |
| `register_identity(address, metadata?)` | create/refresh this agent's `ai:gh:<id>` record |
| `store_memory(content_hash, metadata?)` | record one memory/research hash |
| `store_memory_batch(records)` | record many hashes in ONE atomic transaction |
| `read_record(name)` | read any record by NVS name |

## Standard flows

### 1. Establish identity (once)
1. `login(<github_token>)` — establishes the agent under a GitHub identity.
2. Obtain an Emercoin address as the agent's signing key (the operator funds /
   manages the gateway wallet; for a self-sovereign key, generate one and supply
   its address).
3. `register_identity(<address>, {"role": "...", "model": "..."})`.
   This writes `ai:gh:<github_id>` binding the GitHub id ↔ address on-chain.

### 2. Store a memory / research hash
- Hash the artifact yourself; store the **body off-chain** (IPFS, object store).
- One item: `store_memory("<sha256>", {"kind": "research", "ref": "<uri>"})`.
- Many items: `store_memory_batch([{ "content_hash": "...", "metadata": {...} }, ...])`
  — atomic and cheaper (one transaction). Prefer this for >1 record.

### 3. Read back
- `read_record("ai:gh:<id>")` for an identity, or
  `read_record("ai:gh:<id>:mem:<hash>")` for a memory record.
- A just-written record returns `status: "pending"` (in the mempool) and flips to
  `status: "confirmed"` after the next block (~10 min). Don't treat `pending` as
  failure; re-read later to confirm.

## Conventions & limits

- **Never put secrets or raw bodies on-chain** — only hashes + small metadata.
  NVS records are public and permanent for their lifetime.
- **Rate limit**: free tier allows 10 NVS writes/minute (a batch of N counts as N).
- **Names are namespaced** per GitHub id: `ai:gh:<id>` (identity),
  `ai:gh:<id>:mem:<hash>` (memory). Don't write outside your namespace.
- **Records expire** (default ~30 days) unless refreshed — re-register/re-store to
  extend anything that must persist.

## If something fails

- 401 / "not authenticated" → call `login` first (or set `GATEWAY_JWT`).
- 429 → you hit the per-minute write limit; batch your writes or wait.
- `read_record` 404 right after a write → it's still pending; re-read after a block.
- Check `node_status().synced` — reads of confirmed names need a synced node.
