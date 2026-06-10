"""Gateway settings. Network (regtest/testnet/mainnet) is just the RPC target."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GATEWAY_", env_file=".env", extra="ignore")

    # Node RPC — points at the emc service over the internal docker network.
    rpc_url: str = "http://emc:6662"
    rpc_user: str = "emcrpc"
    rpc_password: str = "emcpass"

    # Auth: self-contained session JWT (no agent registry; we trust GitHub ID).
    jwt_secret: str = "dev-insecure-change-me"
    jwt_ttl_seconds: int = 3600

    # Free tier rate limit (token bucket in Redis, keyed by github_id).
    free_tier_writes_per_min: int = 10
    redis_url: str = "redis://redis:6379/0"

    # NVS record lifetime in days (records expire on Emercoin).
    nvs_default_days: int = 30


settings = Settings()
