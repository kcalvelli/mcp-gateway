"""JWT token generation and validation for MCP Gateway."""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from .config import get_auth_config


class TokenError(Exception):
    """Token validation or generation error."""

    pass


def create_access_token(
    subject: str,
    scopes: list[str] | None = None,
    expires_delta: timedelta | None = None,
    additional_claims: dict[str, Any] | None = None,
) -> str:
    """
    Create a JWT access token.

    Args:
        subject: Token subject (e.g., "github:username")
        scopes: List of permission scopes
        expires_delta: Custom expiration time
        additional_claims: Additional JWT claims

    Returns:
        Encoded JWT token string
    """
    config = get_auth_config()

    if expires_delta is None:
        expires_delta = timedelta(minutes=config.access_token_expire_minutes)

    now = datetime.now(timezone.utc)
    expire = now + expires_delta

    claims = {
        "sub": subject,
        "iss": "mcp-gateway",
        "aud": "mcp-client",
        "exp": expire,
        "iat": now,
        "jti": secrets.token_urlsafe(16),  # Unique token ID
    }

    if scopes:
        claims["scope"] = " ".join(scopes)

    if additional_claims:
        claims.update(additional_claims)

    return jwt.encode(claims, config.jwt_secret, algorithm=config.jwt_algorithm)


def create_refresh_token(subject: str) -> str:
    """
    Create a JWT refresh token.

    Args:
        subject: Token subject (e.g., "github:username")

    Returns:
        Encoded JWT refresh token string
    """
    config = get_auth_config()
    expires_delta = timedelta(days=config.refresh_token_expire_days)

    return create_access_token(
        subject=subject,
        expires_delta=expires_delta,
        additional_claims={"type": "refresh"},
    )


def verify_token(token: str) -> dict[str, Any]:
    """
    Verify and decode a JWT token.

    Args:
        token: JWT token string

    Returns:
        Decoded token claims

    Raises:
        TokenError: If token is invalid or expired
    """
    config = get_auth_config()

    try:
        payload = jwt.decode(
            token,
            config.jwt_secret,
            algorithms=[config.jwt_algorithm],
            audience="mcp-client",
            issuer="mcp-gateway",
        )
        return payload
    except JWTError as e:
        raise TokenError(f"Invalid token: {e}")


def is_refresh_token(payload: dict[str, Any]) -> bool:
    """Check if a token payload is a refresh token."""
    return payload.get("type") == "refresh"


def get_token_scopes(payload: dict[str, Any]) -> list[str]:
    """Extract scopes from token payload."""
    scope_str = payload.get("scope", "")
    return scope_str.split() if scope_str else []
