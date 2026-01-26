"""Authentication middleware for MCP Gateway."""

import logging
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import get_auth_config
from .tokens import TokenError, verify_token

logger = logging.getLogger(__name__)

# Bearer token extractor (auto_error=False to allow optional auth)
oauth2_scheme = HTTPBearer(auto_error=False)


@dataclass
class AuthenticatedUser:
    """Represents an authenticated user."""

    subject: str  # e.g., "github:username"
    scopes: list[str]
    claims: dict[str, Any]

    @property
    def provider(self) -> str:
        """Extract provider from subject."""
        if ":" in self.subject:
            return self.subject.split(":")[0]
        return "unknown"

    @property
    def username(self) -> str:
        """Extract username from subject."""
        if ":" in self.subject:
            return self.subject.split(":", 1)[1]
        return self.subject


class OptionalAuth:
    """Dependency that extracts user if authenticated, None otherwise."""

    async def __call__(
        self,
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = Depends(oauth2_scheme),
    ) -> AuthenticatedUser | None:
        config = get_auth_config()

        # If OAuth is not enabled, allow all requests
        if not config.enabled:
            return None

        if credentials is None:
            return None

        try:
            payload = verify_token(credentials.credentials)
            scopes = payload.get("scope", "").split() if payload.get("scope") else []
            return AuthenticatedUser(
                subject=payload["sub"],
                scopes=scopes,
                claims=payload,
            )
        except TokenError:
            return None


def _get_base_url(request: Request) -> str:
    """Get the base URL from config or request."""
    config = get_auth_config()

    if config.base_url:
        return config.base_url.rstrip("/")

    # Auto-detect from request
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.url.netloc)
    return f"{scheme}://{host}"


def _get_www_authenticate_header(request: Request) -> str:
    """Build WWW-Authenticate header with resource_metadata per RFC 9728."""
    base_url = _get_base_url(request)
    resource_metadata_url = f"{base_url}/.well-known/oauth-protected-resource"
    return f'Bearer resource_metadata="{resource_metadata_url}"'


def _build_authorization_url(request: Request) -> str:
    """
    Build a direct authorization URL for proxy OAuth pattern.

    This is used to support clients like Claude.ai that don't properly
    follow MCP OAuth discovery and instead expect a direct authorization_url
    in the 401 response body.
    """
    import secrets
    from urllib.parse import urlencode

    base_url = _get_base_url(request)

    # Generate a state parameter for CSRF protection
    state = secrets.token_urlsafe(32)

    # Build authorization URL with parameters that work for Claude.ai
    # Claude.ai will replace redirect_uri with its own callback URL
    params = {
        "response_type": "code",
        "client_id": "claude-ai-proxy",  # Placeholder, will be replaced by Claude
        "redirect_uri": f"{base_url}/oauth/callback",  # Default, Claude overrides
        "state": state,
        "scope": "tools:read tools:execute",
    }

    return f"{base_url}/oauth/authorize?{urlencode(params)}"


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(oauth2_scheme),
) -> AuthenticatedUser | None:
    """
    Dependency to get current user from Bearer token.

    Returns None if OAuth is disabled or no token provided.
    Raises 401 if OAuth is enabled but token is invalid.
    """
    config = get_auth_config()

    # If OAuth is not enabled, allow all requests (return None = anonymous)
    if not config.enabled:
        return None

    # If no credentials provided
    if credentials is None:
        # Check if this is a public path
        if _is_public_path(request.url.path):
            return None
        raise HTTPException(
            status_code=401,
            detail={
                "error": "authentication_required",
                "message": "Not authenticated",
                "authorization_url": _build_authorization_url(request),
            },
            headers={"WWW-Authenticate": _get_www_authenticate_header(request)},
        )

    # Validate token
    try:
        payload = verify_token(credentials.credentials)
    except TokenError as e:
        logger.warning(f"Invalid token: {e}")
        raise HTTPException(
            status_code=401,
            detail={
                "error": "invalid_token",
                "message": str(e),
                "authorization_url": _build_authorization_url(request),
            },
            headers={"WWW-Authenticate": _get_www_authenticate_header(request)},
        )

    scopes = payload.get("scope", "").split() if payload.get("scope") else []

    return AuthenticatedUser(
        subject=payload["sub"],
        scopes=scopes,
        claims=payload,
    )


def require_auth(
    request: Request,
    user: AuthenticatedUser | None = Depends(get_current_user),
) -> AuthenticatedUser:
    """
    Dependency that requires authentication.

    Use this for endpoints that must have a valid user.
    """
    config = get_auth_config()

    # If OAuth is not enabled, return anonymous user
    if not config.enabled:
        return AuthenticatedUser(
            subject="anonymous",
            scopes=["tools:read", "tools:execute"],
            claims={},
        )

    if user is None:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "authentication_required",
                "message": "Authentication required",
                "authorization_url": _build_authorization_url(request),
            },
            headers={"WWW-Authenticate": _get_www_authenticate_header(request)},
        )

    return user


def require_scope(required_scope: str):
    """
    Dependency factory that requires a specific scope.

    Usage:
        @app.get("/protected", dependencies=[Depends(require_scope("tools:execute"))])
    """

    def dependency(user: AuthenticatedUser = Depends(require_auth)) -> AuthenticatedUser:
        config = get_auth_config()

        # If OAuth is not enabled, allow all
        if not config.enabled:
            return user

        if required_scope not in user.scopes:
            raise HTTPException(
                status_code=403,
                detail=f"Scope '{required_scope}' required",
            )

        return user

    return dependency


# Paths that don't require authentication
PUBLIC_PATHS = {
    "/",
    "/health",
    "/openapi.json",
    "/docs",
    "/redoc",
    "/.well-known/oauth-authorization-server",
    "/.well-known/oauth-protected-resource",
    "/oauth/authorize",
    "/oauth/callback",
    "/oauth/token",
    "/oauth/register",
    "/oauth/device",
    "/oauth/device/verify",
    "/oauth/device/authorize",
    "/oauth/device/callback",
}

# Path prefixes that are public
PUBLIC_PREFIXES = (
    "/static/",
)


def _is_public_path(path: str) -> bool:
    """Check if a path is public (doesn't require auth)."""
    if path in PUBLIC_PATHS:
        return True
    for prefix in PUBLIC_PREFIXES:
        if path.startswith(prefix):
            return True
    return False
