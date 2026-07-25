import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from src.domain.entities import ConversationState, Flight, DealResult, PriceHistory
from src.domain.conversation_service import ConversationService, SearchFilters
from src.domain.intent_classifier import IntentClassifier
from src.adapters.database.conversation_state_repository import InMemoryConversationStateRepository
from src.adapters.ai.openai_provider import OpenAIProvider
from src.config import Settings

@pytest.mark.anyio
async def test_intent_detection_live_search():
    # Verify search variations resolve to ASK_CHEAPEST_FLIGHTS
    provider = OpenAIProvider(api_key=None)
    classifier = IntentClassifier(provider)
    
    queries = [
        "Cheapest flight to Japan",
        "Japan under 25000",
        "Any Japan flights?",
        "Flights below 30k",
        "Tokyo tickets",
        "Japan August",
        "Flights for September",
        "Search flights",
        "Show me deals",
        "Cheapest ticket to Dubai",
        "Best flight to Vietnam"
    ]
    
    for q in queries:
        provider.generate_structured_response = MagicMock(return_value=MagicMock(intent="ASK_CHEAPEST_FLIGHTS"))
        intent = classifier.classify_intent(q)
        assert intent == "ASK_CHEAPEST_FLIGHTS"

@pytest.mark.anyio
async def test_query_parsing_and_live_invocation():
    repo = InMemoryConversationStateRepository()
    provider = OpenAIProvider(api_key=None)
    goal_service = MagicMock()
    deal_engine = MagicMock()
    domain_deal_engine = MagicMock()
    scanner_service = MagicMock()

    # Stub search results
    jp_flight = Flight(
        id="f1", origin="BLR", destination="NRT",
        departure_date=datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc),
        price=Decimal("35000"), airline="Japan Airlines", stops=0, duration_minutes=480
    )
    scanner_service.search_everywhere = AsyncMock(return_value=[jp_flight])
    
    # DealEngine output
    deal = DealResult(
        flight=jp_flight, current_price=Decimal("35000"),
        historical_stats=PriceHistory(
            origin="BLR", destination="NRT", current_price=Decimal("35000"),
            lowest_price=Decimal("35000"), highest_price=Decimal("45000"),
            rolling_average=Decimal("45000"), first_seen=datetime.now(timezone.utc), last_seen=datetime.now(timezone.utc)
        ),
        deal_score=91.0, deal_category="SUPER", savings=Decimal("10000"), percentage_below_average=22.2,
        recommendation="BOOK NOW", confidence=94, insights=[]
    )
    domain_deal_engine.process_flights = MagicMock(return_value=[deal])

    service = ConversationService(
        conversation_state_repo=repo,
        ai_provider=provider,
        travel_goal_service=goal_service,
        deal_engine=deal_engine,
        domain_deal_engine=domain_deal_engine,
        scanner_service=scanner_service,
        settings=MagicMock(SCAN_ORIGINS=["DEL", "BOM", "BLR"])
    )

    # Mock provider structured responses
    provider.generate_structured_response = MagicMock()
    provider.generate_structured_response.side_effect = [
        MagicMock(intent="ASK_CHEAPEST_FLIGHTS"), # Classifier
        SearchFilters(origin="BLR", country="Japan", month="September", budget=45000.0) # Filters
    ]

    response = await service.handle_message_async("user_123", "Bangalore to Japan in September under 45000")
    
    # Assertions
    scanner_service.search_everywhere.assert_called_once_with(
        ["BLR"],
        max_budget=45000.0,
        depart_months="2026-09",
        destination_codes=["HND", "NRT", "KIX", "CTS", "FUK", "OKA", "ITM", "TYO", "NGO"],
        destination_query="Japan"
    )
    assert "🥇 Best Choice" in response
    assert "₹35,000" in response
    assert "Japan Airlines" in response

@pytest.mark.anyio
async def test_multi_origin_scanning_default():
    repo = InMemoryConversationStateRepository()
    provider = OpenAIProvider(api_key=None)
    goal_service = MagicMock()
    deal_engine = MagicMock()
    domain_deal_engine = MagicMock()
    scanner_service = MagicMock()
    scanner_service.search_everywhere = AsyncMock(return_value=[])

    service = ConversationService(
        conversation_state_repo=repo,
        ai_provider=provider,
        travel_goal_service=goal_service,
        deal_engine=deal_engine,
        domain_deal_engine=domain_deal_engine,
        scanner_service=scanner_service,
        settings=MagicMock(SCAN_ORIGINS=["DEL", "BOM", "BLR"])
    )

    provider.generate_structured_response = MagicMock()
    provider.generate_structured_response.side_effect = [
        MagicMock(intent="ASK_CHEAPEST_FLIGHTS"),
        SearchFilters(country="Japan", month="September", budget=45000.0) # No origin specified
    ]

    await service.handle_message_async("user_123", "Japan in September")
    scanner_service.search_everywhere.assert_called_once_with(
        ["DEL", "BOM", "BLR"],
        max_budget=45000.0,
        depart_months="2026-09",
        destination_codes=["HND", "NRT", "KIX", "CTS", "FUK", "OKA", "ITM", "TYO", "NGO"],
        destination_query="Japan"
    )

