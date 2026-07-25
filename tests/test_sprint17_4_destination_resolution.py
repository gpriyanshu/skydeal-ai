import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from src.domain.entities import Flight, DealResult, PriceHistory
from src.domain.conversation_service import ConversationService, SearchFilters
from src.domain.destination_resolver import DestinationResolver
from src.domain.scanner_service import ScannerService
from src.adapters.database.conversation_state_repository import InMemoryConversationStateRepository
from src.adapters.ai.openai_provider import OpenAIProvider


def test_destination_resolver_countries_and_cities():
    resolver = DestinationResolver()

    # Test Country resolution
    malaysia_codes = resolver.resolve_destination("Malaysia")
    assert malaysia_codes == ["KUL", "PEN", "LGK", "JHB", "BKI", "KCH"]

    thailand_codes = resolver.resolve_destination("Thailand")
    assert thailand_codes == ["BKK", "DMK", "HKT", "CNX", "KBV"]

    japan_codes = resolver.resolve_destination("Japan")
    assert "HND" in japan_codes
    assert "NRT" in japan_codes
    assert "ITM" in japan_codes

    # Test City resolution
    tokyo_codes = resolver.resolve_destination("Tokyo")
    assert tokyo_codes == ["HND", "NRT"]

    kl_codes = resolver.resolve_destination("Kuala Lumpur")
    assert kl_codes == ["KUL"]

    bangkok_codes = resolver.resolve_destination("Bangkok")
    assert bangkok_codes == ["BKK", "DMK"]


def test_destination_resolver_synonyms():
    resolver = DestinationResolver()

    # UK synonyms
    uk_codes = resolver.resolve_destination("UK")
    britain_codes = resolver.resolve_destination("Britain")
    uk_full_codes = resolver.resolve_destination("United Kingdom")
    assert uk_codes == ["LHR", "LGW", "MAN", "STN"]
    assert britain_codes == ["LHR", "LGW", "MAN", "STN"]
    assert uk_full_codes == ["LHR", "LGW", "MAN", "STN"]

    # USA synonyms
    usa_codes = resolver.resolve_destination("USA")
    us_codes = resolver.resolve_destination("United States")
    america_codes = resolver.resolve_destination("America")
    assert usa_codes == ["JFK", "LAX", "SFO", "ORD", "MIA"]
    assert us_codes == ["JFK", "LAX", "SFO", "ORD", "MIA"]
    assert america_codes == ["JFK", "LAX", "SFO", "ORD", "MIA"]

    # UAE synonyms
    uae_codes = resolver.resolve_destination("UAE")
    emirates_codes = resolver.resolve_destination("Emirates")
    assert uae_codes == ["DXB", "AUH", "SHJ"]
    assert emirates_codes == ["DXB", "AUH", "SHJ"]

    # South Korea synonyms
    korea_codes = resolver.resolve_destination("Korea")
    sk_codes = resolver.resolve_destination("South Korea")
    assert korea_codes == ["ICN", "GMP", "PUS"]
    assert sk_codes == ["ICN", "GMP", "PUS"]


def test_destination_resolver_unknown_and_iata():
    resolver = DestinationResolver()

    # Unknown destinations
    assert resolver.resolve_destination("Atlantis") is None
    assert resolver.resolve_destination("Leh") is None
    assert resolver.resolve_destination("Mauritius") is None
    assert resolver.resolve_destination("UnknownPlace") is None

    # Direct IATA code fallback
    assert resolver.resolve_destination("KUL") == ["KUL"]
    assert resolver.resolve_destination("nrt") == ["NRT"]


@pytest.mark.anyio
async def test_scanner_service_integration_prevents_global_search():
    provider = MagicMock()
    provider.search_flights_async = AsyncMock(return_value=[])
    provider.search_everywhere = AsyncMock()

    scanner = ScannerService(provider)

    # Resolve "Malaysia"
    resolver = DestinationResolver()
    resolved_codes = resolver.resolve_destination("Malaysia")

    # Perform search_everywhere with destination codes
    flights = await scanner.search_everywhere(
        origin="DEL",
        destination_codes=resolved_codes,
        destination_query="Malaysia"
    )

    # Provider search_everywhere (global search) MUST NEVER be called
    provider.search_everywhere.assert_not_called()

    from unittest.mock import ANY
    assert provider.search_flights_async.call_count == len(resolved_codes)
    for code in resolved_codes:
        provider.search_flights_async.assert_any_call("DEL", code, ANY)


