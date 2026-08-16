"""API key auth via a configurable custom header, enforced before any MCP
logic runs. Raw ASGI middleware -- see basic-auth/auth_middleware.py's
docstring in the sibling repo for why (SSE streaming compatibility).
"""

from __future__ import annotations

import hmac
import json

from starlette.types import ASGIApp, Receive, Scope, Send


class ApiKeyAuthMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        api_key: str,
        header_name: str,
        exempt_paths: frozenset[str] = frozenset(),
    ) -> None:
        self.app = app
        self.api_key = api_key
        # ASGI header names arrive lowercased; header_name is normalized to
        # lowercase by config.load_settings() so the lookup below matches
        # regardless of how the caller cased it on the wire.
        self.header_name = header_name.encode("latin-1")
        self.exempt_paths = exempt_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] != "http" or path in self.exempt_paths:
            await self.app(scope, receive, send)
            return

        headers = dict(scope["headers"])
        supplied = headers.get(self.header_name, b"").decode("latin-1")
        if not supplied or not hmac.compare_digest(supplied, self.api_key):
            await _unauthorized(send)
            return

        await self.app(scope, receive, send)


async def _unauthorized(send: Send) -> None:
    body = json.dumps({"error": "unauthorized"}).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send({"type": "http.response.body", "body": body})