@pytest.mark.anyio
async def test_ranking_logic():
    repo = InMemoryConversationStateRepository()
    provider = OpenAIProvider(api_key=None)
    goal_service = MagicMock()
    deal_engine = MagicMock()
    domain_deal_engine = MagicMock()
    scanner_service = MagicMock()

    f1 = Flight(id="f1", origin="DEL", destination="NRT", departure_date=datetime(2026, 9, 10, tzinfo=timezone.utc), price=Decimal("20000"), airline="ANA", stops=0, duration_minutes=300)
    f2 = Flight(id="f2", origin="DEL", destination="NRT", departure_date=datetime(2026, 9, 11, tzinfo=timezone.utc), price=Decimal("15000"), airline="ANA", stops=1, duration_minutes=300)
    
    scanner_service.search_everywhere = AsyncMock(return_value=[f1, f2])

    d1 = DealResult(
        flight=f1, current_price=Decimal("20000"),
        historical_stats=PriceHistory(
            origin="DEL", destination="NRT", current_price=Decimal("20000"),
            lowest_price=Decimal("15000"), highest_price=Decimal("25000"),
            rolling_average=Decimal("22000"), first_seen=datetime.now(timezone.utc), last_seen=datetime.now(timezone.utc)
        ), deal_score=80.0, deal_category="GREAT", savings=Decimal("5000"), percentage_below_average=20.0,
        recommendation="BOOK NOW", confidence=85, insights=[]
    )
    d2 = DealResult(
        flight=f2, current_price=Decimal("15000"),
        historical_stats=PriceHistory(
            origin="DEL", destination="NRT", current_price=Decimal("15000"),
            lowest_price=Decimal("12000"), highest_price=Decimal("22000"),
            rolling_average=Decimal("22000"), first_seen=datetime.now(timezone.utc), last_seen=datetime.now(timezone.utc)
        ), deal_score=90.0, deal_category="SUPER", savings=Decimal("10000"), percentage_below_average=40.0,
        recommendation="BOOK NOW", confidence=95, insights=[]
    )
    # Return d1 and d2 in this order. Ranking should sort d2 first due to higher deal score (90 vs 80)
    domain_deal_engine.process_flights = MagicMock(return_value=[d1, d2])

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
        SearchFilters(country="Japan", month="September", budget=30000.0)
    ]

    response = await service.handle_message_async("user_123", "Search flights to Japan")
    
    # 🥇 Best Choice should be d2 because it ranks higher
    assert "🥇 Best Choice" in response
    assert "₹15,000" in response # price of d2
    assert "🥈 Alternative #2" in response
    assert "₹20,000" in response # price of d1

@pytest.mark.anyio
async def test_automatic_goal_suggestion_and_creation():
    repo = InMemoryConversationStateRepository()
    provider = OpenAIProvider(api_key=None)
    goal_service = MagicMock()
    deal_engine = MagicMock()
    domain_deal_engine = MagicMock()
    scanner_service = MagicMock()
    scanner_service.search_everywhere = AsyncMock(return_value=[])

    service = ConversationService(
        conversation_state_repo=repo,
        ai_provider=provider,
        travel_goal_service=goal_service,
        deal_engine=deal_engine,
        domain_deal_engine=domain_deal_engine,
        scanner_service=scanner_service,
        settings=MagicMock(SCAN_ORIGINS=["DEL"])
    )

    # 1. First turn: search has no results -> offers to create goal
    provider.generate_structured_response = MagicMock()
    provider.generate_structured_response.side_effect = [
        MagicMock(intent="ASK_CHEAPEST_FLIGHTS"),
        SearchFilters(country="Japan", month="September", budget=30000.0)
    ]

    response1 = await service.handle_message_async("user_123", "Cheap Japan flights for September under 30000")
    assert "No Matching Flights Found" in response1
    assert "Would you like me to keep monitoring Japan for September under ₹30,000?" in response1

    # 2. Second turn: user replies "YES"
    provider.generate_structured_response.side_effect = [
        MagicMock(intent="CREATE_GOAL") # Classified as goal confirmation / creation
    ]
    
    mock_goal = MagicMock()
    mock_goal.country = "Japan"
    mock_goal.start_date = datetime(2026, 9, 1)
    mock_goal.end_date = datetime(2026, 9, 30)
    mock_goal.budget_inr = Decimal("30000")
    goal_service.create_goal.return_value = mock_goal

    response2 = await service.handle_message_async("user_123", "YES")
    assert "Goal Created Successfully!" in response2
    goal_service.create_goal.assert_called_once_with("user_123", "visit Japan from 2026-09-01 to 2026-09-30 with a budget of 30000.0")

@pytest.mark.anyio
async def test_live_search_api_failure_fallback():
    repo = InMemoryConversationStateRepository()
    provider = OpenAIProvider(api_key=None)
    goal_service = MagicMock()
    deal_engine = MagicMock()
    domain_deal_engine = MagicMock()
    
    scanner_service = MagicMock()
    scanner_service.search_everywhere.side_effect = Exception("TravelPayouts API limit reached")

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
        SearchFilters(country="Japan", month="September", budget=30000.0)
    ]

    response = await service.handle_message_async("user_123", "Cheap Japan flights")
    assert "No Matching Flights Found" in response # Graceful fallback
