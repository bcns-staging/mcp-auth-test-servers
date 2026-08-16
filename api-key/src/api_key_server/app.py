from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from .auth_middleware import ApiKeyAuthMiddleware
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
                ApiKeyAuthMiddleware,
                api_key=settings.test_api_key,
                header_name=settings.header_name,
                exempt_paths=frozenset({"/status"}),
            ),
        ],
    )
