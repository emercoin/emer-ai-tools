"""MCP adapter for the Emercoin Agent Gateway.

A thin MCP server that exposes the edge gateway's HTTP API as tools, so an AI
agent can use the Emercoin chain as its identity + memory layer directly. The
edge remains the canonical agent-facing surface and authorization boundary; this
is just a client.

Config (env):
  GATEWAY_URL  base URL of the edge gateway (default http://localhost:8000)
  GATEWAY_JWT  optional pre-issued session token; otherwise call the `login` tool

Run: `python server.py` (stdio transport — the agent's MCP client launches it).
"""
from __future__ import annotations

import asyncio
import os
import time

import httpx
from mcp.server.fastmcp import FastMCP

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:8000").rstrip("/")

mcp = FastMCP("emercoin-agent")

# Session token cached across tool calls (set by `login_poll`, or seeded from env).
_token: str | None = os.environ.get("GATEWAY_JWT")

# Poll interval per pending device-login session (set by `login`).
_device_intervals: dict[str, int] = {}


def _auth_headers() -> dict[str, str]:
    if not _token:
        raise RuntimeError("not authenticated: call the `login` tool or set GATEWAY_JWT")
    return {"Authorization": f"Bearer {_token}"}


@mcp.tool()
async def node_status() -> dict:
    """Get Emercoin node sync status (blocks, headers, progress, synced)."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{GATEWAY_URL}/status")
        resp.raise_for_status()
        return resp.json()


@mcp.tool()
async def login() -> dict:
    """Begin GitHub login (device flow). Returns a short code; SHOW IT TO THE USER
    and ask them to open `verification_uri` and enter `user_code`, then call
    `login_poll(session_id)` to finish. No GitHub token needed from the user."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(f"{GATEWAY_URL}/auth/github/device/start")
        resp.raise_for_status()
        data = resp.json()
    _device_intervals[data["session_id"]] = int(data.get("interval", 5))
    return {
        "session_id": data["session_id"],
        "user_code": data["user_code"],
        "verification_uri": data["verification_uri"],
        "expires_in": data["expires_in"],
        "instructions": (
            f"Tell the user to open {data['verification_uri']} and enter the code "
            f"{data['user_code']}, then call login_poll('{data['session_id']}')."
        ),
    }


@mcp.tool()
async def login_poll(session_id: str, wait_seconds: int = 50) -> dict:
    """Finish device-flow login once the user has authorized. Polls for up to
    `wait_seconds`, caching the session JWT on success. Returns
    {status: "authorized", github_id, github_login} or {status: "pending"} —
    if pending, the user hasn't authorized yet; call this again."""
    global _token
    interval = _device_intervals.get(session_id, 5)
    deadline = time.monotonic() + max(0, wait_seconds)
    async with httpx.AsyncClient(timeout=15.0) as client:
        while True:
            resp = await client.post(
                f"{GATEWAY_URL}/auth/github/device/poll", json={"session_id": session_id}
            )
            if resp.status_code == 200:
                data = resp.json()
                _token = data["access_token"]
                _device_intervals.pop(session_id, None)
                return {
                    "status": "authorized",
                    "github_id": data["github_id"],
                    "github_login": data["github_login"],
                }
            if resp.status_code == 202:
                body = resp.json()
                if body.get("status") == "slow_down":
                    interval = int(body.get("interval", interval + 5))
                if time.monotonic() >= deadline:
                    return {
                        "status": "pending",
                        "session_id": session_id,
                        "hint": "user hasn't authorized yet; call login_poll again",
                    }
                await asyncio.sleep(interval)
                continue
            if resp.status_code == 410:
                _device_intervals.pop(session_id, None)
                raise RuntimeError("device code expired; call login() again for a fresh code")
            if resp.status_code == 403:
                _device_intervals.pop(session_id, None)
                raise RuntimeError("authorization denied by the user")
            resp.raise_for_status()
            raise RuntimeError(f"unexpected poll status {resp.status_code}: {resp.text}")


@mcp.tool()
async def login_with_token(github_token: str) -> dict:
    """Dev/CI fallback: log in with a pre-issued GitHub token (works only if the
    gateway has raw-token login enabled). Prefer `login()` (device flow)."""
    global _token
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(f"{GATEWAY_URL}/auth/login", json={"github_token": github_token})
        resp.raise_for_status()
        data = resp.json()
    _token = data["access_token"]
    return {"github_id": data["github_id"], "github_login": data["github_login"]}


@mcp.tool()
async def register_identity(address: str, metadata: dict | None = None) -> dict:
    """Register/refresh this agent's on-chain identity record (ai:gh:<github_id>).

    `address` is the agent's Emercoin address, later used for signature login.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{GATEWAY_URL}/nvs/identity",
            headers=_auth_headers(),
            json={"address": address, "metadata": metadata or {}},
        )
        resp.raise_for_status()
        return resp.json()


@mcp.tool()
async def store_memory(content_hash: str, metadata: dict | None = None) -> dict:
    """Store a research/memory hash on-chain (ai:gh:<github_id>:mem:<hash>).

    Keep the body off-chain (e.g. IPFS); only its hash + metadata go on-chain.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{GATEWAY_URL}/nvs/mem",
            headers=_auth_headers(),
            json={"content_hash": content_hash, "metadata": metadata or {}},
        )
        resp.raise_for_status()
        return resp.json()


@mcp.tool()
async def store_memory_batch(records: list[dict]) -> dict:
    """Store many memory hashes in ONE atomic on-chain transaction (cheaper and
    atomic vs. calling store_memory repeatedly).

    Each record is {"content_hash": str, "metadata"?: dict}. Returns one txid for
    the whole batch. Counts as len(records) against the per-minute write tier.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{GATEWAY_URL}/nvs/mem/batch",
            headers=_auth_headers(),
            json={"records": records},
        )
        resp.raise_for_status()
        return resp.json()


@mcp.tool()
async def read_record(name: str) -> dict:
    """Read any NVS record by name (e.g. ai:gh:12345 or ai:gh:12345:mem:<hash>)."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{GATEWAY_URL}/nvs/{name}")
        resp.raise_for_status()
        return resp.json()


if __name__ == "__main__":
    mcp.run()
