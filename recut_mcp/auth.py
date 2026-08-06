"""
OAuth 2.1 for the hosted HTTP transport (spec sec 9.2, Unit 4.7). Local
stdio mode (the v1 default, see DESIGN_NOTES.md "Local-first default")
needs no auth at all - nothing here is imported by recut_mcp/server.py's
stdio path.

MINIMAL SELF-HOSTED PROVIDER: Unit 4.7's own instruction is "a standard
OAuth 2.1 flow against whatever auth provider you choose, or a minimal
self-hosted OAuth server if none is chosen" - no third-party identity
provider (Auth0, Okta, ...) is configured anywhere in this project, so
this implements that explicit fallback: a combined Authorization Server +
Resource Server on one MCPServer instance (the MCP Python SDK's own
"legacy combined AS+RS" pattern - appropriate for a single-operator
self-hosted deployment, not a multi-tenant hosted product; see the SDK's
examples/servers/simple-auth/mcp_simple_auth/legacy_as_server.py, which
this module's shape closely follows).

Single operator credential pair (RECUT_MCP_AUTH_USERNAME/
RECUT_MCP_AUTH_PASSWORD - see common/config.py) - deliberately NOT
hardcoded, unlike the SDK's own demo provider (which ships a fixed
demo_user/demo_password pair): this is real repository code, not a
throwaway example. Authorization codes and access tokens live in an
in-memory dict - lost on restart, single-process only. Acceptable v1
scope for a single-operator server (same posture as
Settings.celery_task_always_eager's own "no real deployment
infrastructure exists yet" note) - swap for a persistent store (e.g.
api.store's Redis-backed pattern) if this ever needs to survive restarts
or run behind multiple worker processes.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyHttpUrl
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

_AUTH_CODE_TTL_S = 300
_ACCESS_TOKEN_TTL_S = 3600


class MissingAuthCredentialsError(Exception):
    """Raised at server-start time if hosted mode is requested but no
    operator credential pair is configured - fail loudly rather than
    silently falling back to an insecure default."""


@dataclass
class _PendingAuthorization:
    redirect_uri: str
    code_challenge: str
    redirect_uri_provided_explicitly: bool
    client_id: str
    resource: str | None


class RecutOAuthProvider(OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]):
    """Combined AS+RS provider for a single operator credential pair. PKCE
    itself is verified by the SDK's own /token route handler (against
    AuthorizationCode.code_challenge) - not re-implemented here; this
    class only owns code/token issuance and the login form."""

    def __init__(self, *, username: str, password: str, scope: str, login_url: str, server_url: str) -> None:
        self._username = username
        self._password = password
        self._scope = scope
        self._login_url = login_url
        self._server_url = server_url
        self._clients: dict[str, OAuthClientInformationFull] = {}
        self._pending_by_state: dict[str, _PendingAuthorization] = {}
        self._auth_codes: dict[str, AuthorizationCode] = {}
        self._access_tokens: dict[str, AccessToken] = {}

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self._clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if not client_info.client_id:
            raise ValueError("no client_id provided")
        self._clients[client_info.client_id] = client_info

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        state = params.state or secrets.token_hex(16)
        self._pending_by_state[state] = _PendingAuthorization(
            redirect_uri=str(params.redirect_uri),
            code_challenge=params.code_challenge,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            client_id=client.client_id,
            resource=params.resource,
        )
        return f"{self._login_url}?state={state}&client_id={client.client_id}"

    async def get_login_page(self, state: str) -> HTMLResponse:
        if state not in self._pending_by_state:
            raise HTTPException(400, "unknown or expired state parameter")
        return HTMLResponse(
            f"""<!DOCTYPE html>
<html><body>
<h2>RECUT sign-in</h2>
<form action="{self._server_url.rstrip('/')}/login/callback" method="post">
  <input type="hidden" name="state" value="{state}">
  <label>Username <input type="text" name="username" required></label><br>
  <label>Password <input type="password" name="password" required></label><br>
  <button type="submit">Sign in</button>
