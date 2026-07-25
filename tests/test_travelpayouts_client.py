from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.adapters.providers.travelpayouts_client import (
    TravelPayoutsAuthenticationError,
    TravelPayoutsClient,
    TravelPayoutsGraphQLError,
    TravelPayoutsNetworkError,
    TravelPayoutsRateLimitError,
    TravelPayoutsUnexpectedResponse,
)
from src.config import Settings


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        TRAVELPAYOUTS_API_TOKEN="mock_token_12345",
        TRAVELPAYOUTS_BASE_URL="https://api.travelpayouts.com/graphql/v1/query",
        GRAPHQL_TIMEOUT_SECONDS=5,
    )


@pytest.mark.asyncio
async def test_client_init_missing_token():
    # Instantiate Settings without a token
    settings = Settings(TRAVELPAYOUTS_API_TOKEN=None)
    with pytest.raises(TravelPayoutsAuthenticationError) as exc_info:
        TravelPayoutsClient(settings)
    assert "TRAVELPAYOUTS_API_TOKEN is not configured" in str(exc_info.value)


@pytest.mark.asyncio
async def test_execute_success(test_settings):
    client = TravelPayoutsClient(test_settings)
    
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    expected_data = {"data": {"prices_one_way": [{"value": 100}]}}
    mock_response.json.return_value = expected_data
    
    with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        
        query = "query { prices_one_way { value } }"
        variables = {"param": "test"}
        
        result = await client.execute(query, variables)
        
        assert result == expected_data
        mock_post.assert_called_once_with(
            "https://api.travelpayouts.com/graphql/v1/query",
            json={"query": query, "variables": variables}
        )
        
    await client.close()


@pytest.mark.asyncio
async def test_execute_unauthorized_401(test_settings):
    client = TravelPayoutsClient(test_settings)
    
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 401
    mock_response.text = "Unauthorized"
    
    with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        
        with pytest.raises(TravelPayoutsAuthenticationError) as exc_info:
            await client.execute("query {}")
        assert "Authentication failed" in str(exc_info.value)
        
    await client.close()


@pytest.mark.asyncio
async def test_execute_forbidden_403(test_settings):
    client = TravelPayoutsClient(test_settings)
    
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 403
    mock_response.text = "Forbidden"
    
    with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        
        with pytest.raises(TravelPayoutsAuthenticationError) as exc_info:
            await client.execute("query {}")
        assert "Authentication failed" in str(exc_info.value)
        
    await client.close()


@pytest.mark.asyncio
async def test_execute_rate_limiting_429(test_settings):
    client = TravelPayoutsClient(test_settings)
    
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 429
    mock_response.text = "Too Many Requests"
    
    with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        
        with pytest.raises(TravelPayoutsRateLimitError) as exc_info:
            await client.execute("query {}")
        assert "Rate limit exceeded" in str(exc_info.value)
        
    await client.close()


@pytest.mark.asyncio
async def test_execute_server_error_500(test_settings):
    client = TravelPayoutsClient(test_settings)
    
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"
    
    with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        
        with pytest.raises(TravelPayoutsUnexpectedResponse) as exc_info:
            await client.execute("query {}")
        assert "Server error" in str(exc_info.value)
        
    await client.close()


@pytest.mark.asyncio
async def test_execute_unexpected_status_404(test_settings):
    client = TravelPayoutsClient(test_settings)
    
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 404
    mock_response.text = "Not Found"
    
    with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        
        with pytest.raises(TravelPayoutsUnexpectedResponse) as exc_info:
            await client.execute("query {}")
        assert "Unexpected response code" in str(exc_info.value)
        
    await client.close()


@pytest.mark.asyncio
async def test_execute_graphql_errors(test_settings):
    client = TravelPayoutsClient(test_settings)
    
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    errors_list = [{"message": "Cannot query field 'invalid_field' on type 'Price'"}]
    mock_response.json.return_value = {"errors": errors_list, "data": None}
    
    with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        
        with pytest.raises(TravelPayoutsGraphQLError) as exc_info:
            await client.execute("query { invalid_field }")
        assert exc_info.value.errors == errors_list
        
    await client.close()


@pytest.mark.asyncio
async def test_execute_malformed_json(test_settings):
    client = TravelPayoutsClient(test_settings)
    
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.side_effect = ValueError("Malformed JSON")
    
    with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        
        with pytest.raises(TravelPayoutsUnexpectedResponse) as exc_info:
            await client.execute("query {}")
        assert "Failed to parse JSON response" in str(exc_info.value)
        
    await client.close()


@pytest.mark.asyncio
async def test_execute_timeout(test_settings):
    client = TravelPayoutsClient(test_settings)
    
    with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.TimeoutException("Timeout occurred")
        
        with pytest.raises(TravelPayoutsNetworkError) as exc_info:
            await client.execute("query {}")
        assert "Request timed out" in str(exc_info.value)
        
    await client.close()


@pytest.mark.asyncio
async def test_execute_connection_failure(test_settings):
    client = TravelPayoutsClient(test_settings)
    
    with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.ConnectError("Connection refused")
        
        with pytest.raises(TravelPayoutsNetworkError) as exc_info:
            await client.execute("query {}")
        assert "Network connection failed" in str(exc_info.value)
        
    await client.close()
