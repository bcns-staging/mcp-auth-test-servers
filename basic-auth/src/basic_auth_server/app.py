"""Assembles the root ASGI app: both MCP transports (legacy SSE + Streamable
HTTP) mounted at their default paths, wrapped in Basic Auth. Same shape as
mcp-fileserver/app.py.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from .auth_middleware import BasicAuthMiddleware
from .config import Settings
from .server import build_mcp


async def _status(_request: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


def build_app(settings: Settings) -> Starlette:
    mcp = build_mcp()

    sse_app = mcp.sse_app()
    streamable_app = mcp.streamable_http_app()

    @contextlib.asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncIterator[None]:
        async with mcp.session_manager.run():
            yield

    return Starlette(
        routes=[
            Route("/status", _status),
            *sse_app.routes,
            *streamable_app.routes,
        ],
        lifespan=lifespan,
        middleware=[
            Middleware(
                BasicAuthMiddleware,
                username=settings.test_username,
                password=settings.test_password,
                exempt_paths=frozenset({"/status"}),
            ),
        ],
    )
