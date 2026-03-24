"""QuickBooks OAuth2 authorization code flow."""

from __future__ import annotations

import logging
import secrets
import time
from urllib.parse import urlencode

import httpx

from quickbooks_mcp.auth.token_store import StoredTokens, TokenStore
from quickbooks_mcp.config import (
    QBO_AUTH_URL,
    QBO_REVOKE_URL,
    QBO_SCOPES,
    QBO_TOKEN_URL,
    Config,
)

logger = logging.getLogger(__name__)


class OAuthError(Exception):
    """Raised when an OAuth operation fails."""


class OAuthManager:
    """Manages the QuickBooks OAuth2 lifecycle.

    Handles authorization URL generation, token exchange, automatic
    refresh, and revocation.
    """

    def __init__(self, config: Config, token_store: TokenStore) -> None:
        self._config = config
        self._token_store = token_store
        self._cached_tokens: StoredTokens | None = None

    def get_authorization_url(self) -> tuple[str, str]:
        """Generate the OAuth2 authorization URL.

        Returns:
            A tuple of (authorization_url, state) where state should be
            stored for CSRF verification on callback.
        """
        state = secrets.token_urlsafe(32)
        params = {
            "client_id": self._config.qbo_client_id,
            "response_type": "code",
            "scope": QBO_SCOPES,
            "redirect_uri": self._config.qbo_redirect_uri,
            "state": state,
        }
        url = f"{QBO_AUTH_URL}?{urlencode(params)}"
        return url, state

    async def exchange_code(self, authorization_code: str, realm_id: str) -> StoredTokens:
        """Exchange an authorization code for access and refresh tokens.

        Args:
            authorization_code: The code received from the OAuth callback.
            realm_id: The QuickBooks company/realm ID from the callback.

        Returns:
            The stored token data.

        Raises:
            OAuthError: If the token exchange fails.
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                QBO_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": authorization_code,
                    "redirect_uri": self._config.qbo_redirect_uri,
                },
                auth=(self._config.qbo_client_id, self._config.qbo_client_secret),
                headers={"Accept": "application/json"},
            )

        if response.status_code != 200:
            raise OAuthError(
                f"Token exchange failed (HTTP {response.status_code}): {response.text}"
            )

        data = response.json()
        tokens = StoredTokens(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            token_type=data.get("token_type", "Bearer"),
            expires_at=time.time() + data.get("expires_in", 3600),
            realm_id=realm_id,
        )

        self._token_store.store(tokens)
        self._cached_tokens = tokens
        logger.info("OAuth tokens obtained and stored successfully")
        return tokens

    async def get_access_token(self) -> str:
        """Get a valid access token, refreshing if necessary.

        Returns:
            A valid access token string.

        Raises:
            OAuthError: If no tokens are available or refresh fails.
        """
        tokens = self._cached_tokens or self._token_store.load()

        if tokens is None:
            raise OAuthError(
                "No QuickBooks tokens found. Please run the OAuth setup first: "
                "python -m quickbooks_mcp.scripts.setup_oauth"
            )

        if tokens.is_expired:
            logger.info("Access token expired, refreshing...")
            tokens = await self._refresh_token(tokens.refresh_token, tokens.realm_id)

        self._cached_tokens = tokens
        return tokens.access_token

    async def _refresh_token(self, refresh_token: str, realm_id: str) -> StoredTokens:
        """Refresh an expired access token.

        Args:
            refresh_token: The refresh token to use.
            realm_id: The QuickBooks company/realm ID.

        Returns:
            Updated token data.

        Raises:
            OAuthError: If the refresh fails.
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                QBO_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
                auth=(self._config.qbo_client_id, self._config.qbo_client_secret),
                headers={"Accept": "application/json"},
            )

        if response.status_code != 200:
            self._cached_tokens = None
            raise OAuthError(
                f"Token refresh failed (HTTP {response.status_code}): {response.text}. "
                "Please re-authorize with: python -m quickbooks_mcp.scripts.setup_oauth"
            )

        data = response.json()
        tokens = StoredTokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", refresh_token),
            token_type=data.get("token_type", "Bearer"),
            expires_at=time.time() + data.get("expires_in", 3600),
            realm_id=realm_id,
        )

        self._token_store.store(tokens)
        self._cached_tokens = tokens
        logger.info("Access token refreshed successfully")
        return tokens

    async def revoke(self) -> None:
        """Revoke the current refresh token and clear stored tokens."""
        tokens = self._cached_tokens or self._token_store.load()
        if tokens is None:
            logger.info("No tokens to revoke")
            return

        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    QBO_REVOKE_URL,
                    json={"token": tokens.refresh_token},
                    auth=(self._config.qbo_client_id, self._config.qbo_client_secret),
                    headers={"Accept": "application/json"},
                )
        except Exception:
            logger.warning("Failed to revoke token with Intuit (may already be expired)")

        self._token_store.clear()
        self._cached_tokens = None
        logger.info("Tokens revoked and cleared")

    @property
    def is_authenticated(self) -> bool:
        """Check if we have stored tokens (may need refresh)."""
        if self._cached_tokens is not None:
            return True
        return self._token_store.has_tokens
