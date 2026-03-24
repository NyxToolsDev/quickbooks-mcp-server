"""QuickBooks Online REST API client with async HTTP, auth refresh, and rate limiting."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from quickbooks_mcp.auth.oauth import OAuthManager
from quickbooks_mcp.config import Config, MAX_REQUESTS_PER_MINUTE, REQUEST_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


class QBOAPIError(Exception):
    """Raised when the QuickBooks API returns an error."""

    def __init__(self, status_code: int, message: str, detail: str = "") -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"QuickBooks API error (HTTP {status_code}): {message}")


class QBOClient:
    """Async client for the QuickBooks Online REST API.

    Handles authentication header injection, automatic token refresh on 401,
    rate limiting, and structured error responses.
    """

    def __init__(self, config: Config, oauth: OAuthManager) -> None:
        self._config = config
        self._oauth = oauth
        self._request_timestamps: list[float] = []
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=REQUEST_TIMEOUT_SECONDS,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    async def _throttle(self) -> None:
        """Simple rate limiting to stay under QuickBooks throttle limits."""
        now = time.monotonic()
        # Remove timestamps older than 60 seconds
        self._request_timestamps = [
            ts for ts in self._request_timestamps if now - ts < 60.0
        ]
        if len(self._request_timestamps) >= MAX_REQUESTS_PER_MINUTE:
            oldest = self._request_timestamps[0]
            wait = 60.0 - (now - oldest) + 0.1
            if wait > 0:
                logger.debug("Rate limit throttle: waiting %.1fs", wait)
                await asyncio.sleep(wait)
        self._request_timestamps.append(time.monotonic())

    async def _auth_headers(self) -> dict[str, str]:
        """Get authorization headers with a valid access token."""
        token = await self._oauth.get_access_token()
        return {"Authorization": f"Bearer {token}"}

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        retry_on_401: bool = True,
    ) -> dict[str, Any]:
        """Make an authenticated request to the QuickBooks API.

        Args:
            method: HTTP method (GET, POST, etc.).
            path: API path relative to the company base URL.
            params: Query parameters.
            json_body: JSON request body.
            retry_on_401: Whether to retry once on 401 after token refresh.

        Returns:
            Parsed JSON response body.

        Raises:
            QBOAPIError: On any non-success HTTP status.
        """
        await self._throttle()

        url = f"{self._config.base_url}/{path.lstrip('/')}"
        headers = await self._auth_headers()
        client = await self._get_client()

        response = await client.request(
            method=method,
            url=url,
            params=params,
            json=json_body,
            headers=headers,
        )

        # Handle token expiry: refresh and retry once
        if response.status_code == 401 and retry_on_401:
            logger.info("Received 401, attempting token refresh and retry")
            headers = await self._auth_headers()
            response = await client.request(
                method=method,
                url=url,
                params=params,
                json=json_body,
                headers=headers,
            )

        if response.status_code == 429:
            raise QBOAPIError(
                429,
                "Rate limited by QuickBooks. Please wait and try again.",
                detail=response.text,
            )

        if response.status_code >= 400:
            detail = ""
            try:
                error_data = response.json()
                if "Fault" in error_data:
                    errors = error_data["Fault"].get("Error", [])
                    if errors:
                        detail = errors[0].get("Detail", errors[0].get("Message", ""))
            except Exception:
                detail = response.text

            raise QBOAPIError(
                response.status_code,
                detail or f"Request failed: {response.text[:200]}",
                detail=response.text,
            )

        return response.json()  # type: ignore[no-any-return]

    async def query(self, query_string: str) -> list[dict[str, Any]]:
        """Execute a QuickBooks Query Language query.

        Args:
            query_string: The QBO query (e.g., "SELECT * FROM Invoice").

        Returns:
            List of matching entity dicts.
        """
        data = await self._request("GET", "query", params={"query": query_string})
        query_response = data.get("QueryResponse", {})

        # The entity key in QueryResponse matches the entity type queried
        for key, value in query_response.items():
            if isinstance(value, list):
                return value

        return []

    async def query_count(self, query_string: str) -> int:
        """Execute a COUNT query.

        Args:
            query_string: A SELECT COUNT(*) FROM ... query.

        Returns:
            The count result.
        """
        data = await self._request("GET", "query", params={"query": query_string})
        return int(data.get("QueryResponse", {}).get("totalCount", 0))

    async def get(self, entity: str, entity_id: str) -> dict[str, Any]:
        """Get a single entity by ID.

        Args:
            entity: Entity type (e.g., "invoice", "customer").
            entity_id: The entity ID.

        Returns:
            The entity data dict.
        """
        data = await self._request("GET", f"{entity}/{entity_id}")
        # QBO wraps the response in the entity type name (capitalized)
        entity_key = entity.capitalize()
        return data.get(entity_key, data)

    async def create(self, entity: str, body: dict[str, Any]) -> dict[str, Any]:
        """Create a new entity.

        Args:
            entity: Entity type (e.g., "invoice", "payment").
            body: The entity data to create.

        Returns:
            The created entity data.
        """
        data = await self._request("POST", entity, json_body=body)
        entity_key = entity.capitalize()
        return data.get(entity_key, data)

    async def update(self, entity: str, body: dict[str, Any]) -> dict[str, Any]:
        """Update an existing entity.

        Args:
            entity: Entity type.
            body: The full entity data including Id and SyncToken.

        Returns:
            The updated entity data.
        """
        data = await self._request("POST", entity, json_body=body)
        entity_key = entity.capitalize()
        return data.get(entity_key, data)

    async def get_report(
        self,
        report_name: str,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Fetch a QuickBooks report.

        Args:
            report_name: Report name (e.g., "ProfitAndLoss", "BalanceSheet").
            params: Report parameters (date ranges, etc.).

        Returns:
            The report data dict.
        """
        return await self._request("GET", f"reports/{report_name}", params=params)
