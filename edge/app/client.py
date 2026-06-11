"""HTTP client for the node adapter.

The edge speaks plain REST to the adapter and never touches RPC. Adapter errors
are surfaced as `AdapterError` (status + detail) so edge routes can either let
them propagate (a global handler maps them to HTTP responses) or special-case
them (e.g. a 404 identity lookup during agent-login).
"""
from __future__ import annotations

from typing import Any

import httpx


class AdapterError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"adapter {status_code}: {detail}")


class AdapterClient:
    def __init__(self, base_url: str, internal_key: str = "", timeout: float = 30.0) -> None:
        headers = {"X-Internal-Key": internal_key} if internal_key else {}
        self._client = httpx.AsyncClient(base_url=base_url.rstrip("/"), headers=headers, timeout=timeout)

    async def _request(self, method: str, path: str, **kw: Any) -> Any:
        try:
            resp = await self._client.request(method, path, **kw)
        except httpx.HTTPError as exc:
            raise AdapterError(502, f"adapter unreachable: {exc}")
        if resp.status_code >= 400:
            detail = resp.json().get("detail") if "application/json" in resp.headers.get("content-type", "") else resp.text
            raise AdapterError(resp.status_code, detail or resp.reason_phrase)
        return resp.json()

    # node passthrough
    async def info(self) -> dict:
        return await self._request("GET", "/info")

    async def status(self) -> dict:
        return await self._request("GET", "/status")

    async def state(self) -> dict:
        return await self._request("GET", "/")

    # nvs
    async def write(self, name: str, value: Any, days: int) -> dict:
        return await self._request("POST", "/nvs", json={"name": name, "value": value, "days": days})

    async def write_batch(self, operations: list[dict]) -> dict:
        return await self._request("POST", "/nvs/batch", json={"operations": operations})

    async def read(self, name: str) -> dict:
        return await self._request("GET", f"/nvs/{name}")

    async def history(self, name: str) -> dict:
        return await self._request("GET", f"/history/{name}")

    async def address_names(self, address: str) -> dict:
        return await self._request("GET", f"/addresses/{address}/names")

    # crypto
    async def verify(self, address: str, signature: str, message: str) -> bool:
        res = await self._request(
            "POST", "/verify",
            json={"address": address, "signature": signature, "message": message},
        )
        return bool(res.get("valid"))

    async def get_identity(self, name: str) -> dict:
        """Read an identity record, returning {} if it doesn't exist yet."""
        try:
            return await self.read(name)
        except AdapterError as exc:
            if exc.status_code == 404:
                return {}
            raise

    async def aclose(self) -> None:
        await self._client.aclose()
