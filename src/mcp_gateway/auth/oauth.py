"""OAuth2 endpoints for MCP Gateway."""

import hashlib
import logging
import secrets
from base64 import urlsafe_b64encode
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from itsdangerous import URLSafeTimedSerializer

from .config import get_auth_config
from .providers.github import GitHubProvider
from .tokens import create_access_token, create_refresh_token, verify_token, TokenError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["OAuth"])

# In-memory storage for authorization codes and PKCE verifiers
# In production, use Redis or database
_auth_codes: dict[str, dict[str, Any]] = {}
_pkce_challenges: dict[str, str] = {}  # state -> code_challenge


def _get_serializer() -> URLSafeTimedSerializer:
    """Get serializer for secure state tokens."""
    config = get_auth_config()
    return URLSafeTimedSerializer(config.jwt_secret)


def _generate_state() -> str:
    """Generate a secure state parameter."""
    return secrets.token_urlsafe(32)


def _generate_code_verifier() -> str:
    """Generate PKCE code verifier."""
    return secrets.token_urlsafe(32)


def _generate_code_challenge(verifier: str) -> str:
    """Generate PKCE code challenge from verifier."""
    digest = hashlib.sha256(verifier.encode()).digest()
    return urlsafe_b64encode(digest).rstrip(b"=").decode()


def _get_provider():
    """Get the configured OAuth provider."""
    config = get_auth_config()
    if config.provider == "github":
        return GitHubProvider()
    raise ValueError(f"Unknown OAuth provider: {config.provider}")


def _get_base_url(request: Request) -> str:
    """Get the base URL for OAuth callbacks."""
    config = get_auth_config()
    if config.base_url:
        return config.base_url.rstrip("/")

    # Auto-detect from request
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.url.netloc)
    return f"{scheme}://{host}"


# =============================================================================
# OAuth2 Discovery (RFC 8414)
# =============================================================================


@router.get("/.well-known/oauth-authorization-server")
async def oauth_metadata(request: Request):
    """
    OAuth2 Authorization Server Metadata (RFC 8414).

    This endpoint is used by MCP clients to discover OAuth endpoints.
    """
    config = get_auth_config()

    if not config.enabled:
        raise HTTPException(status_code=404, detail="OAuth not enabled")

    base_url = _get_base_url(request)

    return {
        "issuer": base_url,
        "authorization_endpoint": f"{base_url}/oauth/authorize",
        "token_endpoint": f"{base_url}/oauth/token",
        "registration_endpoint": f"{base_url}/oauth/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["client_secret_post", "none"],
        "scopes_supported": ["tools:read", "tools:execute"],
    }


# =============================================================================
# Authorization Endpoint
# =============================================================================


@router.get("/oauth/authorize")
async def oauth_authorize(
    request: Request,
    client_id: str = Query(..., description="Client identifier"),
    redirect_uri: str = Query(..., description="Redirect URI after authorization"),
    response_type: str = Query("code", description="Response type (must be 'code')"),
    state: str = Query(None, description="Client state for CSRF protection"),
    code_challenge: str = Query(None, description="PKCE code challenge"),
    code_challenge_method: str = Query(None, description="PKCE method (S256)"),
    scope: str = Query(None, description="Requested scopes"),
):
    """
    Start the OAuth2 authorization flow.

    Redirects to the configured OAuth provider (GitHub) for authentication.
    """
    config = get_auth_config()

    if not config.enabled:
        raise HTTPException(status_code=404, detail="OAuth not enabled")

    if response_type != "code":
        raise HTTPException(status_code=400, detail="Only 'code' response type supported")

    # Generate internal state that includes client state
    internal_state = _generate_state()
    serializer = _get_serializer()

    # Store state mapping
    state_data = {
        "client_state": state,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "scope": scope,
    }

    # Store PKCE challenge
    if code_challenge:
        _pkce_challenges[internal_state] = code_challenge

    # Encode state data
    encoded_state = serializer.dumps({"internal": internal_state, "data": state_data})

    # Get provider and redirect to authorization
    provider = _get_provider()
    base_url = _get_base_url(request)
    callback_uri = f"{base_url}/oauth/callback"

    auth_url = provider.get_authorization_url(
        redirect_uri=callback_uri,
        state=encoded_state,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
    )

    return RedirectResponse(url=auth_url)


# =============================================================================
# Callback Endpoint
# =============================================================================


