from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from api_key_server.auth_middleware import ApiKeyAuthMiddleware

API_KEY = "test-key-12345"
HEADER_NAME = "x-api-key"


async def _ok(_request: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


def _client() -> TestClient:
    app = Starlette(
        routes=[Route("/protected", _ok), Route("/status", _ok)],
        middleware=[
            Middleware(
                ApiKeyAuthMiddleware,
                api_key=API_KEY,
                header_name=HEADER_NAME,
                exempt_paths=frozenset({"/status"}),
            )
        ],
    )
    return TestClient(app)


def test_correct_key_passes():
    resp = _client().get("/protected", headers={"X-API-Key": API_KEY})
    assert resp.status_code == 200


def test_header_name_is_case_insensitive():
    # HTTP header names are case-insensitive on the wire; httpx/Starlette
    # normalize them, so a differently-cased header from the caller must
    # still match.
    resp = _client().get("/protected", headers={"x-Api-KEY": API_KEY})
    assert resp.status_code == 200


def test_missing_header_rejected():
    resp = _client().get("/protected")
    assert resp.status_code == 401
    assert resp.json() == {"error": "unauthorized"}


def test_wrong_key_rejected():
    resp = _client().get("/protected", headers={"X-API-Key": "wrong-key"})
    assert resp.status_code == 401


def test_empty_key_rejected():
    resp = _client().get("/protected", headers={"X-API-Key": ""})
    assert resp.status_code == 401


def test_exempt_path_bypasses_auth():
    resp = _client().get("/status")
    assert resp.status_code == 200
