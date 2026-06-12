"""Edge settings — the agent-facing IAM layer in front of the node adapter."""
from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EDGE_", env_file=".env", extra="ignore")

    # The node adapter (RPC↔REST). Edge never speaks RPC itself.
    adapter_url: str = "http://adapter:8000"
    # Must match the adapter's ADAPTER_INTERNAL_KEY when that gate is enabled.
    adapter_key: str = ""

    # Public base URL — the OAuth issuer advertised in the MCP /.well-known metadata.
    public_url: str = "https://ai.emercoin.com"

    # Auth: self-contained session JWT (no agent registry; we trust GitHub ID).
    jwt_secret: str = "dev-insecure-change-me"
    jwt_ttl_seconds: int = 3600

    # GitHub OAuth App — identity bootstrap. Device flow needs only the client_id;
    # the web flow also needs the secret + redirect_uri. Scope is empty (we read
    # only the public id+login via GET /user).
    github_client_id: str = ""
    github_client_secret: str = ""
    github_redirect_uri: str = "http://localhost:8000/auth/github/callback"

    # Login surfaces. Device flow is always on. The raw-token /auth/login is a
    # dev/CI shortcut; the browser web flow is opt-in until a public domain exists.
    dev_login_enabled: bool = False
    web_login_enabled: bool = False

    # Free tier rate limit (sliding 60s window in Redis, keyed by github_id).
    free_tier_writes_per_min: int = 10
    redis_url: str = "redis://redis:6379/0"

    # NVS record lifetime in days (records expire on Emercoin).
    nvs_default_days: int = 30

    @model_validator(mode="after")
    def _require_strong_secret(self) -> "Settings":
        # In a real deployment (dev_login disabled) refuse to start on a weak HS256
        # secret — this is what stops the dev secret leaking into prod. Dev keeps
        # the short secret for convenience (it sets EDGE_DEV_LOGIN_ENABLED=true).
        if not self.dev_login_enabled and len(self.jwt_secret.encode()) < 32:
            raise ValueError(
                "EDGE_JWT_SECRET must be >=32 bytes when EDGE_DEV_LOGIN_ENABLED is false"
            )
        return self


settings = Settings()
