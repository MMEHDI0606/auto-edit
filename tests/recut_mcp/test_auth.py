"""
Unit 4.7 done criteria: the same tool surface verified working in Unit 4.6
works identically over Streamable HTTP with a COMPLETED OAuth 2.1
(authorization-code + PKCE) flow. Every step here is real: real dynamic
client registration (RFC 7591), a real PKCE challenge/verifier pair, a
real login form round-trip, a real authorization-code-for-token exchange,
and a real authenticated MCP session (initialize -> notifications/
initialized -> tools/call) over the SDK's own Streamable HTTP ASGI app via
starlette's TestClient (in-process, no real socket needed) - not a
simulation of the protocol, the actual protocol.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import re
import secrets
import urllib.parse

import pytest
from starlette.testclient import TestClient

import recut_mcp.auth as auth_module
from common.config import load_settings
from recut_mcp.auth import MissingAuthCredentialsError, verify_token
from recut_mcp.server import build_http_server

_REDIRECT_URI = "http://127.0.0.1:9999/callback"


@pytest.fixture(autouse=True)
def _reset_active_provider():
    auth_module._set_active_provider(None)
    yield
    auth_module._set_active_provider(None)


@pytest.fixture()
def hosted_auth_env(monkeypatch):
    monkeypatch.setenv("RECUT_MCP_AUTH_USERNAME", "testop")
    monkeypatch.setenv("RECUT_MCP_AUTH_PASSWORD", "testpass123")
    load_settings.cache_clear()
    yield
    load_settings.cache_clear()


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def _register_client(client: TestClient) -> str:
    response = client.post(
        "/register",
        json={
            "redirect_uris": [_REDIRECT_URI],
            "client_name": "test-client",
            "grant_types": ["authorization_code"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        },
    )
    assert response.status_code == 201
    return response.json()["client_id"]


def _authorize_and_login(client: TestClient, *, client_id: str, code_challenge: str, username: str, password: str):
    """Drives /authorize -> /login -> /login/callback. Returns the
    authorization code (str) on success, or the raw callback Response if
    the login itself was rejected (caller asserts on it directly - see
    test_login_with_wrong_password_is_rejected)."""
    authz = client.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": _REDIRECT_URI,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": "test-state",
            "scope": "recut",
        },
        follow_redirects=False,
    )
    assert authz.status_code == 302
    login_page = client.get(authz.headers["location"], follow_redirects=False)
    assert login_page.status_code == 200
    state = re.search(r'name="state" value="([^"]+)"', login_page.text).group(1)

    callback = client.post(
        "/login/callback", data={"username": username, "password": password, "state": state}, follow_redirects=False
    )
    if callback.status_code != 302:
        return callback  # let the caller assert on the error response directly

    code = urllib.parse.parse_qs(urllib.parse.urlparse(callback.headers["location"]).query)["code"][0]
    return code


def _complete_oauth_flow(client: TestClient) -> str:
    """Full authorization-code+PKCE dance with correct credentials -
    returns a real, valid access_token."""
    client_id = _register_client(client)
    verifier, challenge = _pkce_pair()
    code = _authorize_and_login(client, client_id=client_id, code_challenge=challenge, username="testop", password="testpass123")

    token_resp = client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": _REDIRECT_URI,
            "client_id": client_id,
            "code_verifier": verifier,
        },
    )
    assert token_resp.status_code == 200
    return token_resp.json()["access_token"]


def test_build_http_server_refuses_to_start_without_credentials(monkeypatch) -> None:
    monkeypatch.delenv("RECUT_MCP_AUTH_USERNAME", raising=False)
    monkeypatch.delenv("RECUT_MCP_AUTH_PASSWORD", raising=False)
    load_settings.cache_clear()
    try:
        with pytest.raises(MissingAuthCredentialsError):
            build_http_server(host="localhost", port=8000)
    finally:
        load_settings.cache_clear()


def test_full_authorization_code_pkce_flow_issues_a_valid_bearer_token(hosted_auth_env) -> None:
    server = build_http_server(host="localhost", port=8000)
    app = server.streamable_http_app(json_response=True)

    with TestClient(app, base_url="http://localhost:8000") as client:
        client_id = _register_client(client)
        verifier, challenge = _pkce_pair()
        code = _authorize_and_login(
            client, client_id=client_id, code_challenge=challenge, username="testop", password="testpass123"
        )

        token_resp = client.post(
            "/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": _REDIRECT_URI,
                "client_id": client_id,
                "code_verifier": verifier,
            },
        )

        assert token_resp.status_code == 200
        body = token_resp.json()
        assert body["token_type"] == "Bearer"
        assert body["scope"] == "recut"
        assert len(body["access_token"]) > 20


def test_login_with_wrong_password_is_rejected(hosted_auth_env) -> None:
    server = build_http_server(host="localhost", port=8000)
    app = server.streamable_http_app(json_response=True)

    with TestClient(app, base_url="http://localhost:8000") as client:
        client_id = _register_client(client)
        _, challenge = _pkce_pair()
        response = _authorize_and_login(
            client, client_id=client_id, code_challenge=challenge, username="testop", password="wrong-password"
        )
        assert response.status_code == 401


def test_login_page_with_unknown_state_is_rejected(hosted_auth_env) -> None:
    server = build_http_server(host="localhost", port=8000)
    app = server.streamable_http_app(json_response=True)

    with TestClient(app, base_url="http://localhost:8000") as client:
        response = client.get("/login", params={"state": "never-issued-state"})
        assert response.status_code == 400


def test_mcp_endpoint_without_a_token_is_rejected(hosted_auth_env) -> None:
    server = build_http_server(host="localhost", port=8000)
    app = server.streamable_http_app(json_response=True)

    with TestClient(app, base_url="http://localhost:8000") as client:
        response = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}},
            },
        )
        assert response.status_code == 401


def test_authenticated_mcp_session_can_call_a_real_tool(hosted_auth_env, fake_redis_server) -> None:
    """The unit's own done criterion, end to end: a completed OAuth flow,
    then the SAME tool surface (search_library) actually executes over
    Streamable HTTP, exactly as it does over stdio (Unit 4.6)."""
    server = build_http_server(host="localhost", port=8000)
    app = server.streamable_http_app(json_response=True)

    with TestClient(app, base_url="http://localhost:8000") as client:
        access_token = _complete_oauth_flow(client)
        headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json, text/event-stream"}

        init = client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}},
            },
        )
        assert init.status_code == 200
        session_headers = dict(headers, **{"mcp-session-id": init.headers["mcp-session-id"]})

        notif = client.post("/mcp", headers=session_headers, json={"jsonrpc": "2.0", "method": "notifications/initialized"})
        assert notif.status_code == 202

        call = client.post(
            "/mcp",
            headers=session_headers,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "search_library", "arguments": {"query": "anything"}}},
        )
        assert call.status_code == 200
        result = call.json()["result"]
        assert result.get("isError") is not True


def test_verify_token_resolves_a_valid_token_to_the_right_claims(hosted_auth_env) -> None:
    server = build_http_server(host="localhost", port=8000)
    app = server.streamable_http_app(json_response=True)

    with TestClient(app, base_url="http://localhost:8000") as client:
        access_token = _complete_oauth_flow(client)

    claims = asyncio.run(verify_token(access_token))
    assert claims["subject"] == "testop"
    assert claims["scopes"] == ["recut"]


def test_verify_token_raises_for_an_invalid_token(hosted_auth_env) -> None:
    build_http_server(host="localhost", port=8000)  # registers the active provider
    with pytest.raises(ValueError):
        asyncio.run(verify_token("not-a-real-token"))


def test_verify_token_raises_when_no_hosted_server_has_ever_run() -> None:
    with pytest.raises(RuntimeError):
        asyncio.run(verify_token("anything"))