@pytest.mark.anyio
async def test_conversation_validation_unknown_destination():
    repo = InMemoryConversationStateRepository()
    provider = OpenAIProvider(api_key=None)
    goal_service = MagicMock()
    deal_engine = MagicMock()
    domain_deal_engine = MagicMock()
    scanner_service = MagicMock()

    service = ConversationService(
        conversation_state_repo=repo,
        ai_provider=provider,
        travel_goal_service=goal_service,
        deal_engine=deal_engine,
        domain_deal_engine=domain_deal_engine,
        scanner_service=scanner_service,
        settings=MagicMock(SCAN_ORIGINS=["DEL"])
    )

    provider.generate_structured_response = MagicMock()
    provider.generate_structured_response.side_effect = [
        MagicMock(intent="ASK_CHEAPEST_FLIGHTS"),
        SearchFilters(country="Leh")  # Unresolved destination
    ]

    response = await service.handle_message_async("user_123", "I want to go Leh")
    assert response == "I couldn't identify that destination."
    scanner_service.search_everywhere.assert_not_called()


@pytest.mark.anyio
async def test_malaysia_search_never_returns_other_destinations():
    repo = InMemoryConversationStateRepository()
    provider = OpenAIProvider(api_key=None)
    goal_service = MagicMock()
    deal_engine = MagicMock()
    domain_deal_engine = MagicMock()
    
    mock_provider = MagicMock()
    scanner_service = ScannerService(mock_provider)

    # Stub routes returned for Malaysian airports vs other airports
    # Even if mock_provider returns some flights to other countries, we want to make sure they are filtered out
    flights_from_provider = [
        Flight(
            id="f1", origin="DEL", destination="KUL",
            departure_date=datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc),
            price=Decimal("15000"), airline="Malaysia Airlines", stops=0, duration_minutes=300
        ),
        Flight(
            id="f2", origin="DEL", destination="FCO",  # Italy/Rome - should be ignored
            departure_date=datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc),
            price=Decimal("35000"), airline="Alitalia", stops=0, duration_minutes=500
        ),
        Flight(
            id="f3", origin="DEL", destination="PEN",  # Malaysia
            departure_date=datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc),
            price=Decimal("18000"), airline="AirAsia", stops=0, duration_minutes=320
        ),
    ]

    # Mock provider.search_flights_async to return appropriate flights
    async def mock_search_flights(origin, destination, departure_date):
        return [f for f in flights_from_provider if f.destination.upper() == destination.upper()]

    mock_provider.search_flights_async = AsyncMock(side_effect=mock_search_flights)

    # DealEngine output
    deal1 = DealResult(
        flight=flights_from_provider[0], current_price=Decimal("15000"),
        historical_stats=PriceHistory(
            origin="DEL", destination="KUL", current_price=Decimal("15000"),
            lowest_price=Decimal("15000"), highest_price=Decimal("20000"),
            rolling_average=Decimal("20000"), first_seen=datetime.now(timezone.utc), last_seen=datetime.now(timezone.utc)
        ),
        deal_score=95.0, deal_category="SUPER", savings=Decimal("5000"), percentage_below_average=25.0,
        recommendation="BOOK NOW", confidence=95, insights=[]
    )
    deal3 = DealResult(
        flight=flights_from_provider[2], current_price=Decimal("18000"),
        historical_stats=PriceHistory(
            origin="DEL", destination="PEN", current_price=Decimal("18000"),
            lowest_price=Decimal("18000"), highest_price=Decimal("22000"),
            rolling_average=Decimal("22000"), first_seen=datetime.now(timezone.utc), last_seen=datetime.now(timezone.utc)
        ),
        deal_score=90.0, deal_category="GREAT", savings=Decimal("4000"), percentage_below_average=18.2,
        recommendation="BOOK NOW", confidence=90, insights=[]
    )
    domain_deal_engine.process_flights = MagicMock(return_value=[deal1, deal3])

    service = ConversationService(
        conversation_state_repo=repo,
        ai_provider=provider,
        travel_goal_service=goal_service,
        deal_engine=deal_engine,
        domain_deal_engine=domain_deal_engine,
        scanner_service=scanner_service,
        settings=MagicMock(SCAN_ORIGINS=["DEL"])
    )

    provider.generate_structured_response = MagicMock()
    provider.generate_structured_response.side_effect = [
        MagicMock(intent="ASK_CHEAPEST_FLIGHTS"),
        SearchFilters(country="Malaysia", month="September", budget=50000.0)
    ]

    response = await service.handle_message_async("user_123", "I want to go Malaysia")

    # Assert that KUL and PEN flights are in response, and FCO is NOT in response
    assert "Kuala Lumpur" in response or "KUL" in response
    assert "Penang" in response or "PEN" in response
    assert "Rome" not in response
    assert "FCO" not in response
    assert "Italy" not in response
    assert "Mauritius" not in response
    assert "Leh" not in response
