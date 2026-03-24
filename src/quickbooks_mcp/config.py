"""Configuration management for QuickBooks MCP Server."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field


# Default paths
DEFAULT_TOKEN_STORE_DIR = Path.home() / ".quickbooks-mcp"
DEFAULT_TOKEN_STORE_PATH = DEFAULT_TOKEN_STORE_DIR / "tokens.json"
DEFAULT_REDIRECT_URI = "http://localhost:8080/callback"

# QuickBooks API endpoints
QBO_AUTH_URL = "https://appcenter.intuit.com/connect/oauth2"
QBO_TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
QBO_REVOKE_URL = "https://developer.api.intuit.com/v2/oauth2/tokens/revoke"
QBO_BASE_URL = "https://quickbooks.api.intuit.com/v3/company"
QBO_SANDBOX_BASE_URL = "https://sandbox-quickbooks.api.intuit.com/v3/company"
QBO_SCOPES = "com.intuit.quickbooks.accounting"

# Lemon Squeezy validation
LEMON_SQUEEZY_VALIDATE_URL = "https://api.lemonsqueezy.com/v1/licenses/validate"

# Rate limiting
MAX_REQUESTS_PER_MINUTE = 500  # QuickBooks throttle limit
REQUEST_TIMEOUT_SECONDS = 30


class Config(BaseModel):
    """Application configuration loaded from environment variables."""

    qbo_client_id: str = Field(default="", description="QuickBooks OAuth2 Client ID")
    qbo_client_secret: str = Field(default="", description="QuickBooks OAuth2 Client Secret")
    qbo_redirect_uri: str = Field(
        default=DEFAULT_REDIRECT_URI, description="OAuth2 redirect URI"
    )
    qbo_realm_id: str = Field(default="", description="QuickBooks company/realm ID")
    license_key: str = Field(default="", description="Lemon Squeezy premium license key")
    token_store_path: Path = Field(
        default=DEFAULT_TOKEN_STORE_PATH, description="Path to encrypted token storage"
    )
    log_level: str = Field(default="INFO", description="Logging level")
    sandbox: bool = Field(default=False, description="Use QuickBooks sandbox environment")

    @property
    def base_url(self) -> str:
        """Get the appropriate QuickBooks API base URL."""
        if self.sandbox:
            return f"{QBO_SANDBOX_BASE_URL}/{self.qbo_realm_id}"
        return f"{QBO_BASE_URL}/{self.qbo_realm_id}"

    @property
    def is_configured(self) -> bool:
        """Check if minimum required configuration is present."""
        return bool(self.qbo_client_id and self.qbo_client_secret and self.qbo_realm_id)


def load_config() -> Config:
    """Load configuration from environment variables.

    Environment variables:
        QBO_CLIENT_ID: QuickBooks OAuth2 Client ID
        QBO_CLIENT_SECRET: QuickBooks OAuth2 Client Secret
        QBO_REDIRECT_URI: OAuth2 redirect URI (default: http://localhost:8080/callback)
        QBO_REALM_ID: QuickBooks company/realm ID
        LICENSE_KEY: Lemon Squeezy premium license key (optional)
        TOKEN_STORE_PATH: Path to token storage file
        LOG_LEVEL: Logging level (default: INFO)
        QBO_SANDBOX: Use sandbox environment (default: false)
    """
    return Config(
        qbo_client_id=os.environ.get("QBO_CLIENT_ID", ""),
        qbo_client_secret=os.environ.get("QBO_CLIENT_SECRET", ""),
        qbo_redirect_uri=os.environ.get("QBO_REDIRECT_URI", DEFAULT_REDIRECT_URI),
        qbo_realm_id=os.environ.get("QBO_REALM_ID", ""),
        license_key=os.environ.get("LICENSE_KEY", ""),
        token_store_path=Path(
            os.environ.get("TOKEN_STORE_PATH", str(DEFAULT_TOKEN_STORE_PATH))
        ),
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
        sandbox=os.environ.get("QBO_SANDBOX", "false").lower() in ("true", "1", "yes"),
    )
