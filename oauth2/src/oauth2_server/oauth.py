"""In-memory authorization-code and access-token stores. Same module-global
pattern as mcp-fileserver's admin_auth.py sessions -- fine because Cloud Run
is pinned to --max-instances=1 (see deploy.sh), and losing state on a
restart just means a fresh /oauth/authorize round-trip, no different cost
than a normal token expiry.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass


@dataclass
class AuthCode:
    client_id: str
    redirect_uri: str
    scope: str
    expiry: float


@dataclass
class AccessToken:
    client_id: str
    scope: str
    expiry: float


_auth_codes: dict[str, AuthCode] = {}
_access_tokens: dict[str, AccessToken] = {}


def issue_auth_code(client_id: str, redirect_uri: str, scope: str, ttl_seconds: int) -> str:
    code = secrets.token_urlsafe(24)
    _auth_codes[code] = AuthCode(
        client_id=client_id, redirect_uri=redirect_uri, scope=scope, expiry=time.time() + ttl_seconds
    )
    return code


def consume_auth_code(code: str) -> AuthCode | None:
    """Single-use: popped whether valid or not, so a replay of the same code
    always fails, even within its TTL window."""
    entry = _auth_codes.pop(code, None)
    if entry is None or entry.expiry < time.time():
        return None
    return entry


def issue_access_token(client_id: str, scope: str, ttl_seconds: int) -> str:
    token = secrets.token_urlsafe(32)
    _access_tokens[token] = AccessToken(client_id=client_id, scope=scope, expiry=time.time() + ttl_seconds)
    return token


def verify_access_token(token: str) -> bool:
    entry = _access_tokens.get(token)
    if entry is None:
        return False
    if entry.expiry < time.time():
        _access_tokens.pop(token, None)
        return False
    return True
