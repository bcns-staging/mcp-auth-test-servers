"""The OAuth 2.0 authorization-code flow endpoints: /oauth/authorize,
/oauth/token, and a .well-known/oauth-authorization-server metadata document
(RFC 8414) so a platform that supports discovery can auto-fill its
Authorization URL / Token URL fields.

Deliberately NOT a real user-facing authorization server: /oauth/authorize
auto-approves immediately (no login/consent screen) and trusts the caller's
redirect_uri as given rather than checking it against a pre-registered
allowlist. Both are real deviations from a production-grade OAuth server,
acceptable only because this service exists purely to prove an MCP client's
OAuth flow implementation works -- nothing behind the issued tokens is real
or sensitive.
"""

from __future__ import annotations

import base64
import binascii
import hmac

from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse
from starlette.routing import Route

from . import oauth
from .config import Settings


def build_oauth_routes(settings: Settings) -> list[Route]:
    async def authorize(request: Request) -> RedirectResponse | JSONResponse:
        params = request.query_params
        response_type = params.get("response_type")
        client_id = params.get("client_id", "")
        redirect_uri = params.get("redirect_uri")
        state = params.get("state", "")
        scope = params.get("scope", "")

        if response_type != "code":
            return JSONResponse({"error": "unsupported_response_type"}, status_code=400)
        if not redirect_uri:
            return JSONResponse(
                {"error": "invalid_request", "error_description": "redirect_uri is required"}, status_code=400
            )
        if not hmac.compare_digest(client_id, settings.test_client_id):
            return JSONResponse({"error": "unauthorized_client"}, status_code=400)

        code = oauth.issue_auth_code(client_id, redirect_uri, scope, settings.code_ttl_seconds)
        separator = "&" if "?" in redirect_uri else "?"
        location = f"{redirect_uri}{separator}code={code}"
        if state:
            location += f"&state={state}"
        return RedirectResponse(location, status_code=302)

    async def token(request: Request) -> JSONResponse:
        form = await request.form()
        grant_type = form.get("grant_type")
        code = str(form.get("code", ""))
        client_id = str(form.get("client_id", ""))
        client_secret = str(form.get("client_secret", ""))

        # RFC 6749 allows client credentials via HTTP Basic auth instead of
        # the body -- support both, since platforms implement this
        # differently and we don't control which one any given caller uses.
        auth_header = request.headers.get("authorization", "")
        if not client_id and auth_header.startswith("Basic "):
            try:
                decoded = base64.b64decode(auth_header[len("Basic ") :]).decode("utf-8")
                client_id, _, client_secret = decoded.partition(":")
            except (binascii.Error, UnicodeDecodeError):
                pass

        if grant_type != "authorization_code":
            return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)

        client_ok = hmac.compare_digest(client_id, settings.test_client_id) and hmac.compare_digest(
            client_secret, settings.test_client_secret
        )
        if not client_ok:
            return JSONResponse({"error": "invalid_client"}, status_code=401)

        entry = oauth.consume_auth_code(code)
        if entry is None or entry.client_id != client_id:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)

        access_token = oauth.issue_access_token(client_id, entry.scope, settings.token_ttl_seconds)
        return JSONResponse(
            {
                "access_token": access_token,
                "token_type": "Bearer",
                "expires_in": settings.token_ttl_seconds,
                "scope": entry.scope,
            }
        )

    async def well_known(request: Request) -> JSONResponse:
        base = str(request.base_url).rstrip("/")
        return JSONResponse(
            {
                "issuer": base,
                "authorization_endpoint": f"{base}/oauth/authorize",
                "token_endpoint": f"{base}/oauth/token",
                "response_types_supported": ["code"],
                "grant_types_supported": ["authorization_code"],
                "token_endpoint_auth_methods_supported": ["client_secret_post", "client_secret_basic"],
            }
        )

    return [
        Route("/oauth/authorize", authorize, methods=["GET"]),
        Route("/oauth/token", token, methods=["POST"]),
        Route("/.well-known/oauth-authorization-server", well_known, methods=["GET"]),
    ]
