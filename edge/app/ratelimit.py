"""Rate limiting — the only state the edge keeps (ephemeral, not a registry).

Sliding 60s window in Redis, keyed by github_id. Free tier = N writes/min.

A fixed calendar-minute counter is trivially burst-able across the boundary
(N writes at :59 + N at :00 = 2N in two seconds), so we keep a sorted set of
write timestamps and count only those within the trailing `window` seconds. The
check + insert runs as one atomic Lua script so concurrent writes can't race
past the limit.
"""
from __future__ import annotations

import secrets
import time

import redis.asyncio as redis
from fastapi import HTTPException

# KEYS[1]=bucket  ARGV: now, window(s), limit, n, token
# Drops timestamps older than the window, counts what's left, and only admits the
# `n` new writes if they fit under `limit`. Returns the post-write count, or -1 if
# the request would exceed the limit (nothing is inserted in that case).
_SLIDING_WINDOW = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local n = tonumber(ARGV[4])
local token = ARGV[5]
redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
local count = redis.call('ZCARD', key)
if count + n > limit then
  return -1
end
for i = 1, n do
  redis.call('ZADD', key, now, token .. ':' .. i)
end
redis.call('PEXPIRE', key, math.ceil(window * 1000))
return count + n
"""


class RateLimiter:
    def __init__(self, url: str, window_seconds: int = 60) -> None:
        self._redis = redis.from_url(url, decode_responses=True)
        self._window = window_seconds
        self._script = self._redis.register_script(_SLIDING_WINDOW)

    async def check_and_incr(self, github_id: int, limit: int, n: int = 1) -> None:
        """Admit `n` writes against the trailing per-minute window (n>1 for batches)."""
        token = secrets.token_hex(8)
        result = await self._script(
            keys=[f"rl:nvs:{github_id}"],
            args=[time.time(), self._window, limit, n, token],
        )
        if int(result) < 0:
            raise HTTPException(
                status_code=429,
                detail=f"rate limit exceeded: {limit} NVS writes/min on this tier",
            )

    async def ping(self) -> bool:
        return await self._redis.ping()

    async def aclose(self) -> None:
        await self._redis.aclose()
