from collections.abc import Mapping
from typing import Any

import httpx
from loguru import logger

from src.config import Settings
from src.domain.exceptions import ProviderError


class TravelPayoutsError(ProviderError):
    """Base exception for TravelPayouts client errors."""
    pass


class TravelPayoutsAuthenticationError(TravelPayoutsError):
    """Raised when authentication fails (HTTP 401 or 403)."""
    pass


class TravelPayoutsRateLimitError(TravelPayoutsError):
    """Raised when rate limits are exceeded (HTTP 429)."""
    pass


class TravelPayoutsNetworkError(TravelPayoutsError):
    """Raised when a network failure occurs (timeouts, connection issues)."""
    pass


class TravelPayoutsGraphQLError(TravelPayoutsError):
    """Raised when the GraphQL API returns error payloads."""
    def __init__(self, errors: list[dict[str, Any]]):
        super().__init__(f"GraphQL Errors: {errors}")
        self.errors = errors


class TravelPayoutsUnexpectedResponse(TravelPayoutsError):  # noqa: N818
    """Raised when the API returns an unexpected or malformed response."""
    pass


class TravelPayoutsClient:
    """
    Low-level HTTP client responsible for communicating with the TravelPayouts GraphQL API.
    Decoupled from application business logic, entities, and database storage.
    """
    def __init__(self, settings: Settings):
        self.settings = settings
        if not settings.TRAVELPAYOUTS_API_TOKEN:
            raise TravelPayoutsAuthenticationError("TRAVELPAYOUTS_API_TOKEN is not configured.")
        
        self.base_url = settings.TRAVELPAYOUTS_BASE_URL
        self.token = settings.TRAVELPAYOUTS_API_TOKEN
        self.timeout = settings.GRAPHQL_TIMEOUT_SECONDS
        
        # Configure request headers
        self.headers = {
            "X-Access-Token": self.token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        
        # Reusable async httpx client reusing connection pool
        self._client = httpx.AsyncClient(
            headers=self.headers,
            timeout=self.timeout
        )

    async def execute(
        self, query: str, variables: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Executes a GraphQL query against the TravelPayouts endpoint.
        Returns the raw parsed JSON response.
        """
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        logger.debug(f"Executing TravelPayouts GraphQL query to {self.base_url}")
        
        try:
            response = await self._client.post(self.base_url, json=payload)
        except httpx.TimeoutException as e:
            logger.error(f"TravelPayouts API request timed out: {e}")
            raise TravelPayoutsNetworkError(f"Request timed out: {e}") from e
        except httpx.RequestError as e:
            logger.error(f"TravelPayouts network connection error: {e}")
            raise TravelPayoutsNetworkError(f"Network connection failed: {e}") from e

        # Handle HTTP status codes
        if response.status_code in (401, 403):
            logger.error(f"TravelPayouts authentication failed with code {response.status_code}")
            raise TravelPayoutsAuthenticationError(
                f"Authentication failed (HTTP {response.status_code}): {response.text}"
            )
        
        if response.status_code == 429:
            logger.error("TravelPayouts rate limit exceeded (HTTP 429)")
            raise TravelPayoutsRateLimitError("Rate limit exceeded (HTTP 429)")
        
        if response.status_code >= 500:
            logger.error(
                f"TravelPayouts server error (HTTP {response.status_code}): {response.text}"
            )
            raise TravelPayoutsUnexpectedResponse(
                f"Server error (HTTP {response.status_code}): {response.text}"
            )
        
        if response.status_code != 200:
            logger.error(
                f"TravelPayouts unexpected status code {response.status_code}: {response.text}"
            )
            raise TravelPayoutsUnexpectedResponse(
                f"Unexpected response code (HTTP {response.status_code}): {response.text}"
            )

        # Parse JSON response
        try:
            data = response.json()
        except ValueError as e:
            logger.error(f"TravelPayouts returned invalid JSON: {e}")
            raise TravelPayoutsUnexpectedResponse(f"Failed to parse JSON response: {e}") from e

        # Handle GraphQL validation/runtime errors inside the payload
        if "errors" in data:
            logger.error(f"TravelPayouts returned GraphQL errors: {data['errors']}")
            raise TravelPayoutsGraphQLError(data["errors"])

        return data

    async def close(self) -> None:
        """Closes the underlying HTTPX async client connection pool."""
        await self._client.aclose()
