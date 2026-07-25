import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock

from src.domain.entities import Flight, DealResult, PriceHistory
from src.domain.conversation_service import ConversationService, SearchFilters
from src.domain.notification_formatter import NotificationFormatter
from src.adapters.database.conversation_state_repository import InMemoryConversationStateRepository
from src.adapters.ai.openai_provider import OpenAIProvider


def test_reusable_formatter_helpers():
    # 1. Airline code mapping tests
    assert NotificationFormatter.get_airline_name("VJ") == "VietJet Air"
    assert NotificationFormatter.get_airline_name("SQ") == "Singapore Airlines"
    assert NotificationFormatter.get_airline_name("AI") == "Air India"
    assert NotificationFormatter.get_airline_name("TG") == "Thai Airways"
    assert NotificationFormatter.get_airline_name("XX") == "XX"  # Fallback to code
    assert NotificationFormatter.get_airline_name(None) == "Unknown"

    # 2. Duration formatting tests
    assert NotificationFormatter.format_duration(515) == "8h 35m"
    assert NotificationFormatter.format_duration(0) == "Not available"
    assert NotificationFormatter.format_duration(None) == "Not available"

    # 3. Stops formatting tests
    assert NotificationFormatter.format_stops(0) == "Non-stop"
    assert NotificationFormatter.format_stops(1) == "1 stop"
    assert NotificationFormatter.format_stops(2) == "2 stops"
    assert NotificationFormatter.format_stops(None) == "Unknown"


def test_conversational_deal_card_rendering():
    flight = Flight(
        id="f1", origin="DEL", destination="NRT",
        departure_date=datetime(2026, 9, 15, tzinfo=timezone.utc),
        price=Decimal("25000"), airline="VJ", stops=1, duration_minutes=515,
        deep_link="https://aviasales.com/xyz"
    )
    deal = DealResult(
        flight=flight,
        current_price=Decimal("25000"),
        deal_category="GOOD",
        deal_score=72.5,
        savings=Decimal("5000"),
        percentage_below_average=16.7,
        historical_stats=PriceHistory(
            origin="DEL", destination="NRT",
            current_price=Decimal("25000"), lowest_price=Decimal("20000"),
            highest_price=Decimal("35000"), rolling_average=Decimal("30000"),
            first_seen=datetime.now(timezone.utc), last_seen=datetime.now(timezone.utc)
        ),
        recommendation="WAIT",
        confidence=80,
        insights=["Price is stable"]
    )
    card_html = NotificationFormatter.format_conversational_deal_html(deal, "🥈 Alternative #2")

    # Verify key details are present
    assert "🥈 Alternative #2" in card_html
    assert "DEL → NRT" in card_html
    assert "₹25,000" in card_html
    assert "VietJet Air" in card_html
    assert "8h 35m" in card_html
    assert "1 stop" in card_html
    assert "72 / 100" in card_html
    assert "WAIT" in card_html
    assert "80%" in card_html
    assert "Price is stable" in card_html
    assert "🔗 <a href=\"https://aviasales.com/xyz\">Book Flight</a>" in card_html
    assert "━━━━━━━━━━━━━━" in card_html


