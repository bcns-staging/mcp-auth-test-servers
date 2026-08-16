"""HTTP Basic auth, enforced before any MCP logic runs.

Raw ASGI middleware, not Starlette's BaseHTTPMiddleware -- BaseHTTPMiddleware
buffers the whole response through an internal stream, which breaks long-lived
streaming responses like SSE. A raw ASGI middleware forwards the three ASGI
callables through unchanged once auth passes, with zero interference with
streaming. Same pattern mcp-fileserver's BearerAuthMiddleware uses.
"""

from __future__ import annotations

import base64
import binascii
import hmac
import json

from starlette.types import ASGIApp, Receive, Scope, Send


class BasicAuthMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        username: str,
        password: str,
        exempt_paths: frozenset[str] = frozenset(),
    ) -> None:
        self.app = app
        self.username = username
        self.password = password
        self.exempt_paths = exempt_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] != "http" or path in self.exempt_paths:
            await self.app(scope, receive, send)
            return

        headers = dict(scope["headers"])
        supplied = headers.get(b"authorization", b"").decode("latin-1")
        prefix = "Basic "
        if not supplied.startswith(prefix):
            await _unauthorized(send)
            return

        try:
            decoded = base64.b64decode(supplied[len(prefix) :]).decode("utf-8")
            supplied_user, _, supplied_pass = decoded.partition(":")
        except (binascii.Error, UnicodeDecodeError):
            await _unauthorized(send)
            return

        user_ok = hmac.compare_digest(supplied_user, self.username)
        pass_ok = hmac.compare_digest(supplied_pass, self.password)
        if not (user_ok and pass_ok):
            await _unauthorized(send)
            return

        await self.app(scope, receive, send)


async def _unauthorized(send: Send) -> None:
    body = json.dumps({"error": "unauthorized"}).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"www-authenticate", b'Basic realm="mcp-test"'),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
