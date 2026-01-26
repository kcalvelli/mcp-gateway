"""GitHub OAuth provider for MCP Gateway."""

import logging
from urllib.parse import urlencode

import httpx

from ..config import get_auth_config
from .base import OAuthProvider, OAuthUser

logger = logging.getLogger(__name__)

# GitHub OAuth URLs
GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"


class GitHubProviderError(Exception):
    """GitHub OAuth error."""

    pass


class GitHubProvider(OAuthProvider):
    """GitHub OAuth2 provider."""

    @property
    def name(self) -> str:
        return "github"

    def get_authorization_url(
        self,
        redirect_uri: str,
        state: str,
        code_challenge: str | None = None,
        code_challenge_method: str | None = None,
    ) -> str:
        """Generate GitHub authorization URL."""
        config = get_auth_config()

        params = {
            "client_id": config.github_client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": "read:user user:email",  # Request user profile and email
        }

        # GitHub doesn't support PKCE natively, but we include it for compliance
        # with the OAuth flow pattern
        if code_challenge and code_challenge_method:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = code_challenge_method

        return f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> str:
        """Exchange authorization code for GitHub access token."""
        config = get_auth_config()

        data = {
            "client_id": config.github_client_id,
            "client_secret": config.github_client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        }

        if code_verifier:
            data["code_verifier"] = code_verifier

        async with httpx.AsyncClient() as client:
            response = await client.post(
                GITHUB_TOKEN_URL,
                data=data,
                headers={"Accept": "application/json"},
            )

            if response.status_code != 200:
                logger.error(f"GitHub token exchange failed: {response.text}")
                raise GitHubProviderError(f"Token exchange failed: {response.status_code}")

            token_data = response.json()

            if "error" in token_data:
                error = token_data.get("error_description", token_data["error"])
                logger.error(f"GitHub token error: {error}")
                raise GitHubProviderError(f"Token error: {error}")

            access_token = token_data.get("access_token")
            if not access_token:
                raise GitHubProviderError("No access token in response")

            return access_token

    async def get_user_info(self, access_token: str) -> OAuthUser:
        """Fetch user information from GitHub."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                GITHUB_USER_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )

            if response.status_code != 200:
                logger.error(f"GitHub user info failed: {response.text}")
                raise GitHubProviderError(f"User info failed: {response.status_code}")

            user_data = response.json()

            return OAuthUser(
                provider="github",
                id=str(user_data["id"]),
                username=user_data["login"],
                email=user_data.get("email"),
                avatar_url=user_data.get("avatar_url"),
                raw_data=user_data,
            )
