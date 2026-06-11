"""Adapter settings. Network (regtest/testnet/mainnet) is just the RPC target."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ADAPTER_", env_file=".env", extra="ignore")

    # Node RPC — points at the emc service over the internal docker network.
    rpc_url: str = "http://emc:6662"
    rpc_user: str = "emcrpc"
    rpc_password: str = "emcpass"

    # NVS record lifetime in days (records expire on Emercoin).
    nvs_default_days: int = 30

    # Shared-secret gate. Empty = open (dev, browse /docs freely). When set, every
    # request must carry `X-Internal-Key: <internal_key>`. Use it when the adapter
    # is reachable beyond a trusted docker network (e.g. wallet at home, edge on a
    # VPS) — there a network barrier alone isn't enough.
    internal_key: str = ""


settings = Settings()
