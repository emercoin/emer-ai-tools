"""GitHub OAuth App client — identity bootstrap for the edge.

Two web standards, same endpoints, so one client serves both:
  - Device Flow  (headless: CLI / MCP / agents) — no secret, no callback.
  - Authorization Code Flow (browser / future site) — secret + redirect_uri.

We request an empty scope: `GET /user` returns the numeric id + login with no
permissions, which is all the identity we need.
"""
from __future__ import annotations

from urllib.parse import urlencode

import httpx

DEVICE_CODE_URL = "https://github.com/login/device/code"
ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
USER_API = "https://api.github.com/user"
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"


class GitHubOAuth:
    def __init__(
        self, client_id: str, client_secret: str, redirect_uri: str, timeout: float = 10.0
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        # Accept: application/json -> token endpoints answer JSON, not urlencoded.
        self._client = httpx.AsyncClient(timeout=timeout, headers={"Accept": "application/json"})

    async def device_code(self) -> dict:
        """Begin device flow: returns user_code, verification_uri, device_code, interval."""
        resp = await self._client.post(
            DEVICE_CODE_URL, data={"client_id": self.client_id, "scope": ""}
        )
        resp.raise_for_status()
        return resp.json()

    async def poll_token(self, device_code: str) -> dict:
        """Poll for the device-flow token. Returns either {access_token,...} or
        {error: authorization_pending | slow_down | expired_token | access_denied}."""
        resp = await self._client.post(
            ACCESS_TOKEN_URL,
            data={
                "client_id": self.client_id,
                "device_code": device_code,
                "grant_type": DEVICE_GRANT,
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def exchange_code(self, code: str) -> dict:
        """Web flow: exchange an authorization code for an access token (needs secret)."""
        resp = await self._client.post(
            ACCESS_TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "redirect_uri": self.redirect_uri,
            },
        )
        resp.raise_for_status()
        return resp.json()

    def authorize_url(self, state: str) -> str:
        """Web flow: the GitHub consent URL to redirect the browser to."""
        query = urlencode(
            {
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "state": state,
                "scope": "",
            }
        )
        return f"{AUTHORIZE_URL}?{query}"

    async def fetch_user(self, access_token: str) -> tuple[int, str]:
        """Resolve an access token to (github_id, login)."""
        resp = await self._client.get(
            USER_API,
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"},
        )
        resp.raise_for_status()
        data = resp.json()
        return int(data["id"]), data["login"]

    async def aclose(self) -> None:
        await self._client.aclose()
