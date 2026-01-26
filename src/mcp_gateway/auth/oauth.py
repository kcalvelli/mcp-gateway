"""OAuth2 endpoints for MCP Gateway."""

import hashlib
import logging
import secrets
import time
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
_device_codes: dict[str, dict[str, Any]] = {}  # device_code -> {user_code, client_id, scope, expires_at, authorized_user}


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
# OAuth2 Discovery (RFC 8414 & RFC 9470)
# =============================================================================


@router.get("/.well-known/oauth-protected-resource")
async def oauth_protected_resource(request: Request):
    """
    OAuth2 Protected Resource Metadata (RFC 9470).

    This endpoint tells MCP clients where to find the authorization server
    for this protected resource. Required for MCP Streamable HTTP transport.
    """
    config = get_auth_config()

    if not config.enabled:
        raise HTTPException(status_code=404, detail="OAuth not enabled")

    base_url = _get_base_url(request)

    return {
        "resource": base_url,
        "authorization_servers": [base_url],
        "scopes_supported": ["tools:read", "tools:execute"],
        "bearer_methods_supported": ["header"],
    }


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
        "device_authorization_endpoint": f"{base_url}/oauth/device",
        "response_types_supported": ["code"],
        "grant_types_supported": [
            "authorization_code",
            "refresh_token",
            "urn:ietf:params:oauth:grant-type:device_code",
        ],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["client_secret_post", "none"],
        "scopes_supported": ["tools:read", "tools:execute"],
    }


# =============================================================================
# Simple Login Endpoint (for Claude.ai proxy pattern)
# =============================================================================


@router.get("/oauth/login")
async def oauth_login(request: Request):
    """
    Simple OAuth login endpoint for Claude.ai.

    Unlike /oauth/authorize, this doesn't require any parameters.
    It directly redirects to the OAuth provider and handles the callback internally.
    """
    config = get_auth_config()

    if not config.enabled:
        raise HTTPException(status_code=404, detail="OAuth not enabled")

    # Generate state for CSRF protection
    internal_state = _generate_state()
    serializer = _get_serializer()

    base_url = _get_base_url(request)

    # Store state data - we'll redirect back to a simple success page
    state_data = {
        "client_state": None,
        "redirect_uri": f"{base_url}/oauth/login/success",
        "client_id": "claude-ai",
        "scope": "tools:read tools:execute",
        "flow": "login",  # Mark as simple login flow
    }

    encoded_state = serializer.dumps({"internal": internal_state, "data": state_data})

    # Get provider and redirect to authorization
    provider = _get_provider()
    callback_uri = f"{base_url}/oauth/callback"

    auth_url = provider.get_authorization_url(
        redirect_uri=callback_uri,
        state=encoded_state,
    )

    return RedirectResponse(url=auth_url)


