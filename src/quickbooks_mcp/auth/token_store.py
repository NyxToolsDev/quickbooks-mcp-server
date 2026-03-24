"""Secure token persistence with encryption at rest."""

from __future__ import annotations

import base64
import json
import logging
import os
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class StoredTokens(BaseModel):
    """Token data stored on disk."""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_at: float = Field(description="Unix timestamp when access token expires")
    realm_id: str = ""

    @property
    def is_expired(self) -> bool:
        """Check if the access token has expired (with 5-minute buffer)."""
        buffer_seconds = 300  # Refresh 5 minutes before expiry
        return datetime.now(tz=timezone.utc).timestamp() >= (self.expires_at - buffer_seconds)


class TokenStore:
    """Encrypted local storage for OAuth tokens.

    Tokens are encrypted using Fernet symmetric encryption with a key
    derived from machine-specific information. This prevents tokens from
    being usable if the file is copied to another machine.
    """

    def __init__(self, store_path: Path) -> None:
        self._store_path = store_path
        self._fernet = self._create_fernet()

    def _get_machine_seed(self) -> bytes:
        """Generate a machine-specific seed for key derivation.

        Uses the machine's hostname and platform info to create a seed
        that is unique to this machine. This means tokens encrypted on
        one machine cannot be decrypted on another.
        """
        node = platform.node()
        system = platform.system()
        machine = platform.machine()
        seed = f"quickbooks-mcp:{node}:{system}:{machine}"
        return seed.encode("utf-8")

    def _create_fernet(self) -> Fernet:
        """Create a Fernet cipher using a machine-derived key."""
        salt = b"quickbooks-mcp-token-store-v1"
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480_000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(self._get_machine_seed()))
        return Fernet(key)

    def store(self, tokens: StoredTokens) -> None:
        """Encrypt and save tokens to disk.

        Args:
            tokens: The token data to store.
        """
        self._store_path.parent.mkdir(parents=True, exist_ok=True)

        payload = tokens.model_dump_json()
        encrypted = self._fernet.encrypt(payload.encode("utf-8"))

        self._store_path.write_bytes(encrypted)

        # Restrict file permissions (best effort on Windows)
        try:
            os.chmod(self._store_path, 0o600)
        except OSError:
            logger.debug("Could not set restrictive file permissions (expected on Windows)")

        logger.info("Tokens saved to %s", self._store_path)

    def load(self) -> StoredTokens | None:
        """Load and decrypt tokens from disk.

        Returns:
            The stored tokens, or None if no tokens are found or decryption fails.
        """
        if not self._store_path.exists():
            logger.debug("Token store not found at %s", self._store_path)
            return None

        try:
            encrypted = self._store_path.read_bytes()
            decrypted = self._fernet.decrypt(encrypted)
            data: dict[str, Any] = json.loads(decrypted.decode("utf-8"))
            return StoredTokens(**data)
        except Exception:
            logger.warning(
                "Failed to decrypt tokens from %s. "
                "Tokens may have been created on a different machine or are corrupted. "
                "Please re-authorize with: quickbooks-mcp-setup",
                self._store_path,
            )
            return None

    def clear(self) -> None:
        """Remove stored tokens."""
        if self._store_path.exists():
            self._store_path.unlink()
            logger.info("Tokens cleared from %s", self._store_path)

    @property
    def has_tokens(self) -> bool:
        """Check if a token file exists."""
        return self._store_path.exists()
