"""Bearer auth for the MCP transport routes, validated against tokens this
server itself issued via /oauth/token -- not a fixed shared secret like
mcp-fileserver's BearerAuthMiddleware. Raw ASGI middleware for the same SSE-
streaming-compatibility reason documented in the sibling basic-auth repo.
"""

from __future__ import annotations

import json

from starlette.types import ASGIApp, Receive, Scope, Send

from . import oauth


class OAuthBearerMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        exempt_paths: frozenset[str] = frozenset(),
        exempt_prefixes: tuple[str, ...] = (),
    ) -> None:
        self.app = app
        self.exempt_paths = exempt_paths
        self.exempt_prefixes = exempt_prefixes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if (
            scope["type"] != "http"
            or path in self.exempt_paths
            or path.startswith(self.exempt_prefixes)
        ):
            await self.app(scope, receive, send)
            return

        headers = dict(scope["headers"])
        supplied = headers.get(b"authorization", b"").decode("latin-1")
        prefix = "Bearer "
        if not supplied.startswith(prefix) or not oauth.verify_access_token(supplied[len(prefix) :]):
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
