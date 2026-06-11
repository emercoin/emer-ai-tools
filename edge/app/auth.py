"""Authn/authz for the edge.

GitHub identity is the trust anchor. We do NOT keep an agent registry — a valid
GitHub identity is exchanged for a self-contained session JWT carrying the
github_id + tariff. Every protected route just verifies the JWT signature.

Dev login (this module): caller presents a GitHub token, we resolve it to a
GitHub user via the API. The agent-signature login path is in `main`.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import httpx
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings

GITHUB_USER_API = "https://api.github.com/user"


@dataclass
class Principal:
    github_id: int
    github_login: str
    tariff: str


async def resolve_github_token(token: str) -> tuple[int, str]:
    """Verify a GitHub token and return (id, login). Raises 401 if invalid."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            GITHUB_USER_API,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="invalid GitHub token")
    data = resp.json()
    return int(data["id"]), data["login"]


def issue_jwt(github_id: int, github_login: str, tariff: str = "free") -> str:
    now = int(time.time())
    payload = {
        "sub": str(github_id),
        "login": github_login,
        "tariff": tariff,
        "iat": now,
        "exp": now + settings.jwt_ttl_seconds,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


_bearer = HTTPBearer(auto_error=True)


def current_principal(creds: HTTPAuthorizationCredentials = Depends(_bearer)) -> Principal:
    try:
        payload = jwt.decode(creds.credentials, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"invalid token: {exc}")
    return Principal(
        github_id=int(payload["sub"]),
        github_login=payload["login"],
        tariff=payload.get("tariff", "free"),
    )
