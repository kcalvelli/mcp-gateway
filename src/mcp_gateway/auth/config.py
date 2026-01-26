"""OAuth2 configuration for MCP Gateway."""

import os
import secrets
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path


@dataclass
class AuthConfig:
    """OAuth2 authentication configuration."""

    # Whether OAuth is enabled
    enabled: bool = False

    # OAuth provider (currently only "github" supported)
    provider: str = "github"

    # GitHub OAuth credentials
    github_client_id: str = ""
    github_client_secret: str = ""

    # JWT configuration
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7

    # Optional: Allowlist of GitHub usernames (empty = allow all authenticated users)
    allowed_users: list[str] = field(default_factory=list)

    # Base URL for OAuth callbacks (auto-detected if not set)
    base_url: str = ""

    def __post_init__(self):
        """Validate configuration."""
        if self.enabled:
            if not self.github_client_id:
                raise ValueError("MCP_GATEWAY_GITHUB_CLIENT_ID required when OAuth enabled")
            if not self.github_client_secret:
                raise ValueError("MCP_GATEWAY_GITHUB_CLIENT_SECRET required when OAuth enabled")
            if not self.jwt_secret:
                # Generate a random secret if not provided (not recommended for production)
                self.jwt_secret = secrets.token_urlsafe(32)


def _read_secret_file(path: str) -> str:
    """Read a secret from a file path."""
    try:
        return Path(path).read_text().strip()
    except (FileNotFoundError, PermissionError):
        return ""


@lru_cache
def get_auth_config() -> AuthConfig:
    """Load authentication configuration from environment variables."""

    # Check if OAuth is enabled
    enabled = os.environ.get("MCP_GATEWAY_OAUTH_ENABLED", "").lower() in ("true", "1", "yes")

    if not enabled:
        return AuthConfig(enabled=False)

    # Load GitHub credentials (support both env var and file path)
    github_client_id = os.environ.get("MCP_GATEWAY_GITHUB_CLIENT_ID", "")

    # Client secret: check env var first, then file path
    github_client_secret = os.environ.get("MCP_GATEWAY_GITHUB_CLIENT_SECRET", "")
    if not github_client_secret:
        secret_file = os.environ.get("MCP_GATEWAY_GITHUB_CLIENT_SECRET_FILE", "")
        if secret_file:
            github_client_secret = _read_secret_file(secret_file)

    # JWT secret: check env var first, then file path
    jwt_secret = os.environ.get("MCP_GATEWAY_JWT_SECRET", "")
    if not jwt_secret:
        secret_file = os.environ.get("MCP_GATEWAY_JWT_SECRET_FILE", "")
        if secret_file:
            jwt_secret = _read_secret_file(secret_file)

    # Allowed users (comma-separated GitHub usernames)
    allowed_users_str = os.environ.get("MCP_GATEWAY_ALLOWED_USERS", "")
    allowed_users = [u.strip() for u in allowed_users_str.split(",") if u.strip()]

    # Base URL for callbacks
    base_url = os.environ.get("MCP_GATEWAY_BASE_URL", "")

    return AuthConfig(
        enabled=enabled,
        provider=os.environ.get("MCP_GATEWAY_OAUTH_PROVIDER", "github"),
        github_client_id=github_client_id,
        github_client_secret=github_client_secret,
        jwt_secret=jwt_secret,
        jwt_algorithm=os.environ.get("MCP_GATEWAY_JWT_ALGORITHM", "HS256"),
        access_token_expire_minutes=int(os.environ.get("MCP_GATEWAY_TOKEN_EXPIRE_MINUTES", "60")),
        refresh_token_expire_days=int(os.environ.get("MCP_GATEWAY_REFRESH_TOKEN_DAYS", "7")),
        allowed_users=allowed_users,
        base_url=base_url,
    )
