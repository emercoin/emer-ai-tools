# Quickstart

**MCP-capable agent?** Skip everything below — add `https://api.steledger.com/mcp`
as a connector and your client signs you in with GitHub automatically (OAuth,
no token to copy). See the [MCP guide](https://api.steledger.com/docs/mcp.md). The
steps here are the raw HTTP path: use them for scripting, a sandbox, or any client
without MCP/OAuth support.

Base URL: `https://api.steledger.com`. All chain-writing endpoints require a session
JWT in the `Authorization: Bearer <token>` header. Reads are open.

Check the node is healthy and synced:

```bash
curl https://api.steledger.com/status
# {"version":"v0.8.5emc","blocks":...,"synced":true,...}
```

## 1. Authenticate

### Option A — browser (humans)
Open <https://api.steledger.com/login>, click **Continue with GitHub**, and copy the
session token shown on the result page.

### Option B — device flow (headless agents)
No browser on the agent side. Start the flow, show the user a short code, then poll.

```bash
# Start — returns user_code, verification_uri, session_id, interval, expires_in
curl -X POST https://api.steledger.com/auth/github/device/start

# The user opens verification_uri (https://github.com/login/device) and enters user_code.

# Poll until authorized — 202 while pending, 200 + access_token once done
curl -X POST https://api.steledger.com/auth/github/device/poll \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"<session_id from start>"}'
# 200 -> {"access_token":"<JWT>","github_id":...,"github_login":"...","tariff":"free"}
```

Save the `access_token`; it is your session JWT (short-lived).

## 2. Confirm your identity

```bash
TOKEN=<your JWT>
curl https://api.steledger.com/me -H "Authorization: Bearer $TOKEN"
# {"github_id":...,"github_login":"...","tariff":"free"}
```

## 3. Write a memory record on-chain

Store the hash of an artifact (the body stays off-chain; the chain holds the proof):

```bash
curl -X POST https://api.steledger.com/nvs/mem \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"content_hash":"<sha256-hex>","metadata":{"note":"research result"}}'
# {"name":"ai:gh:<id>:mem:<hash>","result":"<txid>"}
```

## 4. Read it back

```bash
curl "https://api.steledger.com/nvs/ai:gh:<id>:mem:<hash>"
# {"status":"pending",...}  immediately (in the mempool), then
# {"status":"confirmed",...} once it lands in a block (~10 min)
```

## (Optional) Register your identity record

Bind an Emercoin address to your GitHub identity so you can later prove control by
signature (machine-speed agent login without a GitHub round-trip):

```bash
curl -X POST https://api.steledger.com/nvs/identity \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"address":"<your-emercoin-address>","metadata":{}}'
# {"name":"ai:gh:<id>","result":"<txid>"}
```

Full machine-readable contract: [OpenAPI](https://api.steledger.com/openapi.json) ·
prefer MCP? see the [MCP guide](https://api.steledger.com/docs/mcp.md) ·
naming and limits: [NVS data model](https://api.steledger.com/docs/nvs.md)
