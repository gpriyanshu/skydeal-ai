import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from src.domain.entities import ConversationState, Flight, DealResult, PriceHistory, TravelGoal
from src.domain.conversation_service import ConversationService, SearchFilters
from src.adapters.database.conversation_state_repository import InMemoryConversationStateRepository
from src.domain.response_builder import ResponseBuilder

def make_mock_intent(intent_name):
    # Create a mock that responds to intent but returns None for all other attribute lookups
    m = MagicMock()
    m.intent = intent_name
    m.country = None
    m.city = None
    m.month = None
    m.date_range = None
    m.budget = None
    m.budget_inr = None
    m.origin = None
    m.travel_type = None
    m.airline = None
    m.max_stops = None
    m.cabin_class = None
    return m

@pytest.mark.anyio
async def test_search_without_monitoring():
    repo = InMemoryConversationStateRepository()
    ai_mock = MagicMock()
    goal_service = MagicMock()
    deal_engine = MagicMock()
    domain_deal = MagicMock()
    scanner = MagicMock()

    # Turn 1: Classify (1st) and Extract (2nd)
    ai_mock.generate_structured_response.side_effect = [
        make_mock_intent("ASK_CHEAPEST_FLIGHTS"),
        SearchFilters(country="Japan", month="September", budget=50000.0)
    ]

    f1 = Flight(
        id="f1", origin="DEL", destination="NRT",
        departure_date=datetime(2026, 9, 15, tzinfo=timezone.utc),
        price=Decimal("25000"), airline="Japan Airlines", stops=0, duration_minutes=480,
        deep_link="https://book.jal.com"
    )
    deal = DealResult(
        flight=f1, current_price=Decimal("25000"), deal_category="GREAT", deal_score=85.0, savings=Decimal("10000"),
        percentage_below_average=28.5, historical_stats=PriceHistory(
            origin="DEL", destination="NRT", current_price=Decimal("25000"), lowest_price=Decimal("20000"),
            highest_price=Decimal("35000"), rolling_average=Decimal("35000"),
            first_seen=datetime.now(timezone.utc), last_seen=datetime.now(timezone.utc)
        ),
        recommendation="BOOK NOW", confidence=90
    )

    scanner.search_everywhere = AsyncMock(return_value=[f1])
    domain_deal.process_flights = MagicMock(return_value=[deal])

    service = ConversationService(
        conversation_state_repo=repo,
        ai_provider=ai_mock,
        travel_goal_service=goal_service,
        deal_engine=deal_engine,
        domain_deal_engine=domain_deal,
        scanner_service=scanner,
        settings=MagicMock(SCAN_ORIGINS=["DEL"], MAX_CONVERSATIONAL_RESULTS=3)
    )

    response = await service.handle_message_async("user_123", "Cheapest flight to Japan in September under 50000")

    # Assertions
    assert "🥇 Best Choice" in response
    assert "Japan Airlines" in response
    assert "Would you like me to monitor this route?" in response
    assert "✅ Create Price Alert" in response
    
    state = repo.get("user_123")
    assert state.pending_action == "create_goal"
    assert state.extracted_preferences["pending_goal_creation"]["country"] == "Japan"
    assert state.extracted_preferences["pending_goal_creation"]["budget"] == 50000.0

@pytest.mark.anyio
async def test_monitoring_after_confirmation_yes():
    repo = InMemoryConversationStateRepository()
    ai_mock = MagicMock()
    goal_service = MagicMock()
    deal_engine = MagicMock()

    # Pre-populate state with pending goal
    state = ConversationState(user_id="user_123")
    state.extracted_preferences["pending_goal_creation"] = {
        "country": "Japan",
        "start_date": "2026-09-01",
        "end_date": "2026-09-30",
        "budget": 50000.0,
        "cheapest_fare": 25000.0,
        "airline": "Japan Airlines",
        "dep_date": "15 Sep",
        "booking_url": "https://book.jal.com"
    }
    repo.save(state)

    mock_goal = TravelGoal(
        id="goal_999", user_id="user_123", country="Japan",
        start_date=datetime(2026, 9, 1, tzinfo=timezone.utc),
        end_date=datetime(2026, 9, 30, tzinfo=timezone.utc),
        budget_inr=Decimal("50000"), status="ACTIVE"
    )
    goal_service.create_goal.return_value = mock_goal

    service = ConversationService(
        conversation_state_repo=repo,
        ai_provider=ai_mock,
        travel_goal_service=goal_service,
        deal_engine=deal_engine,
        domain_deal_engine=None,
        scanner_service=None,
        settings=None
    )

    response = await service.handle_message_async("user_123", "YES")

    # Assertions
    assert "Price Alert Created" in response
    assert "Goal Created Successfully!" in response
    assert "Current Best Deal" in response
    assert "Japan Airlines" in response
    assert "25,000" in response
    
    state_after = repo.get("user_123")
    assert state_after.pending_action is None
    assert not state_after.extracted_preferences

@pytest.mark.anyio
async def test_goal_cancellation_no():
    repo = InMemoryConversationStateRepository()
    ai_mock = MagicMock()
    goal_service = MagicMock()

    state = ConversationState(user_id="user_123")
    state.extracted_preferences["pending_goal_creation"] = {
        "country": "Japan",
        "start_date": "2026-09-01",
        "end_date": "2026-09-30",
        "budget": 50000.0
    }
    repo.save(state)

    service = ConversationService(
        conversation_state_repo=repo,
        ai_provider=ai_mock,
        travel_goal_service=goal_service,
        deal_engine=None,
        domain_deal_engine=None,
        scanner_service=None,
        settings=None
    )

    response = await service.handle_message_async("user_123", "NO")

    # Assertions
    assert "Got it. I won't create a price alert." in response
    
    state_after = repo.get("user_123")
    assert state_after.pending_action is None
    assert not state_after.extracted_preferences

