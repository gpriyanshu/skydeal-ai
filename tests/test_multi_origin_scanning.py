import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.entities import Flight
from src.domain.scanner_service import ScannerService


@pytest.fixture
def mock_provider() -> MagicMock:
    provider = MagicMock()
    provider.search_everywhere = AsyncMock()
    return provider


@pytest.mark.asyncio
async def test_single_origin_scanning(mock_provider):
    scanner = ScannerService(mock_provider)
    mock_flight = Flight(
        id="f1", origin="DEL", destination="BKK",
        departure_date=datetime.now(timezone.utc), price=Decimal("9000"),
        airline="AI", stops=0, duration_minutes=240
    )
    mock_provider.search_everywhere.return_value = [mock_flight]

    results = await scanner.search_everywhere("DEL")
    assert results == [mock_flight]
    mock_provider.search_everywhere.assert_called_once_with("DEL")


@pytest.mark.asyncio
async def test_multiple_origins_concurrent(mock_provider):
    scanner = ScannerService(mock_provider)
    flight_del = Flight(
        id="f1", origin="DEL", destination="BKK",
        departure_date=datetime.now(timezone.utc), price=Decimal("9000"),
        airline="AI", stops=0, duration_minutes=240
    )
    flight_bom = Flight(
        id="f2", origin="BOM", destination="BKK",
        departure_date=datetime.now(timezone.utc), price=Decimal("9500"),
        airline="AI", stops=0, duration_minutes=240
    )

    async def mock_search(origin):
        if origin == "DEL":
            return [flight_del]
        elif origin == "BOM":
            return [flight_bom]
        return []

    mock_provider.search_everywhere.side_effect = mock_search

    results = await scanner.search_everywhere(["DEL", "BOM"])
    assert len(results) == 2
    assert flight_del in results
    assert flight_bom in results
    assert mock_provider.search_everywhere.call_count == 2


@pytest.mark.asyncio
async def test_deduplication(mock_provider):
    scanner = ScannerService(mock_provider)
    dep_date = datetime.now(timezone.utc)
    
    # Two identical flights
    flight1 = Flight(
        id="f1", origin="DEL", destination="BKK",
        departure_date=dep_date, price=Decimal("9000"),
        airline="AI", stops=0, duration_minutes=240
    )
    flight2 = Flight(
        id="f2", origin="DEL", destination="BKK",
        departure_date=dep_date, price=Decimal("9000"),
        airline="AI", stops=0, duration_minutes=240
    )
    # Different origin flight (must NOT be deduplicated)
    flight3 = Flight(
        id="f3", origin="BOM", destination="BKK",
        departure_date=dep_date, price=Decimal("9000"),
        airline="AI", stops=0, duration_minutes=240
    )

    mock_provider.search_everywhere.side_effect = lambda origin: [flight1, flight2] if origin == "DEL" else [flight3]

    results = await scanner.search_everywhere(["DEL", "BOM"])
    
    # We should have exactly 2 flights (DEL -> BKK and BOM -> BKK)
    assert len(results) == 2
    origins = [f.origin for f in results]
    assert "DEL" in origins
    assert "BOM" in origins


@pytest.mark.asyncio
async def test_empty_provider_response(mock_provider):
    scanner = ScannerService(mock_provider)
    mock_provider.search_everywhere.return_value = []

    results = await scanner.search_everywhere(["DEL", "BOM"])
    assert results == []


@pytest.mark.asyncio
async def test_partial_provider_failure(mock_provider):
    scanner = ScannerService(mock_provider)
    flight_bom = Flight(
        id="f1", origin="BOM", destination="BKK",
        departure_date=datetime.now(timezone.utc), price=Decimal("9500"),
        airline="AI", stops=0, duration_minutes=240
    )

    async def mock_search(origin):
        if origin == "DEL":
            raise Exception("Provider crashed!")
        elif origin == "BOM":
            return [flight_bom]
        return []

    mock_provider.search_everywhere.side_effect = mock_search

    # Scanning DEL and BOM; DEL fails, but BOM should succeed and return its flight
    results = await scanner.search_everywhere(["DEL", "BOM"])
    assert results == [flight_bom]


@pytest.mark.asyncio
async def test_scanning_logging_details(mock_provider):
    scanner = ScannerService(mock_provider)
    mock_provider.search_everywhere.return_value = []

    from unittest.mock import patch
    with patch("src.domain.scanner_service.logger") as mock_logger:
        await scanner.search_everywhere(["DEL", "BOM"])

    # Extract all logged messages from mock calls
    info_calls = [call[0][0] for call in mock_logger.info.call_args_list]
    
    assert any("Starting scan: DEL" in msg for msg in info_calls)
    assert any("Starting scan: BOM" in msg for msg in info_calls)
    assert any("Origins scanned: 2" in msg for msg in info_calls)
    assert any("Flights before merge: 0" in msg for msg in info_calls)
    assert any("Flights after deduplication: 0" in msg for msg in info_calls)
    assert any("Flights sent to Deal Engine: 0" in msg for msg in info_calls)
    assert any("Total execution time: " in msg for msg in info_calls)
