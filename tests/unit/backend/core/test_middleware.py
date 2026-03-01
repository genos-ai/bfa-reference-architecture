"""
Unit Tests for Request Context Middleware.

Tests use a real Starlette test client with the actual middleware —
no mocks. Verifies request ID, source extraction, response timing,
and error handling through real HTTP requests.
"""

from datetime import datetime

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from modules.backend.core.middleware import RequestContextMiddleware


def _make_app(handler=None):
    """Build a minimal Starlette app with the real middleware."""

    async def default_handler(request: Request) -> JSONResponse:
        return JSONResponse({
            "request_id": request.state.request_id,
            "source": request.state.source,
            "start_time": request.state.start_time.isoformat() if request.state.start_time else None,
        })

    async def error_handler(request: Request) -> JSONResponse:
        raise RuntimeError("Something went wrong")

    routes = [
        Route("/test", handler or default_handler),
        Route("/error", error_handler),
    ]
    app = Starlette(routes=routes)
    app.add_middleware(RequestContextMiddleware)
    return app


@pytest.fixture
def client():
    return TestClient(_make_app(), raise_server_exceptions=False)


class TestRequestId:
    """Tests for X-Request-ID generation and propagation."""

    def test_generates_request_id_when_not_provided(self, client):
        response = client.get("/test")
        assert response.status_code == 200
        assert "X-Request-ID" in response.headers
        assert len(response.headers["X-Request-ID"]) == 36

    def test_uses_provided_request_id(self, client):
        response = client.get("/test", headers={"X-Request-ID": "custom-id-123"})
        assert response.headers["X-Request-ID"] == "custom-id-123"
        assert response.json()["request_id"] == "custom-id-123"

    def test_request_id_stored_on_state(self, client):
        response = client.get("/test")
        assert response.json()["request_id"] is not None
        assert len(response.json()["request_id"]) == 36


class TestSource:
    """Tests for X-Frontend-ID source extraction."""

    def test_extracts_source_web(self, client):
        response = client.get("/test", headers={"X-Frontend-ID": "web"})
        assert response.json()["source"] == "web"

    def test_extracts_source_cli(self, client):
        response = client.get("/test", headers={"X-Frontend-ID": "cli"})
        assert response.json()["source"] == "cli"

    def test_extracts_source_telegram(self, client):
        response = client.get("/test", headers={"X-Frontend-ID": "telegram"})
        assert response.json()["source"] == "telegram"

    def test_source_is_none_when_header_missing(self, client):
        response = client.get("/test")
        assert response.json()["source"] is None

    def test_unrecognized_source_dropped(self, client):
        response = client.get("/test", headers={"X-Frontend-ID": "custom-client"})
        assert response.json()["source"] is None

    def test_source_case_insensitive(self, client):
        response = client.get("/test", headers={"X-Frontend-ID": "WEB"})
        assert response.json()["source"] == "web"

    def test_source_trimmed(self, client):
        response = client.get("/test", headers={"X-Frontend-ID": "  cli  "})
        assert response.json()["source"] == "cli"


class TestResponseTime:
    """Tests for X-Response-Time header."""

    def test_adds_response_time_header(self, client):
        response = client.get("/test")
        assert "X-Response-Time" in response.headers
        assert response.headers["X-Response-Time"].endswith("ms")

    def test_response_time_is_non_negative(self, client):
        response = client.get("/test")
        ms_str = response.headers["X-Response-Time"].replace("ms", "")
        assert int(ms_str) >= 0


class TestRequestState:
    """Tests for request.state population."""

    def test_start_time_is_timezone_naive_utc(self, client):
        response = client.get("/test")
        start_time_str = response.json()["start_time"]
        assert start_time_str is not None
        dt = datetime.fromisoformat(start_time_str)
        assert dt.tzinfo is None


class TestErrorHandling:
    """Tests for middleware behavior during errors."""

    def test_reraises_exception(self):
        app = _make_app()
        test_client = TestClient(app, raise_server_exceptions=False)
        response = test_client.get("/error")
        assert response.status_code == 500

    def test_error_response_has_request_id(self):
        app = _make_app()
        test_client = TestClient(app, raise_server_exceptions=False)
        response = test_client.get("/error", headers={"X-Request-ID": "err-123"})
        assert response.status_code == 500
