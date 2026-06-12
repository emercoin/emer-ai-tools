"""OAuth 2.1 Authorization Server for the remote MCP endpoint.

Implements the MCP authorization spec so an MCP client (Claude, etc.) signs the
user in automatically — Dynamic Client Registration + authorization-code + PKCE +
refresh — instead of the user pasting a token. User authentication is delegated to
**GitHub** (we already are a GitHub OAuth app); the issued access token is our own
session JWT, so the SAME token also authorizes the REST API and the manual-bearer
path (backwards compatible with the pasted-token setup).

The GitHub consent redirects back to the existing `/auth/github/callback` route,
which hands MCP-flow states here (so no extra callback URL in the GitHub app).

Storage is in-memory (single edge instance). A redeploy clears registered clients,
pending codes and refresh tokens — clients re-register and re-auth automatically.
Moving this to Redis is a hardening TODO.
"""
from __future__ import annotations

import secrets
import time

import jwt
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


class GitHubOAuthProvider(
    OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]
):
    def __init__(self) -> None:
        self._github: GitHubOAuth | None = None
        self.clients: dict[str, OAuthClientInformationFull] = {}
        self.auth_codes: dict[str, AuthorizationCode] = {}
        self.state_map: dict[str, dict] = {}
        self.refresh: dict[str, dict] = {}
        self._login: dict[str, str] = {}  # github_id(str) -> login

    def configure(self, github: GitHubOAuth) -> None:
        self._github = github

    # --- DCR -------------------------------------------------------------
    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self.clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        self.clients[client_info.client_id] = client_info

    # --- authorization: delegate user auth to GitHub ---------------------
    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        state = params.state or secrets.token_hex(16)
        self.state_map[state] = {
            "redirect_uri": str(params.redirect_uri),
            "code_challenge": params.code_challenge,
            "redirect_uri_provided_explicitly": params.redirect_uri_provided_explicitly,
            "client_id": client.client_id,
            "resource": params.resource,
        }
        # Send the user to GitHub's consent screen. GitHub returns to the shared
        # /auth/github/callback, which routes MCP states back to complete_github().
        return self._github.authorize_url(state)

    def owns_state(self, state: str) -> bool:
        return state in self.state_map

    async def complete_github(self, code: str, state: str) -> str:
        """Called by /auth/github/callback for MCP-flow states. Returns the
        redirect URI back to the MCP client carrying our authorization code."""
        data = self.state_map.pop(state)
        token = await self._github.exchange_code(code)
        access = token.get("access_token")
        if not access:
            raise ValueError(f"github code exchange failed: {token.get('error', 'unknown')}")
        gh_id, gh_login = await self._github.fetch_user(access)
        self._login[str(gh_id)] = gh_login
        new_code = f"mcp_{secrets.token_hex(16)}"
        self.auth_codes[new_code] = AuthorizationCode(
            code=new_code,
            client_id=data["client_id"],
            redirect_uri=AnyHttpUrl(data["redirect_uri"]),
            redirect_uri_provided_explicitly=data["redirect_uri_provided_explicitly"],
            expires_at=time.time() + 300,
            scopes=[MCP_SCOPE],
            code_challenge=data["code_challenge"],
            resource=data["resource"],
            subject=str(gh_id),
        )
        return construct_redirect_uri(data["redirect_uri"], code=new_code, state=state)

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        return self.auth_codes.get(authorization_code)

    # --- token issuance: access token = our session JWT ------------------
    def _issue(self, gh_id: int, gh_login: str, scopes: list[str], client_id: str) -> OAuthToken:
        access = issue_jwt(gh_id, gh_login)
        refresh = f"rt_{secrets.token_hex(32)}"
        self.refresh[refresh] = {
            "github_id": gh_id,
            "login": gh_login,
            "client_id": client_id,
            "scopes": scopes,
        }
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
        if authorization_code.code not in self.auth_codes:
            raise ValueError("invalid authorization code")
        gh_id = int(authorization_code.subject)
        gh_login = self._login.get(authorization_code.subject, "")
        del self.auth_codes[authorization_code.code]
        return self._issue(gh_id, gh_login, authorization_code.scopes, client.client_id)

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
        data = self.refresh.get(refresh_token)
        if data is None or data["client_id"] != client.client_id:
            return None
        return RefreshToken(token=refresh_token, client_id=client.client_id, scopes=data["scopes"], expires_at=None)

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        data = self.refresh.pop(refresh_token.token, None)
        if data is None:
            raise ValueError("invalid refresh token")
        use_scopes = scopes or data["scopes"]
        return self._issue(data["github_id"], data["login"], use_scopes, client.client_id)

    async def revoke_token(self, token: str, token_type_hint: str | None = None) -> None:
        self.refresh.pop(token, None)