@pytest.mark.anyio
async def test_mixed_intent():
    repo = InMemoryConversationStateRepository()
    ai_mock = MagicMock()
    goal_service = MagicMock()
    deal_engine = MagicMock()
    domain_deal = MagicMock()
    scanner = MagicMock()

    # The query "Search flights to Japan... and monitor them" triggers a local intent classification override directly returning "MIXED_INTENT".
    # Therefore, only 1 AI call is made to extract search filters.
    ai_mock.generate_structured_response.side_effect = [
        SearchFilters(country="Japan", month="September", budget=50000.0)
    ]

    f1 = Flight(
        id="f1", origin="DEL", destination="NRT",
        departure_date=datetime(2026, 9, 15, tzinfo=timezone.utc),
        price=Decimal("25000"), airline="Japan Airlines", stops=0, duration_minutes=480,
        deep_link="https://book.jal.com"
    )
    deal = DealResult(
        flight=f1, current_price=Decimal("25000"), deal_category="GREAT", deal_score=85.0, savings=Decimal("10000"),
        percentage_below_average=28.5, historical_stats=PriceHistory(
            origin="DEL", destination="NRT", current_price=Decimal("25000"), lowest_price=Decimal("20000"),
            highest_price=Decimal("35000"), rolling_average=Decimal("35000"),
            first_seen=datetime.now(timezone.utc), last_seen=datetime.now(timezone.utc)
        ),
        recommendation="BOOK NOW", confidence=90
    )

    scanner.search_everywhere = AsyncMock(return_value=[f1])
    domain_deal.process_flights = MagicMock(return_value=[deal])

    mock_goal = TravelGoal(
        id="goal_999", user_id="user_123", country="Japan",
        start_date=datetime(2026, 9, 1, tzinfo=timezone.utc),
        end_date=datetime(2026, 9, 30, tzinfo=timezone.utc),
        budget_inr=Decimal("50000"), status="ACTIVE"
    )
    goal_service.create_goal.return_value = mock_goal

    service = ConversationService(
        conversation_state_repo=repo,
        ai_provider=ai_mock,
        travel_goal_service=goal_service,
        deal_engine=deal_engine,
        domain_deal_engine=domain_deal,
        scanner_service=scanner,
        settings=MagicMock(SCAN_ORIGINS=["DEL"], MAX_CONVERSATIONAL_RESULTS=3)
    )

    response = await service.handle_message_async("user_123", "Search flights to Japan in September under 50000 and monitor them")

    # Assertions
    assert "🥇 Best Choice" in response
    assert "Japan Airlines" in response
    assert "Price Alert Created" in response
    assert "Goal Created Successfully!" in response
    assert "Current Best Deal" in response
    
    state_after = repo.get("user_123")
    assert state_after.pending_action is None

@pytest.mark.anyio
async def test_follow_up_refinement_context_preservation():
    repo = InMemoryConversationStateRepository()
    ai_mock = MagicMock()
    goal_service = MagicMock()
    deal_engine = MagicMock()
    domain_deal = MagicMock()
    scanner = MagicMock()

    service = ConversationService(
        conversation_state_repo=repo,
        ai_provider=ai_mock,
        travel_goal_service=goal_service,
        deal_engine=deal_engine,
        domain_deal_engine=domain_deal,
        scanner_service=scanner,
        settings=MagicMock(SCAN_ORIGINS=["DEL"], MAX_CONVERSATIONAL_RESULTS=3)
    )

    # Turn 1: Search flights to Japan in September
    # 2 calls: intent classifier (1st), filters (2nd)
    ai_mock.generate_structured_response.side_effect = [
        make_mock_intent("ASK_CHEAPEST_FLIGHTS"),
        SearchFilters(country="Japan", month="September")
    ]
    scanner.search_everywhere = AsyncMock(return_value=[])
    domain_deal.process_flights = MagicMock(return_value=[])

    await service.handle_message_async("user_123", "flights to Japan in September")
    state = repo.get("user_123")
    assert state.country == "Japan"
    assert state.month == "September"
    assert state.budget is None

    # Turn 2: Under 22000 (Fills missing budget slot)
    # 1 call: filters extraction only (no intent classification because slot_to_fill is set)
    ai_mock.generate_structured_response.side_effect = [
        SearchFilters(budget=22000.0)
    ]
    await service.handle_message_async("user_123", "Under 22000")
    state = repo.get("user_123")
    assert state.country == "Japan"
    assert state.month == "September"
    assert state.budget == 22000.0

    # Turn 3: Direct flights only
    # 2 calls: intent (1st), filters (2nd)
    ai_mock.generate_structured_response.side_effect = [
        make_mock_intent("ASK_CHEAPEST_FLIGHTS"),
        SearchFilters()
    ]
    await service.handle_message_async("user_123", "Direct flights only")
    state = repo.get("user_123")
    assert state.country == "Japan"
    assert state.month == "September"
    assert state.budget == 22000.0
    assert state.max_stops == 0

    # Turn 4: Business class
    # 2 calls: intent (1st), filters (2nd)
    ai_mock.generate_structured_response.side_effect = [
        make_mock_intent("ASK_CHEAPEST_FLIGHTS"),
        SearchFilters()
    ]
    await service.handle_message_async("user_123", "Business class")
    state = repo.get("user_123")
    assert state.country == "Japan"
    assert state.month == "September"
    assert state.budget == 22000.0
    assert state.max_stops == 0
    assert state.cabin_class == "business"
