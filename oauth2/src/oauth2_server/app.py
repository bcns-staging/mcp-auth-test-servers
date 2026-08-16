from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from .auth_middleware import OAuthBearerMiddleware
from .config import Settings
from .routes import build_oauth_routes
from .server import build_mcp


async def _status(_request: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


def build_app(settings: Settings) -> Starlette:
    mcp = build_mcp()

    sse_app = mcp.sse_app()
    streamable_app = mcp.streamable_http_app()
    oauth_routes = build_oauth_routes(settings)

    @contextlib.asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncIterator[None]:
        async with mcp.session_manager.run():
            yield

    return Starlette(
        routes=[
            Route("/status", _status),
            *oauth_routes,
            *sse_app.routes,
            *streamable_app.routes,
        ],
        lifespan=lifespan,
        middleware=[
            # allow_origins=["*"]: this server exists specifically so an
            # unknown platform can test its OAuth client against it, so
            # there's no fixed origin to allow-list ahead of time -- unlike
            # mcp-fileserver's real CORS config, which does know its exact
            # caller. Needed because some MCP platforms run the whole
            # authorization-code exchange client-side in the browser, which
            # means a CORS preflight (OPTIONS) hits /oauth/token before the
            # real POST -- without this, Starlette's routing 405s that
            # OPTIONS outright since the route only declares POST.
            Middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_methods=["*"],
                allow_headers=["*"],
            ),
            Middleware(
                OAuthBearerMiddleware,
                # /oauth/* issues the tokens this middleware checks, and
                # .well-known/* is public discovery metadata -- neither can
                # require the very credential they're handing out.
                exempt_paths=frozenset({"/status", "/oauth/authorize", "/oauth/token", "/.well-known/oauth-authorization-server"}),
            ),
        ],
    )
