"""MCP adapter for the Emercoin Agent Gateway.

A thin MCP server that exposes the gateway's HTTP API as tools, so an AI agent
can use the Emercoin chain as its identity + memory layer directly. The gateway
remains the canonical surface and authorization boundary; this is just a client.

Config (env):
  GATEWAY_URL  base URL of the gateway (default http://gateway:8000)
  GATEWAY_JWT  optional pre-issued session token; otherwise call the `login` tool

Run: `python server.py` (stdio transport — the agent's MCP client launches it).
"""
from __future__ import annotations

import os

import httpx
from mcp.server.fastmcp import FastMCP

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://gateway:8000").rstrip("/")

mcp = FastMCP("emercoin-agent")

# Session token cached across tool calls (set by `login`, or seeded from env).
_token: str | None = os.environ.get("GATEWAY_JWT")


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
async def login(github_token: str) -> dict:
    """Authenticate with a GitHub token; caches the session JWT for later tools."""
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
async def read_record(name: str) -> dict:
    """Read any NVS record by name (e.g. ai:gh:12345 or ai:gh:12345:mem:<hash>)."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{GATEWAY_URL}/nvs/{name}")
        resp.raise_for_status()
        return resp.json()


if __name__ == "__main__":
    mcp.run()
