"""Rate limiting — the only state the gateway keeps (ephemeral, not a registry).

Fixed 60s window counter in Redis, keyed by github_id. Free tier = N writes/min.
"""
from __future__ import annotations

import time

import redis.asyncio as redis
from fastapi import HTTPException


class RateLimiter:
    def __init__(self, url: str) -> None:
        self._redis = redis.from_url(url, decode_responses=True)

    async def check_and_incr(self, github_id: int, limit: int, n: int = 1) -> None:
        """Count `n` writes against the per-minute window (n>1 for batch writes)."""
        window = int(time.time() // 60)
        key = f"rl:nvs:{github_id}:{window}"
        count = await self._redis.incrby(key, n)
        if count == n:
            await self._redis.expire(key, 60)
        if count > limit:
            raise HTTPException(
                status_code=429,
                detail=f"rate limit exceeded: {limit} NVS writes/min on this tier",
            )

    async def ping(self) -> bool:
        return await self._redis.ping()

    async def aclose(self) -> None:
        await self._redis.aclose()
