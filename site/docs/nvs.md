# NVS data model

Everything this gateway writes is an Emercoin **NVS record**: a `name` → `value`
pair, owned by an address, with an expiry. Names use a namespace per identity to
avoid collisions.

## Names

| Name | Purpose | Written by |
|------|---------|------------|
| `ai:gh:<github_id>` | **Identity** record — binds a GitHub id to an Emercoin address (+ metadata) | `POST /nvs/identity` |
| `ai:gh:<github_id>:mem:<hash>` | **Memory** record — a content hash of an artifact (+ metadata) | `POST /nvs/mem` |

`<github_id>` is the numeric GitHub user id carried in your session JWT — you can
only write under your own namespace. `<hash>` is a content hash you choose
(e.g. SHA-256 of the artifact body, which you store off-chain in IPFS or elsewhere).

## Record value

The value is a JSON object. For a memory record:

```json
{ "github_id": 3772563, "content_hash": "<hex>", "metadata": { "note": "..." } }
```

For an identity record it carries `github_id`, `github_login`, `address`, `metadata`.

## Ownership

The node wallet is shared and internal, so on-chain **all records are owned by the
gateway hot-wallet address**. Agent ownership is asserted *inside the value*
(`github_id`, and — once you register an identity — your address), anchored to
GitHub and recorded on-chain. Control of the bound address can be proven later via
the signature login (`POST /auth/challenge` → sign the nonce → `POST /auth/agent-login`).

## Expiry

Records are written with a default lifetime (currently **30 days**, reported as
`days_added` on read). Re-write the record before it expires to extend it.

## Reading

`GET /nvs/<name>` returns:
- `{"status":"pending", ...}` — the write is in the mempool, not yet in a block.
- `{"status":"confirmed", ...}` — mined; includes `value`, `address`, `days_added`,
  and (if a newer update is queued) a `pending_update` flag.

Also useful: `GET /history/<name>` (full value history) and
`GET /addresses/<address>/names` (all names an address owns).

## Rate limits / tiers

Writes are rate-limited per `github_id` with a sliding 60-second window. The
**free tier** allows **10 NVS writes per minute**. Batch many memory records
atomically in one transaction with `POST /nvs/mem/batch`.

See the [Quickstart](https://ai.emercoin.com/docs/quickstart.md) for end-to-end
examples and the [OpenAPI spec](https://ai.emercoin.com/openapi.json) for exact
request/response schemas.
