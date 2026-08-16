import base64

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from basic_auth_server.auth_middleware import BasicAuthMiddleware

USERNAME = "test-user"
PASSWORD = "test-pass"


async def _ok(_request: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


def _client() -> TestClient:
    app = Starlette(
        routes=[Route("/protected", _ok), Route("/status", _ok)],
        middleware=[
            Middleware(
                BasicAuthMiddleware,
                username=USERNAME,
                password=PASSWORD,
                exempt_paths=frozenset({"/status"}),
            )
        ],
    )
    return TestClient(app)


def _basic_header(username: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def test_correct_credentials_pass():
    resp = _client().get("/protected", headers=_basic_header(USERNAME, PASSWORD))
    assert resp.status_code == 200
    assert resp.text == "ok"


def test_missing_auth_header_rejected():
    resp = _client().get("/protected")
    assert resp.status_code == 401
    assert resp.json() == {"error": "unauthorized"}
    assert "Basic" in resp.headers["www-authenticate"]


def test_wrong_username_rejected():
    resp = _client().get("/protected", headers=_basic_header("someone-else", PASSWORD))
    assert resp.status_code == 401


def test_wrong_password_rejected():
    resp = _client().get("/protected", headers=_basic_header(USERNAME, "wrong"))
    assert resp.status_code == 401


def test_non_basic_scheme_rejected():
    resp = _client().get("/protected", headers={"Authorization": "Bearer sometoken"})
    assert resp.status_code == 401


def test_malformed_base64_rejected():
    resp = _client().get("/protected", headers={"Authorization": "Basic not-valid-base64!!"})
    assert resp.status_code == 401


def test_exempt_path_bypasses_auth():
    resp = _client().get("/status")
    assert resp.status_code == 200