@pytest.mark.anyio
async def test_conversational_search_multiple_flight_rendering_and_sorting():
    repo = InMemoryConversationStateRepository()
    provider = OpenAIProvider(api_key=None)
    goal_service = MagicMock()
    deal_engine = MagicMock()
    domain_deal_engine = MagicMock()
    scanner_service = MagicMock()

    # Stub multiple search results (unsorted, mixed dates and prices)
    f1 = Flight(
        id="f1", origin="DEL", destination="NRT",
        departure_date=datetime(2026, 9, 20, tzinfo=timezone.utc),
        price=Decimal("30000"), airline="VJ", stops=1, duration_minutes=500,
        deep_link="https://link1.com"
    )
    f2 = Flight(
        id="f2", origin="DEL", destination="NRT",
        departure_date=datetime(2026, 9, 10, tzinfo=timezone.utc),
        price=Decimal("20000"), airline="AI", stops=0, duration_minutes=480,
        deep_link="https://link2.com"
    )
    f3 = Flight(
        id="f3", origin="DEL", destination="NRT",
        departure_date=datetime(2026, 9, 15, tzinfo=timezone.utc),
        price=Decimal("25000"), airline="SQ", stops=1, duration_minutes=600,
        deep_link="https://link3.com"
    )

    stats = PriceHistory(
        origin="DEL", destination="NRT",
        current_price=Decimal("20000"), lowest_price=Decimal("15000"),
        highest_price=Decimal("40000"), rolling_average=Decimal("35000"),
        first_seen=datetime.now(timezone.utc), last_seen=datetime.now(timezone.utc)
    )

    d1 = DealResult(
        flight=f1, current_price=Decimal("30000"), deal_category="GOOD", deal_score=65.0, savings=Decimal("5000"),
        percentage_below_average=14.3, historical_stats=stats, recommendation="WAIT", confidence=70
    )
    d2 = DealResult(
        flight=f2, current_price=Decimal("20000"), deal_category="SUPER", deal_score=95.0, savings=Decimal("15000"),
        percentage_below_average=42.8, historical_stats=stats, recommendation="BOOK NOW", confidence=90
    )
    d3 = DealResult(
        flight=f3, current_price=Decimal("25000"), deal_category="GREAT", deal_score=80.0, savings=Decimal("10000"),
        percentage_below_average=28.6, historical_stats=stats, recommendation="WAIT", confidence=80
    )

    scanner_service.search_everywhere = AsyncMock(return_value=[f1, f2, f3])
    domain_deal_engine.process_flights = MagicMock(return_value=[d1, d2, d3])

    # Config with max 3 results
    settings = MagicMock(SCAN_ORIGINS=["DEL"], MAX_CONVERSATIONAL_RESULTS=3)

    service = ConversationService(
        conversation_state_repo=repo,
        ai_provider=provider,
        travel_goal_service=goal_service,
        deal_engine=deal_engine,
        domain_deal_engine=domain_deal_engine,
        scanner_service=scanner_service,
        settings=settings
    )

    provider.generate_structured_response = MagicMock()
    provider.generate_structured_response.side_effect = [
        MagicMock(intent="ASK_CHEAPEST_FLIGHTS"),
        SearchFilters(country="Japan", month="September", budget=50000.0)
    ]

    response = await service.handle_message_async("user_abc", "Japan in September")

    # Assertions
    # Sorted by Deal Score: d2 (95) -> d3 (80) -> d1 (65)
    # So d2 should be 🥇 Best Choice, d3 should be 🥈 Alternative #2, d1 should be 🥉 Alternative #3
    assert "🥇 Best Choice" in response
    assert "🥈 Alternative #2" in response
    assert "🥉 Alternative #3" in response
    
    assert "Air India" in response       # from AI
    assert "Singapore Airlines" in response  # from SQ
    assert "VietJet Air" in response      # from VJ

    assert "https://link1.com" in response
    assert "https://link2.com" in response
    assert "https://link3.com" in response

    # Check suggestion refinement block is appended
    assert "Need something different?" in response
    assert "• Cheapest in October" in response
    assert "• Direct flights only" in response


@pytest.mark.anyio
async def test_conversational_search_empty_result_formatting():
    repo = InMemoryConversationStateRepository()
    provider = OpenAIProvider(api_key=None)
    goal_service = MagicMock()
    deal_engine = MagicMock()
    domain_deal_engine = MagicMock()
    scanner_service = MagicMock()

    scanner_service.search_everywhere = AsyncMock(return_value=[])
    domain_deal_engine.process_flights = MagicMock(return_value=[])

    service = ConversationService(
        conversation_state_repo=repo,
        ai_provider=provider,
        travel_goal_service=goal_service,
        deal_engine=deal_engine,
        domain_deal_engine=domain_deal_engine,
        scanner_service=scanner_service,
        settings=MagicMock(SCAN_ORIGINS=["DEL"], MAX_CONVERSATIONAL_RESULTS=3)
    )

    provider.generate_structured_response = MagicMock()
    provider.generate_structured_response.side_effect = [
        MagicMock(intent="ASK_CHEAPEST_FLIGHTS"),
        SearchFilters(country="Japan", month="September", budget=15000.0)
    ]

    response = await service.handle_message_async("user_abc", "Japan in September under 15k")

    # Assert empty result layout
    assert "🔍 <b>No Matching Flights Found</b>" in response
    assert "Japan" in response
    assert "September" in response
    assert "₹15,000" in response
    assert "Would you like me to keep monitoring Japan for September under ₹15,000?" in response
