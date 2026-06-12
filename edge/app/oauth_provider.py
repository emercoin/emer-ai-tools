"""OAuth 2.1 Authorization Server for the remote MCP endpoint.

Implements the MCP authorization spec so an MCP client (Claude, etc.) signs the
user in automatically — Dynamic Client Registration + authorization-code + PKCE +
refresh — instead of the user pasting a token. User authentication is delegated to
**GitHub** (we already are a GitHub OAuth app); the issued access token is our own
session JWT, so the SAME token also authorizes the REST API and the manual-bearer
path (backwards compatible with the pasted-token setup).

The GitHub consent redirects back to the existing `/auth/github/callback` route,
which hands MCP-flow states here (so no extra callback URL in the GitHub app).

State is kept in **Redis** so registered clients, pending codes and refresh tokens
survive an edge redeploy (clients stay registered, users stay signed in).
"""
from __future__ import annotations

import json
import secrets
import time

import jwt
import redis.asyncio as redis
from pydantic import AnyHttpUrl

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from .auth import issue_jwt
from .config import settings
from .github import GitHubOAuth

MCP_SCOPE = "agent"

_CLIENT_TTL = 90 * 86400   # registered clients persist ~90 days
_STATE_TTL = 600           # pending authorize state: 10 min
_CODE_TTL = 300            # authorization code: 5 min
_REFRESH_TTL = 30 * 86400  # refresh token: 30 days


class GitHubOAuthProvider(
    OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]
):
    def __init__(self) -> None:
        self._github: GitHubOAuth | None = None
        self._redis: redis.Redis | None = None

    def configure(self, github: GitHubOAuth, redis_url: str) -> None:
        self._github = github
        self._redis = redis.from_url(redis_url, decode_responses=True)

    async def aclose(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()

    # --- DCR -------------------------------------------------------------
    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        raw = await self._redis.get(f"oauth:client:{client_id}")
        return OAuthClientInformationFull.model_validate_json(raw) if raw else None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        await self._redis.set(
            f"oauth:client:{client_info.client_id}", client_info.model_dump_json(), ex=_CLIENT_TTL
        )

    # --- authorization: delegate user auth to GitHub ---------------------
    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        state = params.state or secrets.token_hex(16)
        await self._redis.set(
            f"oauth:state:{state}",
            json.dumps(
                {
                    "redirect_uri": str(params.redirect_uri),
                    "code_challenge": params.code_challenge,
                    "redirect_uri_provided_explicitly": params.redirect_uri_provided_explicitly,
                    "client_id": client.client_id,
                    "resource": params.resource,
                }
            ),
            ex=_STATE_TTL,
        )
        # GitHub returns to the shared /auth/github/callback, which routes MCP
        # states back to complete_github().
        return self._github.authorize_url(state)

    async def owns_state(self, state: str) -> bool:
        return bool(await self._redis.exists(f"oauth:state:{state}"))

    async def complete_github(self, code: str, state: str) -> str:
        """Called by /auth/github/callback for MCP-flow states. Returns the
        redirect URI back to the MCP client carrying our authorization code."""
        raw = await self._redis.getdel(f"oauth:state:{state}")
        if not raw:
            raise ValueError("invalid or expired state")
        data = json.loads(raw)
        token = await self._github.exchange_code(code)
        access = token.get("access_token")
        if not access:
            raise ValueError(f"github code exchange failed: {token.get('error', 'unknown')}")
        gh_id, gh_login = await self._github.fetch_user(access)
        new_code = f"mcp_{secrets.token_hex(16)}"
        ac = AuthorizationCode(
            code=new_code,
            client_id=data["client_id"],
            redirect_uri=AnyHttpUrl(data["redirect_uri"]),
            redirect_uri_provided_explicitly=data["redirect_uri_provided_explicitly"],
            expires_at=time.time() + _CODE_TTL,
            scopes=[MCP_SCOPE],
            code_challenge=data["code_challenge"],
            resource=data["resource"],
            subject=str(gh_id),
        )
        await self._redis.set(
            f"oauth:code:{new_code}",
            json.dumps({"ac": ac.model_dump(mode="json"), "login": gh_login}),
            ex=_CODE_TTL,
        )
        return construct_redirect_uri(data["redirect_uri"], code=new_code, state=state)

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        raw = await self._redis.get(f"oauth:code:{authorization_code}")
        if not raw:
            return None
        return AuthorizationCode.model_validate(json.loads(raw)["ac"])

    # --- token issuance: access token = our session JWT ------------------
    async def _issue(self, gh_id: int, gh_login: str, scopes: list[str], client_id: str) -> OAuthToken:
        access = issue_jwt(gh_id, gh_login)
        refresh = f"rt_{secrets.token_hex(32)}"
        await self._redis.set(
            f"oauth:rt:{refresh}",
            json.dumps({"github_id": gh_id, "login": gh_login, "client_id": client_id, "scopes": scopes}),
            ex=_REFRESH_TTL,
        )
        return OAuthToken(
            access_token=access,
            token_type="Bearer",
            expires_in=settings.jwt_ttl_seconds,
            scope=" ".join(scopes),
            refresh_token=refresh,
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        raw = await self._redis.getdel(f"oauth:code:{authorization_code.code}")
        if not raw:
            raise ValueError("invalid authorization code")
        stored = json.loads(raw)
        gh_id = int(authorization_code.subject)
        return await self._issue(gh_id, stored.get("login", ""), authorization_code.scopes, client.client_id)

    async def load_access_token(self, token: str) -> AccessToken | None:
        try:
            payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        except jwt.PyJWTError:
            return None
        return AccessToken(
            token=token,
            client_id="",
            scopes=[MCP_SCOPE],
            expires_at=payload.get("exp"),
            subject=str(payload["sub"]),
            claims={"login": payload.get("login", ""), "tariff": payload.get("tariff", "free")},
        )

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        raw = await self._redis.get(f"oauth:rt:{refresh_token}")
        if not raw:
            return None
        data = json.loads(raw)
        if data["client_id"] != client.client_id:
            return None
        return RefreshToken(token=refresh_token, client_id=client.client_id, scopes=data["scopes"], expires_at=None)

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        raw = await self._redis.getdel(f"oauth:rt:{refresh_token.token}")
        if not raw:
            raise ValueError("invalid refresh token")
        data = json.loads(raw)
        use_scopes = scopes or data["scopes"]
        return await self._issue(data["github_id"], data["login"], use_scopes, client.client_id)

    async def revoke_token(self, token: str, token_type_hint: str | None = None) -> None:
        await self._redis.delete(f"oauth:rt:{token}")
