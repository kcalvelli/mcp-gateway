"""Base OAuth provider interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class OAuthUser:
    """User information from OAuth provider."""

    provider: str  # e.g., "github"
    id: str  # Provider-specific user ID
    username: str  # Display username
    email: str | None = None
    avatar_url: str | None = None
    raw_data: dict[str, Any] | None = None

    @property
    def subject(self) -> str:
        """Return the subject identifier for JWT tokens."""
        return f"{self.provider}:{self.username}"


class OAuthProvider(ABC):
    """Abstract base class for OAuth providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'github')."""
        pass

    @abstractmethod
    def get_authorization_url(
        self,
        redirect_uri: str,
        state: str,
        code_challenge: str | None = None,
        code_challenge_method: str | None = None,
    ) -> str:
        """
        Generate the authorization URL for the OAuth flow.

        Args:
            redirect_uri: Where to redirect after authorization
            state: CSRF protection state
            code_challenge: PKCE code challenge
            code_challenge_method: PKCE challenge method (e.g., "S256")

        Returns:
            Authorization URL to redirect the user to
        """
        pass

    @abstractmethod
    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> str:
        """
        Exchange authorization code for access token.

        Args:
            code: Authorization code from callback
            redirect_uri: Same redirect_uri used in authorization
            code_verifier: PKCE code verifier

        Returns:
            Access token from the provider
        """
        pass

    @abstractmethod
    async def get_user_info(self, access_token: str) -> OAuthUser:
        """
        Fetch user information using the access token.

        Args:
            access_token: Provider access token

        Returns:
            User information
        """
        pass
