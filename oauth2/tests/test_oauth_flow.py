import base64
from urllib.parse import parse_qs, urlparse

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from oauth2_server import oauth
from oauth2_server.auth_middleware import OAuthBearerMiddleware
from oauth2_server.config import Settings
from oauth2_server.routes import build_oauth_routes

CLIENT_ID = "test-client"
CLIENT_SECRET = "test-secret"
REDIRECT_URI = "https://platform.example.com/oauth/callback"

SETTINGS = Settings(
    port=8080,
    test_client_id=CLIENT_ID,
    test_client_secret=CLIENT_SECRET,
    code_ttl_seconds=60,
    token_ttl_seconds=3600,
)


async def _protected(_request: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


def _client() -> TestClient:
    """A small stand-in app: the real OAuth routes/middleware from this
    server, but a trivial dummy protected route instead of the real MCP SSE/
    streamable-http apps -- those need FastMCP's session manager wired
    through the ASGI lifespan protocol to behave, which TestClient doesn't
    reliably drive outside a real server process. What's actually under test
    here (the OAuth flow and token validation) doesn't depend on that at
    all, so isolating it avoids the whole class of hang."""
    oauth._auth_codes.clear()
    oauth._access_tokens.clear()
    app = Starlette(
        routes=[
            Route("/protected", _protected),
            Route("/status", _protected),
            *build_oauth_routes(SETTINGS),
        ],
        middleware=[
            Middleware(
                OAuthBearerMiddleware,
                exempt_paths=frozenset(
                    {"/status", "/oauth/authorize", "/oauth/token", "/.well-known/oauth-authorization-server"}
                ),
            ),
        ],
    )
    return TestClient(app)


def _authorize(client: TestClient, **overrides):
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "state": "xyz",
        "scope": "read",
        **overrides,
    }
    return client.get("/oauth/authorize", params=params, follow_redirects=False)


def _extract_code(redirect_url: str) -> str:
    query = parse_qs(urlparse(redirect_url).query)
    return query["code"][0]


def test_authorize_redirects_with_code_and_state():
    resp = _authorize(_client())
    assert resp.status_code == 302
    location = resp.headers["location"]
    assert location.startswith(REDIRECT_URI)
    query = parse_qs(urlparse(location).query)
    assert "code" in query
    assert query["state"] == ["xyz"]


def test_authorize_rejects_wrong_client_id():
    resp = _authorize(_client(), client_id="someone-else")
    assert resp.status_code == 400
    assert resp.json()["error"] == "unauthorized_client"


def test_authorize_rejects_missing_redirect_uri():
    resp = _client().get("/oauth/authorize", params={"response_type": "code", "client_id": CLIENT_ID})
    assert resp.status_code == 400


def test_authorize_rejects_wrong_response_type():
    resp = _authorize(_client(), response_type="token")
    assert resp.status_code == 400
    assert resp.json()["error"] == "unsupported_response_type"


def test_full_flow_code_exchanges_for_working_access_token():
    client = _client()
    code = _extract_code(_authorize(client).headers["location"])

    token_resp = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
    )
    assert token_resp.status_code == 200
    body = token_resp.json()
    assert body["token_type"] == "Bearer"
    access_token = body["access_token"]

    # The issued token must actually work against a protected route.
    protected_resp = client.get("/protected", headers={"Authorization": f"Bearer {access_token}"})
    assert protected_resp.status_code == 200
    assert protected_resp.text == "ok"


def test_token_endpoint_accepts_client_credentials_via_basic_auth():
    client = _client()
    code = _extract_code(_authorize(client).headers["location"])

    basic = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    token_resp = client.post(
        "/oauth/token",
        data={"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI},
        headers={"Authorization": f"Basic {basic}"},
    )
    assert token_resp.status_code == 200
    assert "access_token" in token_resp.json()


def test_code_is_single_use():
    client = _client()
    code = _extract_code(_authorize(client).headers["location"])
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }
    first = client.post("/oauth/token", data=payload)
    assert first.status_code == 200
    second = client.post("/oauth/token", data=payload)
    assert second.status_code == 400
    assert second.json()["error"] == "invalid_grant"


def test_token_endpoint_rejects_wrong_client_secret():
    client = _client()
    code = _extract_code(_authorize(client).headers["location"])
    resp = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": CLIENT_ID,
            "client_secret": "wrong-secret",
        },
    )
    assert resp.status_code == 401
    assert resp.json()["error"] == "invalid_client"


def test_token_endpoint_rejects_unknown_code():
    resp = _client().post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": "never-issued",
            "redirect_uri": REDIRECT_URI,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_grant"


def test_token_endpoint_rejects_wrong_grant_type():
    resp = _client().post(
        "/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "unsupported_grant_type"


def test_protected_route_rejects_missing_bearer_token():
    resp = _client().get("/protected")
    assert resp.status_code == 401


def test_protected_route_rejects_bogus_bearer_token():
    resp = _client().get("/protected", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


def test_well_known_metadata_exposes_correct_endpoints():
    client = _client()
    resp = client.get("/.well-known/oauth-authorization-server")
    assert resp.status_code == 200
    body = resp.json()
    assert body["authorization_endpoint"].endswith("/oauth/authorize")
    assert body["token_endpoint"].endswith("/oauth/token")
    assert "authorization_code" in body["grant_types_supported"]


def test_status_and_oauth_routes_are_exempt_from_bearer_auth():
    client = _client()
    assert client.get("/status").status_code == 200
    assert client.get("/.well-known/oauth-authorization-server").status_code == 200