@router.get("/oauth/callback")
async def oauth_callback(
    request: Request,
    code: str = Query(..., description="Authorization code from provider"),
    state: str = Query(..., description="State parameter"),
    error: str = Query(None, description="Error code if authorization failed"),
    error_description: str = Query(None, description="Error description"),
):
    """
    Handle OAuth provider callback.

    Exchanges the authorization code for tokens and redirects back to the client.
    """
    config = get_auth_config()

    if not config.enabled:
        raise HTTPException(status_code=404, detail="OAuth not enabled")

    # Handle errors from provider
    if error:
        logger.error(f"OAuth callback error: {error} - {error_description}")
        raise HTTPException(status_code=400, detail=error_description or error)

    # Decode and validate state
    serializer = _get_serializer()
    try:
        state_payload = serializer.loads(state, max_age=600)  # 10 minute expiry
        internal_state = state_payload["internal"]
        state_data = state_payload["data"]
    except Exception as e:
        logger.error(f"Invalid state: {e}")
        raise HTTPException(status_code=400, detail="Invalid or expired state")

    # Exchange code for provider token
    provider = _get_provider()
    base_url = _get_base_url(request)
    callback_uri = f"{base_url}/oauth/callback"

    try:
        provider_token = await provider.exchange_code(code, callback_uri)
    except Exception as e:
        logger.error(f"Token exchange failed: {e}")
        raise HTTPException(status_code=500, detail="Token exchange failed")

    # Get user info
    try:
        user = await provider.get_user_info(provider_token)
    except Exception as e:
        logger.error(f"User info failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to get user info")

    # Check user allowlist
    if config.allowed_users and user.username not in config.allowed_users:
        logger.warning(f"User {user.username} not in allowlist")
        raise HTTPException(status_code=403, detail="User not authorized")

    logger.info(f"OAuth login successful: {user.username}")

    # Generate our authorization code
    auth_code = secrets.token_urlsafe(32)
    _auth_codes[auth_code] = {
        "subject": user.subject,
        "username": user.username,
        "scope": state_data.get("scope"),
        "code_challenge": _pkce_challenges.pop(internal_state, None),
        "redirect_uri": state_data["redirect_uri"],
    }

    # Redirect back to client with our auth code
    redirect_uri = state_data["redirect_uri"]
    params = {"code": auth_code}
    if state_data.get("client_state"):
        params["state"] = state_data["client_state"]

    return RedirectResponse(url=f"{redirect_uri}?{urlencode(params)}")


# =============================================================================
# Token Endpoint
# =============================================================================


@router.post("/oauth/token")
async def oauth_token(request: Request):
    """
    Exchange authorization code for access token.

    Supports:
    - authorization_code grant
    - refresh_token grant
    """
    config = get_auth_config()

    if not config.enabled:
        raise HTTPException(status_code=404, detail="OAuth not enabled")

    # Parse form data
    try:
        form = await request.form()
    except Exception:
        # Also accept JSON
        form = await request.json()

    grant_type = form.get("grant_type")

    if grant_type == "authorization_code":
        return await _handle_authorization_code_grant(form)
    elif grant_type == "refresh_token":
        return await _handle_refresh_token_grant(form)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported grant type: {grant_type}")


async def _handle_authorization_code_grant(form: dict) -> JSONResponse:
    """Handle authorization_code grant type."""
    code = form.get("code")
    redirect_uri = form.get("redirect_uri")
    code_verifier = form.get("code_verifier")

    if not code:
        raise HTTPException(status_code=400, detail="Missing code")

    # Validate authorization code
    code_data = _auth_codes.pop(code, None)
    if not code_data:
        raise HTTPException(status_code=400, detail="Invalid or expired code")

    # Verify PKCE if challenge was provided
    if code_data.get("code_challenge"):
        if not code_verifier:
            raise HTTPException(status_code=400, detail="Missing code_verifier")
        expected_challenge = _generate_code_challenge(code_verifier)
        if expected_challenge != code_data["code_challenge"]:
            raise HTTPException(status_code=400, detail="Invalid code_verifier")

    # Verify redirect_uri matches
    if redirect_uri and redirect_uri != code_data["redirect_uri"]:
        raise HTTPException(status_code=400, detail="Redirect URI mismatch")

    # Generate tokens
    scopes = ["tools:read", "tools:execute"]
    access_token = create_access_token(
        subject=code_data["subject"],
        scopes=scopes,
        additional_claims={"username": code_data["username"]},
    )
    refresh_token = create_refresh_token(subject=code_data["subject"])

    config = get_auth_config()

    return JSONResponse(
        content={
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": config.access_token_expire_minutes * 60,
            "refresh_token": refresh_token,
            "scope": " ".join(scopes),
        }
    )


async def _handle_refresh_token_grant(form: dict) -> JSONResponse:
    """Handle refresh_token grant type."""
    refresh_token = form.get("refresh_token")

    if not refresh_token:
        raise HTTPException(status_code=400, detail="Missing refresh_token")

    try:
        payload = verify_token(refresh_token)
    except TokenError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=400, detail="Not a refresh token")

    # Generate new tokens
    scopes = ["tools:read", "tools:execute"]
    access_token = create_access_token(
        subject=payload["sub"],
        scopes=scopes,
    )
    new_refresh_token = create_refresh_token(subject=payload["sub"])

    config = get_auth_config()

    return JSONResponse(
        content={
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": config.access_token_expire_minutes * 60,
            "refresh_token": new_refresh_token,
            "scope": " ".join(scopes),
        }
    )


# =============================================================================
# Dynamic Client Registration (RFC 7591)
# =============================================================================


@router.post("/oauth/register")
async def oauth_register(request: Request):
    """
    Dynamic Client Registration endpoint.

    MCP clients can use this to register themselves.
    For simplicity, we accept any client registration.
    """
    config = get_auth_config()

    if not config.enabled:
        raise HTTPException(status_code=404, detail="OAuth not enabled")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Generate a client_id (we don't actually use client_secret for public clients)
    client_id = secrets.token_urlsafe(16)

    return JSONResponse(
        content={
            "client_id": client_id,
            "client_name": body.get("client_name", "MCP Client"),
            "redirect_uris": body.get("redirect_uris", []),
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",  # Public client
        },
        status_code=201,
    )
