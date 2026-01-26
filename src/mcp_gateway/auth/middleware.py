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
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate token
    try:
        payload = verify_token(credentials.credentials)
    except TokenError as e:
        logger.warning(f"Invalid token: {e}")
        raise HTTPException(
            status_code=401,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )

    scopes = payload.get("scope", "").split() if payload.get("scope") else []

    return AuthenticatedUser(
        subject=payload["sub"],
        scopes=scopes,
        claims=payload,
    )


def require_auth(
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
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
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
