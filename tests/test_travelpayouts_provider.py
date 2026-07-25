from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.adapters.providers.travelpayouts import TravelPayoutsProvider
from src.adapters.providers.travelpayouts_client import (
    TravelPayoutsAuthenticationError,
    TravelPayoutsClient,
    TravelPayoutsRateLimitError,
    TravelPayoutsUnexpectedResponse,
)
from src.adapters.providers.travelpayouts_mapper import TravelPayoutsResponseMapper
from src.domain.entities import Flight


@pytest.fixture
def mock_client() -> MagicMock:
    return MagicMock(spec=TravelPayoutsClient)


@pytest.fixture
def mock_mapper() -> MagicMock:
    return MagicMock(spec=TravelPayoutsResponseMapper)


@pytest.mark.asyncio
async def test_provider_search_everywhere_success(mock_client, mock_mapper):
    provider = TravelPayoutsProvider(mock_client, mock_mapper)
    
    mock_raw_json = {"data": {"prices_one_way": [{"value": 100}]}}
    mock_client.execute = AsyncMock(return_value=mock_raw_json)
    
    mock_flight = Flight(
        id="tp_del_dxb_20260815_0",
        origin="DEL",
        destination="DXB",
        departure_date=datetime(2026, 8, 15, 10, 30),
        price=Decimal("100"),
        airline="AI",
        stops=0,
        duration_minutes=240,
        deep_link="http://link"
    )
    mock_mapper.map.return_value = [mock_flight]
    
    flights = await provider.search_everywhere("DEL")
    
    assert flights == [mock_flight]
    mock_client.execute.assert_called_once()
    mock_mapper.map.assert_called_once_with(mock_raw_json)


@pytest.mark.asyncio
async def test_provider_search_everywhere_auth_failure(mock_client, mock_mapper):
    provider = TravelPayoutsProvider(mock_client, mock_mapper)
    mock_client.execute = AsyncMock(
        side_effect=TravelPayoutsAuthenticationError("Invalid API token")
    )
    
    with pytest.raises(TravelPayoutsAuthenticationError) as exc_info:
        await provider.search_everywhere("DEL")
    assert "Invalid API token" in str(exc_info.value)


@pytest.mark.asyncio
async def test_provider_search_everywhere_rate_limit(mock_client, mock_mapper):
    provider = TravelPayoutsProvider(mock_client, mock_mapper)
    mock_client.execute = AsyncMock(
        side_effect=TravelPayoutsRateLimitError("Rate limit exceeded")
    )
    
    with pytest.raises(TravelPayoutsRateLimitError) as exc_info:
        await provider.search_everywhere("DEL")
    assert "Rate limit exceeded" in str(exc_info.value)


@pytest.mark.asyncio
async def test_provider_search_everywhere_mapper_failure(mock_client, mock_mapper):
    provider = TravelPayoutsProvider(mock_client, mock_mapper)
    mock_client.execute = AsyncMock(return_value={"bad": "response"})
    mock_mapper.map.side_effect = ValueError("Unexpected mapper parsing error")
    
    with pytest.raises(TravelPayoutsUnexpectedResponse) as exc_info:
        await provider.search_everywhere("DEL")
    assert "Mapping failed" in str(exc_info.value)


def test_provider_search_flights_success(mock_client, mock_mapper):
    provider = TravelPayoutsProvider(mock_client, mock_mapper)
    
    mock_raw_json = {"data": {"prices_one_way": [{"value": 100}]}}
    mock_client.execute = AsyncMock(return_value=mock_raw_json)
    
    flight_match = Flight(
        id="tp_del_dxb_20260815_0",
        origin="DEL",
        destination="DXB",
        departure_date=datetime(2026, 8, 15, 10, 30),
        price=Decimal("100"),
        airline="AI",
        stops=0,
        duration_minutes=240,
        deep_link="http://link"
    )
    flight_no_match = Flight(
        id="tp_del_dxb_20260816_0",
        origin="DEL",
        destination="DXB",
        departure_date=datetime(2026, 8, 16, 10, 30),
        price=Decimal("120"),
        airline="AI",
        stops=0,
        duration_minutes=240,
        deep_link="http://link"
    )
    mock_mapper.map.return_value = [flight_match, flight_no_match]
    
    flights = provider.search_flights(
        origin="DEL",
        destination="DXB",
        departure_date="2026-08-15"
    )
    
    assert flights == [flight_match]


def test_provider_search_flights_empty_response(mock_client, mock_mapper):
    provider = TravelPayoutsProvider(mock_client, mock_mapper)
    mock_client.execute = AsyncMock(return_value={"data": {"prices_one_way": []}})
    mock_mapper.map.return_value = []
    
    flights = provider.search_flights(
        origin="DEL",
        destination="DXB",
        departure_date="2026-08-15"
    )
    
    assert flights == []


def test_provider_search_airports_match():
    provider = TravelPayoutsProvider(MagicMock(), MagicMock())
    results = provider.search_airports("del")
    assert results == ["DEL"]
    
    results = provider.search_airports("sin")
    assert results == ["SIN"]


@pytest.mark.asyncio
async def test_provider_search_everywhere_custom_limit(mock_client, mock_mapper):
    settings = MagicMock()
    settings.TRAVELPAYOUTS_PAGE_SIZE = 500
    settings.ALLOWED_DESTINATION_COUNTRIES = []
    settings.COUNTRY_MAX_BUDGETS = {}
    settings.MAX_DAYS_AHEAD = 120
    
    provider = TravelPayoutsProvider(mock_client, mock_mapper, settings=settings)
    
    mock_raw_json = {"data": {"prices_one_way": []}}
    mock_client.execute = AsyncMock(return_value=mock_raw_json)
    mock_mapper.map.return_value = []
    
    await provider.search_everywhere("DEL")
    
    mock_client.execute.assert_called_once()
    variables = mock_client.execute.call_args[0][1]
    assert variables["limit"] == 500