</form>
</body></html>"""
        )

    async def handle_login_callback(self, request: Request) -> Response:
        form = await request.form()
        username, password, state = form.get("username"), form.get("password"), form.get("state")
        if not (isinstance(username, str) and isinstance(password, str) and isinstance(state, str)):
            raise HTTPException(400, "missing username, password, or state")

        pending = self._pending_by_state.get(state)
        if pending is None:
            raise HTTPException(400, "unknown or expired state parameter")

        # Constant-time comparison - a plain `==` here would leak how many
        # leading characters matched via response timing.
        if not (
            secrets.compare_digest(username, self._username) and secrets.compare_digest(password, self._password)
        ):
            raise HTTPException(401, "invalid credentials")

        code = f"recut_{secrets.token_hex(16)}"
        self._auth_codes[code] = AuthorizationCode(
            code=code,
            client_id=pending.client_id,
            redirect_uri=AnyHttpUrl(pending.redirect_uri),
            redirect_uri_provided_explicitly=pending.redirect_uri_provided_explicitly,
            expires_at=time.time() + _AUTH_CODE_TTL_S,
            scopes=[self._scope],
            code_challenge=pending.code_challenge,
            resource=pending.resource,
            subject=username,
        )
        del self._pending_by_state[state]
        redirect_uri = construct_redirect_uri(pending.redirect_uri, code=code, state=state)
        return RedirectResponse(url=redirect_uri, status_code=302)

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        return self._auth_codes.get(authorization_code)

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        if authorization_code.code not in self._auth_codes:
            raise ValueError("invalid or already-used authorization code")

        token = f"recut_{secrets.token_hex(32)}"
        self._access_tokens[token] = AccessToken(
            token=token,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            expires_at=int(time.time()) + _ACCESS_TOKEN_TTL_S,
            resource=authorization_code.resource,
            subject=authorization_code.subject,
        )
        del self._auth_codes[authorization_code.code]

        return OAuthToken(
            access_token=token,
            token_type="Bearer",
            expires_in=_ACCESS_TOKEN_TTL_S,
            scope=" ".join(authorization_code.scopes),
        )

    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> RefreshToken | None:
        return None  # refresh tokens are not supported by this minimal v1 provider

    async def exchange_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: RefreshToken, scopes: list[str]
    ) -> OAuthToken:
        raise NotImplementedError("refresh tokens are not supported by this minimal v1 provider")

    async def load_access_token(self, token: str) -> AccessToken | None:
        access_token = self._access_tokens.get(token)
        if access_token is None:
            return None
        if access_token.expires_at is not None and access_token.expires_at < time.time():
            del self._access_tokens[token]
            return None
        return access_token

    async def revoke_token(self, token: AccessToken | RefreshToken, token_type_hint: str | None = None) -> None:
        self._access_tokens.pop(token.token, None)


# The single active provider, if a hosted server is running in this
# process - lets verify_token() (below) check a token without every
# caller needing to thread the provider instance through by hand. None
# when only stdio mode has ever been started (or nothing has).
_active_provider: RecutOAuthProvider | None = None


def _set_active_provider(provider: RecutOAuthProvider | None) -> None:
    global _active_provider
    _active_provider = provider


async def verify_token(token: str) -> dict:
    """Returns the authenticated principal's claims, or raises.

    DEVIATION FROM THE ORIGINAL STUB SIGNATURE (was a plain `def`): token
    verification is inherently async here (AccessToken lookup is an async
    provider method, matching the SDK's own AccessToken/TokenVerifier
    shape throughout) - faking synchronicity with `asyncio.run()` risks a
    "loop already running" error the moment this is ever called from
    async code (e.g. the SDK's own request path), which is worse than an
    honest async signature. NOTE: the SDK's own request middleware does
    NOT call this function - it calls the active provider's
    load_access_token() directly. This function exists as a standalone
    convenience for callers (tests, an admin CLI) that want to check a
    token without going through the full SDK request machinery.
    """
    if _active_provider is None:
        raise RuntimeError(
            "no RECUT OAuth provider is active - call recut_mcp.server.run_http_server() "
            "(or build_http_server()) first"
        )

    access_token = await _active_provider.load_access_token(token)
    if access_token is None:
        raise ValueError("invalid, expired, or revoked token")

    return {
        "client_id": access_token.client_id,
        "scopes": access_token.scopes,
        "subject": access_token.subject,
        "expires_at": access_token.expires_at,
    }
