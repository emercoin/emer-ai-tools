"""Ephemeral OAuth state in Redis (alongside login nonces + rate-limit windows).

- Device flow: an opaque `session_id` -> GitHub `device_code`. We keep the
  device_code server-side and hand the client only the session_id to poll with.
- Web flow: a single-use `state` value to defend the callback against CSRF.
"""
from __future__ import annotations

import secrets

import redis.asyncio as redis


class OAuthStateStore:
    def __init__(self, url: str) -> None:
        self._redis = redis.from_url(url, decode_responses=True)

    # --- device flow ---
    async def put_device(self, device_code: str, ttl_seconds: int) -> str:
        """Store the device_code under a fresh session_id (TTL = GitHub expires_in)."""
        session_id = secrets.token_urlsafe(16)
        await self._redis.set(f"ghdev:{session_id}", device_code, ex=ttl_seconds)
        return session_id

    async def get_device(self, session_id: str) -> str | None:
        return await self._redis.get(f"ghdev:{session_id}")

    async def drop_device(self, session_id: str) -> None:
        await self._redis.delete(f"ghdev:{session_id}")

    # --- web flow ---
    async def issue_state(self, ttl_seconds: int = 600) -> str:
        state = secrets.token_urlsafe(24)
        await self._redis.set(f"ghstate:{state}", "1", ex=ttl_seconds)
        return state

    async def consume_state(self, state: str) -> bool:
        """Atomically validate + delete a state (single use)."""
        return bool(await self._redis.getdel(f"ghstate:{state}"))

    async def aclose(self) -> None:
        await self._redis.aclose()
