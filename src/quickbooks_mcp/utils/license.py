"""Lemon Squeezy license key validation for premium features."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx

from quickbooks_mcp.config import LEMON_SQUEEZY_VALIDATE_URL

logger = logging.getLogger(__name__)

# Cache validation for 1 hour to avoid hitting Lemon Squeezy on every tool call
_CACHE_TTL_SECONDS = 3600


@dataclass
class LicenseStatus:
    """Result of a license validation check."""

    valid: bool
    license_key: str
    customer_name: str
    status: str  # "active", "inactive", "expired", "disabled"
    error: str

    @property
    def is_premium(self) -> bool:
        """Check if the license grants premium access."""
        return self.valid and self.status == "active"


# Module-level cache
_cached_status: LicenseStatus | None = None
_cache_timestamp: float = 0.0


async def validate_license(license_key: str) -> LicenseStatus:
    """Validate a Lemon Squeezy license key.

    Results are cached for 1 hour to minimize API calls.

    Args:
        license_key: The license key to validate.

    Returns:
        LicenseStatus with validation result.
    """
    global _cached_status, _cache_timestamp  # noqa: PLW0603

    if not license_key:
        return LicenseStatus(
            valid=False,
            license_key="",
            customer_name="",
            status="missing",
            error="No license key provided. Premium features require a license key.",
        )

    # Return cached result if still valid
    now = time.monotonic()
    if (
        _cached_status is not None
        and _cached_status.license_key == license_key
        and (now - _cache_timestamp) < _CACHE_TTL_SECONDS
    ):
        return _cached_status

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                LEMON_SQUEEZY_VALIDATE_URL,
                json={
                    "license_key": license_key,
                    "instance_name": "quickbooks-mcp",
                },
                headers={"Accept": "application/json"},
            )

        if response.status_code != 200:
            status = LicenseStatus(
                valid=False,
                license_key=license_key,
                customer_name="",
                status="error",
                error=f"License validation failed (HTTP {response.status_code})",
            )
            _cached_status = status
            _cache_timestamp = now
            return status

        data = response.json()
        valid = data.get("valid", False)
        meta = data.get("meta", {})
        license_data = data.get("license_key", {})

        status = LicenseStatus(
            valid=valid,
            license_key=license_key,
            customer_name=meta.get("customer_name", ""),
            status=license_data.get("status", "unknown"),
            error="" if valid else "License is not active",
        )

    except httpx.TimeoutException:
        # On timeout, allow access if we had a previous valid cache
        if _cached_status is not None and _cached_status.valid:
            logger.warning("License validation timed out, using cached valid result")
            return _cached_status

        status = LicenseStatus(
            valid=False,
            license_key=license_key,
            customer_name="",
            status="timeout",
            error="License validation timed out. Please check your internet connection.",
        )

    except Exception as exc:
        logger.warning("License validation error: %s", exc)
        # Graceful degradation: if we had a previous valid cache, keep it
        if _cached_status is not None and _cached_status.valid:
            return _cached_status

        status = LicenseStatus(
            valid=False,
            license_key=license_key,
            customer_name="",
            status="error",
            error=f"License validation error: {exc}",
        )

    _cached_status = status
    _cache_timestamp = now
    return status


def require_premium(license_key: str) -> str | None:
    """Synchronous check if premium features are available.

    This uses the cached validation result. Returns None if premium is
    available, or an error message string if not.

    Args:
        license_key: The license key to check.

    Returns:
        None if premium access is granted, or an error message.
    """
    if _cached_status is not None and _cached_status.license_key == license_key:
        if _cached_status.is_premium:
            return None
        return _cached_status.error

    if not license_key:
        return (
            "This is a premium feature. Upgrade at https://lewenterprises.com/quickbooks-mcp "
            "to unlock financial reports, write operations, and analytics. "
            "Set the LICENSE_KEY environment variable after purchase."
        )

    return None  # Will be validated async on first use


def clear_cache() -> None:
    """Clear the license validation cache (used in testing)."""
    global _cached_status, _cache_timestamp  # noqa: PLW0603
    _cached_status = None
    _cache_timestamp = 0.0
