"""Edge settings — the agent-facing IAM layer in front of the node adapter."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EDGE_", env_file=".env", extra="ignore")

    # The node adapter (RPC↔REST). Edge never speaks RPC itself.
    adapter_url: str = "http://adapter:8000"
    # Must match the adapter's ADAPTER_INTERNAL_KEY when that gate is enabled.
    adapter_key: str = ""

    # Auth: self-contained session JWT (no agent registry; we trust GitHub ID).
    jwt_secret: str = "dev-insecure-change-me"
    jwt_ttl_seconds: int = 3600

    # Free tier rate limit (sliding 60s window in Redis, keyed by github_id).
    free_tier_writes_per_min: int = 10
    redis_url: str = "redis://redis:6379/0"

    # NVS record lifetime in days (records expire on Emercoin).
    nvs_default_days: int = 30


settings = Settings()
