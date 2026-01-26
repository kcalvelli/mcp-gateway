"""OAuth2 providers for MCP Gateway."""

from .base import OAuthProvider
from .github import GitHubProvider

__all__ = ["OAuthProvider", "GitHubProvider"]
