from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.entities import Flight
from src.domain.exceptions import ProviderError
from src.domain.scanner_service import ScannerService
from src.use_cases.scan_everywhere import ScanEverywhereUseCase
from src.use_cases.scan_route import ScanRouteUseCase


class DummyProviderError(ProviderError):
    pass


@pytest.fixture
def mock_provider() -> MagicMock:
    provider = MagicMock()
    provider.search_everywhere = AsyncMock()
    provider.search_flights_async = AsyncMock()
    provider.search_flights = MagicMock()
    return provider


@pytest.mark.asyncio
async def test_successful_scan_everywhere(mock_provider):
    scanner = ScannerService(mock_provider)
    mock_flight = Flight(
        id="tp_del_dxb_20260815_0",
        origin="DEL",
        destination="DXB",
        departure_date=datetime(2026, 8, 15),
        price=Decimal("100"),
        airline="AI",
        stops=0,
        duration_minutes=240
    )
    mock_provider.search_everywhere.return_value = [mock_flight]
    
    use_case = ScanEverywhereUseCase(scanner)
    results = await use_case.execute("DEL")
    
    assert results == [mock_flight]
    mock_provider.search_everywhere.assert_called_once_with("DEL")


@pytest.mark.asyncio
async def test_successful_scan_route_async(mock_provider):
    scanner = ScannerService(mock_provider)
    mock_flight = Flight(
        id="tp_del_lhr_20260815_0",
        origin="DEL",
        destination="LHR",
        departure_date=datetime(2026, 8, 15),
        price=Decimal("400"),
        airline="AI",
        stops=0,
        duration_minutes=540
    )
    mock_provider.search_flights_async.return_value = [mock_flight]
    
    use_case = ScanRouteUseCase(scanner)
    results = await use_case.execute("DEL", "LHR", "2026-08-15")
    
    assert results == [mock_flight]
    mock_provider.search_flights_async.assert_called_once_with(
        "DEL", "LHR", "2026-08-15"
    )


@pytest.mark.asyncio
async def test_successful_scan_route_sync_fallback():
    mock_provider = MagicMock()
    # Remove async method to force synchronous fallback
    if hasattr(mock_provider, "search_flights_async"):
        del mock_provider.search_flights_async
    
    mock_flight = Flight(
        id="tp_del_lhr_20260815_0",
        origin="DEL",
        destination="LHR",
        departure_date=datetime(2026, 8, 15),
        price=Decimal("400"),
        airline="AI",
        stops=0,
        duration_minutes=540
    )
    mock_provider.search_flights.return_value = [mock_flight]
    
    scanner = ScannerService(mock_provider)
    use_case = ScanRouteUseCase(scanner)
    results = await use_case.execute("DEL", "LHR", "2026-08-15")
    
    assert results == [mock_flight]
    mock_provider.search_flights.assert_called_once_with(
        "DEL", "LHR", "2026-08-15"
    )


@pytest.mark.asyncio
async def test_provider_failure_propagation(mock_provider):
    scanner = ScannerService(mock_provider)
    mock_provider.search_everywhere.side_effect = DummyProviderError("Auth failure")
    
    with pytest.raises(ProviderError):
        await scanner.search_everywhere("DEL")


@pytest.mark.asyncio
async def test_unexpected_exception_not_swallowed(mock_provider):
    scanner = ScannerService(mock_provider)
    mock_provider.search_everywhere.side_effect = KeyError("Unexpected crash")
    
    with pytest.raises(KeyError):
        await scanner.search_everywhere("DEL")


@pytest.mark.asyncio
async def test_empty_results_handling(mock_provider):
    scanner = ScannerService(mock_provider)
    mock_provider.search_everywhere.return_value = []
    
    results = await scanner.search_everywhere("DEL")
    assert results == []


@pytest.mark.asyncio
async def test_invalid_origin_validation(mock_provider):
    scanner = ScannerService(mock_provider)
    
    with pytest.raises(ValueError) as exc_info:
        await scanner.search_everywhere("INVALID")
    assert "Invalid origin airport code" in str(exc_info.value)
    
    with pytest.raises(ValueError):
        await scanner.search_route("DE", "LHR", "2026-08-15")


@pytest.mark.asyncio
async def test_unsupported_everywhere_provider():
    mock_provider = MagicMock()
    if hasattr(mock_provider, "search_everywhere"):
        del mock_provider.search_everywhere
    
    scanner = ScannerService(mock_provider)
    with pytest.raises(NotImplementedError) as exc_info:
        await scanner.search_everywhere("DEL")
    assert "Everywhere search is not supported" in str(exc_info.value)