@router.get("/auth/status")
async def auth_status(request: Request):
    """
    Authentication status endpoint for Claude.ai.

    Returns information about how to authenticate with this server.
    """
    config = get_auth_config()

    base_url = _get_base_url(request)

    return {
        "auth_type": "oauth2" if config.enabled else "none",
        "auth_enabled": config.enabled,
        "login_url": f"{base_url}/oauth/login" if config.enabled else None,
        "authorization_url": f"{base_url}/oauth/authorize" if config.enabled else None,
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
    elif grant_type == "urn:ietf:params:oauth:grant-type:device_code":
        return await _handle_device_code_grant(form)
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


async def _handle_device_code_grant(form: dict) -> JSONResponse:
    """Handle device_code grant type (RFC 8628)."""
    device_code = form.get("device_code")
    # client_id = form.get("client_id")  # Optional validation

    if not device_code:
        raise HTTPException(status_code=400, detail="Missing device_code")

    # Look up device code
    device_data = _device_codes.get(device_code)

    if not device_data:
        raise HTTPException(status_code=400, detail="Invalid device_code")

    # Check if expired
    if time.time() > device_data["expires_at"]:
        # Clean up expired code
        user_code = device_data.get("user_code")
        _device_codes.pop(device_code, None)
        if user_code:
            _device_codes.pop(f"user:{user_code}", None)
        raise HTTPException(status_code=400, detail="expired_token")

    # Check if user has authorized
    if device_data["authorized_user"] is None:
        # User hasn't authorized yet - return authorization_pending
        # This is a special OAuth error that tells client to keep polling
        return JSONResponse(
            content={"error": "authorization_pending"},
            status_code=400,
        )

    # User has authorized! Generate tokens
    user = device_data["authorized_user"]

    # Clean up device code
    user_code = device_data.get("user_code")
    _device_codes.pop(device_code, None)
    if user_code:
        _device_codes.pop(f"user:{user_code}", None)

    scopes = ["tools:read", "tools:execute"]
    access_token = create_access_token(
        subject=user["subject"],
        scopes=scopes,
        additional_claims={"username": user["username"]},
    )
    refresh_token = create_refresh_token(subject=user["subject"])

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


# =============================================================================
# Device Authorization (RFC 8628)
# =============================================================================


def _generate_user_code() -> str:
    """Generate a user-friendly code for device authorization."""
    # Generate 8 character alphanumeric code (easy to type)
    import string
    chars = string.ascii_uppercase + string.digits
    # Remove confusing characters
    chars = chars.replace("0", "").replace("O", "").replace("I", "").replace("1", "")
    return "".join(secrets.choice(chars) for _ in range(8))


@router.post("/oauth/device")
async def device_authorization(request: Request):
    """
    Device Authorization endpoint (RFC 8628).

    Used by clients that can't open a browser (CLI tools, Claude.ai integrations).
    Returns a device_code and user_code for the user to authorize.
    """
    config = get_auth_config()

    if not config.enabled:
        raise HTTPException(status_code=404, detail="OAuth not enabled")

    # Parse form data or JSON
    try:
        body = await request.form()
        body = dict(body)
    except Exception:
        try:
            body = await request.json()
        except Exception:
            body = {}

    client_id = body.get("client_id", "unknown")
    scope = body.get("scope", "tools:read tools:execute")

    # Generate codes
    device_code = secrets.token_urlsafe(32)
    user_code = _generate_user_code()

    base_url = _get_base_url(request)

    # Store device code data (expires in 15 minutes)
    _device_codes[device_code] = {
        "user_code": user_code,
        "client_id": client_id,
        "scope": scope,
        "expires_at": time.time() + 900,  # 15 minutes
        "authorized_user": None,  # Set when user authorizes
    }

    # Also index by user_code for lookup during authorization
    _device_codes[f"user:{user_code}"] = device_code

    return JSONResponse(
        content={
            "device_code": device_code,
            "user_code": user_code,
            "verification_uri": f"{base_url}/oauth/device/verify",
            "verification_uri_complete": f"{base_url}/oauth/device/verify?user_code={user_code}",
            "expires_in": 900,
            "interval": 5,
        }
    )


@router.get("/oauth/device/verify")
async def device_verify_page(
    request: Request,
    user_code: str = Query(None, description="Pre-filled user code"),
):
    """
    Device verification page where users enter their code.

    This is a simple HTML page that redirects to GitHub OAuth.
    """
    config = get_auth_config()

    if not config.enabled:
        raise HTTPException(status_code=404, detail="OAuth not enabled")

    base_url = _get_base_url(request)

    # Simple HTML form
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Device Authorization - MCP Gateway</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                   max-width: 400px; margin: 100px auto; padding: 20px; text-align: center; }}
            h1 {{ color: #333; }}
            input {{ font-size: 24px; padding: 10px; text-align: center;
                    letter-spacing: 4px; text-transform: uppercase; width: 200px; }}
            button {{ font-size: 18px; padding: 10px 30px; margin-top: 20px;
                     background: #007bff; color: white; border: none; border-radius: 5px; cursor: pointer; }}
            button:hover {{ background: #0056b3; }}
            .error {{ color: red; margin-top: 10px; }}
        </style>
    </head>
    <body>
        <h1>🔐 MCP Gateway</h1>
        <p>Enter the code shown by your application:</p>
        <form action="{base_url}/oauth/device/authorize" method="get">
            <input type="text" name="user_code" value="{user_code or ''}"
                   placeholder="XXXX-XXXX" maxlength="8" required autofocus>
            <br>
            <button type="submit">Authorize</button>
        </form>
    </body>
    </html>
    """
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html)


@router.get("/oauth/device/authorize")
async def device_authorize(
    request: Request,
    user_code: str = Query(..., description="User code from device"),
):
    """
    Start device authorization flow after user enters code.

    Redirects to GitHub OAuth, then back to complete the device authorization.
    """
    config = get_auth_config()

    if not config.enabled:
        raise HTTPException(status_code=404, detail="OAuth not enabled")

    # Look up device code by user code
    user_code = user_code.upper().replace("-", "").replace(" ", "")
    device_code = _device_codes.get(f"user:{user_code}")

    if not device_code:
        from fastapi.responses import HTMLResponse
        return HTMLResponse(
            content="<h1>Invalid or expired code</h1><p>Please try again.</p>",
            status_code=400
        )

    device_data = _device_codes.get(device_code)
    if not device_data or time.time() > device_data["expires_at"]:
        from fastapi.responses import HTMLResponse
        return HTMLResponse(
            content="<h1>Code expired</h1><p>Please request a new code from your application.</p>",
            status_code=400
        )

    # Start OAuth flow with GitHub, storing device_code in state
    serializer = _get_serializer()
    state_data = {
        "device_code": device_code,
        "user_code": user_code,
    }
    encoded_state = serializer.dumps({"type": "device", "data": state_data})

    provider = _get_provider()
    base_url = _get_base_url(request)
    callback_uri = f"{base_url}/oauth/device/callback"

    auth_url = provider.get_authorization_url(
        redirect_uri=callback_uri,
        state=encoded_state,
    )

    return RedirectResponse(url=auth_url)


@router.get("/oauth/device/callback")
async def device_callback(
    request: Request,
    code: str = Query(..., description="Authorization code from provider"),
    state: str = Query(..., description="State parameter"),
    error: str = Query(None, description="Error code if authorization failed"),
    error_description: str = Query(None, description="Error description"),
):
    """
    Handle OAuth callback for device authorization.

    Marks the device code as authorized so the polling client can get a token.
    """
    config = get_auth_config()

    if not config.enabled:
        raise HTTPException(status_code=404, detail="OAuth not enabled")

    from fastapi.responses import HTMLResponse

    # Handle errors from provider
    if error:
        logger.error(f"Device OAuth callback error: {error} - {error_description}")
        return HTMLResponse(
            content=f"<h1>Authorization failed</h1><p>{error_description or error}</p>",
            status_code=400
        )

    # Decode state
    serializer = _get_serializer()
    try:
        state_payload = serializer.loads(state, max_age=600)
        if state_payload.get("type") != "device":
            raise ValueError("Not a device authorization state")
        state_data = state_payload["data"]
        device_code = state_data["device_code"]
    except Exception as e:
        logger.error(f"Invalid device state: {e}")
        return HTMLResponse(
            content="<h1>Invalid or expired state</h1>",
            status_code=400
        )

    # Get device data
    device_data = _device_codes.get(device_code)
    if not device_data or time.time() > device_data["expires_at"]:
        return HTMLResponse(
            content="<h1>Device code expired</h1><p>Please start over.</p>",
            status_code=400
        )

    # Exchange code for provider token
    provider = _get_provider()
    base_url = _get_base_url(request)
    callback_uri = f"{base_url}/oauth/device/callback"

    try:
        provider_token = await provider.exchange_code(code, callback_uri)
    except Exception as e:
        logger.error(f"Device token exchange failed: {e}")
        return HTMLResponse(
            content="<h1>Token exchange failed</h1>",
            status_code=500
        )

    # Get user info
    try:
        user = await provider.get_user_info(provider_token)
    except Exception as e:
        logger.error(f"Device user info failed: {e}")
        return HTMLResponse(
            content="<h1>Failed to get user info</h1>",
            status_code=500
        )

    # Check user allowlist
    if config.allowed_users and user.username not in config.allowed_users:
        logger.warning(f"Device auth: User {user.username} not in allowlist")
        return HTMLResponse(
            content=f"<h1>Access Denied</h1><p>User {user.username} is not authorized.</p>",
            status_code=403
        )

    logger.info(f"Device OAuth login successful: {user.username}")

    # Mark device code as authorized
    device_data["authorized_user"] = {
        "subject": user.subject,
        "username": user.username,
    }

    return HTMLResponse(
        content="""
        <html>
        <head>
            <title>Authorized - MCP Gateway</title>
            <style>
                body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                       max-width: 400px; margin: 100px auto; padding: 20px; text-align: center; }
                h1 { color: #28a745; }
            </style>
        </head>
        <body>
            <h1>✅ Authorized!</h1>
            <p>You can close this window and return to your application.</p>
        </body>
        </html>
        """
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
