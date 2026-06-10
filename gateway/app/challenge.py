"""Short-lived challenge nonces for agent signature login (stored in Redis)."""
from __future__ import annotations

import secrets

import redis.asyncio as redis


class ChallengeStore:
    def __init__(self, url: str, ttl_seconds: int = 300) -> None:
        self._redis = redis.from_url(url, decode_responses=True)
        self._ttl = ttl_seconds

    async def issue(self, subject: str) -> str:
        nonce = secrets.token_hex(16)
        await self._redis.set(f"chal:{subject}", nonce, ex=self._ttl)
        return nonce

    async def consume(self, subject: str) -> str | None:
        """Atomically fetch and delete the nonce (single use)."""
        return await self._redis.getdel(f"chal:{subject}")

    async def aclose(self) -> None:
        await self._redis.aclose()
