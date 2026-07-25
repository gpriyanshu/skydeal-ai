import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from src.domain.entities import ConversationState, Flight, DealResult, PriceHistory
from src.domain.conversation_service import ConversationService, SearchFilters
from src.domain.intent_classifier import IntentClassifier
from src.adapters.database.conversation_state_repository import InMemoryConversationStateRepository
from src.adapters.ai.openai_provider import OpenAIProvider

@pytest.mark.anyio
async def test_one_turn_success_malaysia():
    repo = InMemoryConversationStateRepository()
    provider = OpenAIProvider(api_key=None)
    goal_service = MagicMock()
    deal_engine = MagicMock()
    domain_deal_engine = MagicMock()
    scanner_service = MagicMock()
    
    f = Flight(id="f1", origin="DEL", destination="KUL", departure_date=datetime(2026, 8, 15, tzinfo=timezone.utc), price=Decimal("12000"), airline="AirAsia", stops=0, duration_minutes=240)
    scanner_service.search_everywhere = AsyncMock(return_value=[f])
    deal = DealResult(
        flight=f, current_price=Decimal("12000"),
        historical_stats=PriceHistory(
            origin="DEL", destination="KUL", current_price=Decimal("12000"),
            lowest_price=Decimal("10000"), highest_price=Decimal("15000"),
            rolling_average=Decimal("14000"), first_seen=datetime.now(timezone.utc), last_seen=datetime.now(timezone.utc)
        ),
        deal_score=95.0, deal_category="SUPER", savings=Decimal("2000"), percentage_below_average=14.3,
        recommendation="BOOK NOW", confidence=90, insights=[]
    )
    domain_deal_engine.process_flights = MagicMock(return_value=[deal])

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
        SearchFilters(country="Malaysia", month="August", budget=15000.0)
    ]

    response = await service.handle_message_async("user_1", "I want to travel to Malaysia in August under 15000")
    assert "🥇 Best Choice" in response
    assert "Airasia" in response
    assert "₹12,000" in response

@pytest.mark.anyio
async def test_multi_turn_japan_budget_follow_up():
    repo = InMemoryConversationStateRepository()
    provider = OpenAIProvider(api_key=None)
    goal_service = MagicMock()
    deal_engine = MagicMock()
    domain_deal_engine = MagicMock()
    scanner_service = MagicMock()
    
    f = Flight(id="f1", origin="DEL", destination="NRT", departure_date=datetime(2026, 9, 15, tzinfo=timezone.utc), price=Decimal("28000"), airline="ANA", stops=0, duration_minutes=300)
    scanner_service.search_everywhere = AsyncMock(return_value=[f])
    deal = DealResult(
        flight=f, current_price=Decimal("28000"),
        historical_stats=PriceHistory(
            origin="DEL", destination="NRT", current_price=Decimal("28000"),
            lowest_price=Decimal("25000"), highest_price=Decimal("35000"),
            rolling_average=Decimal("32000"), first_seen=datetime.now(timezone.utc), last_seen=datetime.now(timezone.utc)
        ),
        deal_score=90.0, deal_category="SUPER", savings=Decimal("4000"), percentage_below_average=12.5,
        recommendation="BOOK NOW", confidence=88, insights=[]
    )
    domain_deal_engine.process_flights = MagicMock(return_value=[deal])

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
        SearchFilters(country="Japan", month="September", budget=None),
        SearchFilters(budget=30000.0)
    ]

    response1 = await service.handle_message_async("user_1", "Travel to Japan in September")
    assert response1 == "What is your budget?"
    state = repo.get("user_1")
    assert state.country == "Japan"
    assert state.month == "September"
    assert state.pending_slot == "budget"
    assert state.pending_action == "ASK_CHEAPEST_FLIGHTS"

    response2 = await service.handle_message_async("user_1", "30000")
    assert "🥇 Best Choice" in response2
    assert "ANA" in response2
    assert "₹28,000" in response2
    state = repo.get("user_1")
    assert state.budget == 30000.0
    assert state.pending_slot is None

@pytest.mark.anyio
async def test_multi_turn_country_follow_up():
    repo = InMemoryConversationStateRepository()
    provider = OpenAIProvider(api_key=None)
    goal_service = MagicMock()
    deal_engine = MagicMock()
    domain_deal_engine = MagicMock()
    scanner_service = MagicMock()
    
    f = Flight(id="f1", origin="DEL", destination="BKK", departure_date=datetime(2026, 9, 15, tzinfo=timezone.utc), price=Decimal("18000"), airline="Thai", stops=0, duration_minutes=240)
    scanner_service.search_everywhere = AsyncMock(return_value=[f])
    deal = DealResult(
        flight=f, current_price=Decimal("18000"),
        historical_stats=PriceHistory(
            origin="DEL", destination="BKK", current_price=Decimal("18000"),
            lowest_price=Decimal("15000"), highest_price=Decimal("22000"),
            rolling_average=Decimal("20000"), first_seen=datetime.now(timezone.utc), last_seen=datetime.now(timezone.utc)
        ),
        deal_score=90.0, deal_category="SUPER", savings=Decimal("2000"), percentage_below_average=10.0,
        recommendation="BOOK NOW", confidence=88, insights=[]
    )
    domain_deal_engine.process_flights = MagicMock(return_value=[deal])

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
        SearchFilters(country=None, month="September", budget=30000.0),
        SearchFilters(country="Thailand")
    ]

    response1 = await service.handle_message_async("user_1", "Flights in September under 30000")
    assert response1 == "Could you please tell me your destination country?"
    state = repo.get("user_1")
    assert state.month == "September"
    assert state.budget == 30000.0
    assert state.pending_slot == "country"

    response2 = await service.handle_message_async("user_1", "Thailand")
    assert "🥇 Best Choice" in response2
    assert "Thai" in response2
    state = repo.get("user_1")
    assert state.country == "Thailand"

@pytest.mark.anyio
async def test_multi_turn_month_follow_up():
    repo = InMemoryConversationStateRepository()
    provider = OpenAIProvider(api_key=None)
    goal_service = MagicMock()
    deal_engine = MagicMock()
    domain_deal_engine = MagicMock()
    scanner_service = MagicMock()
    
    f = Flight(id="f1", origin="DEL", destination="BKK", departure_date=datetime(2026, 10, 15, tzinfo=timezone.utc), price=Decimal("18000"), airline="Thai", stops=0, duration_minutes=240)
    scanner_service.search_everywhere = AsyncMock(return_value=[f])
    deal = DealResult(
        flight=f, current_price=Decimal("18000"),
        historical_stats=PriceHistory(
            origin="DEL", destination="BKK", current_price=Decimal("18000"),
            lowest_price=Decimal("15000"), highest_price=Decimal("22000"),
            rolling_average=Decimal("20000"), first_seen=datetime.now(timezone.utc), last_seen=datetime.now(timezone.utc)
        ),
        deal_score=90.0, deal_category="SUPER", savings=Decimal("2000"), percentage_below_average=10.0,
        recommendation="BOOK NOW", confidence=88, insights=[]
    )
    domain_deal_engine.process_flights = MagicMock(return_value=[deal])

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
        SearchFilters(country="Thailand", month=None, budget=30000.0),
        SearchFilters(month="October")
    ]

    response1 = await service.handle_message_async("user_1", "Flights to Thailand under 30000")
    assert response1 == "What month do you plan to travel?"
    state = repo.get("user_1")
    assert state.country == "Thailand"
    assert state.budget == 30000.0
    assert state.pending_slot == "month"

    response2 = await service.handle_message_async("user_1", "October")
    assert "🥇 Best Choice" in response2
    assert "Thai" in response2
    state = repo.get("user_1")
    assert state.month == "October"

@pytest.mark.anyio
async def test_conversation_timeout():
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
        settings=MagicMock(SCAN_ORIGINS=["DEL"], CONVERSATION_TIMEOUT=1)
    )

    state = ConversationState(user_id="user_1")
    state.country = "Japan"
    state.month = "September"
    state.pending_slot = "budget"
    state.timestamp = datetime.now(timezone.utc) - timedelta(seconds=5)
    repo.save(state)

    provider.generate_structured_response = MagicMock()
    provider.generate_structured_response.side_effect = [
        MagicMock(intent="ASK_CHEAPEST_FLIGHTS"),
        SearchFilters(country="Thailand", month="August", budget=20000.0)
    ]

    f = Flight(id="f1", origin="DEL", destination="BKK", departure_date=datetime(2026, 8, 15, tzinfo=timezone.utc), price=Decimal("18000"), airline="Thai", stops=0, duration_minutes=240)
    scanner_service.search_everywhere = AsyncMock(return_value=[f])
    deal = DealResult(
        flight=f, current_price=Decimal("18000"),
        historical_stats=PriceHistory(
            origin="DEL", destination="BKK", current_price=Decimal("18000"),
            lowest_price=Decimal("15000"), highest_price=Decimal("22000"),
            rolling_average=Decimal("20000"), first_seen=datetime.now(timezone.utc), last_seen=datetime.now(timezone.utc)
        ),
        deal_score=90.0, deal_category="SUPER", savings=Decimal("2000"), percentage_below_average=10.0,
        recommendation="BOOK NOW", confidence=88, insights=[]
    )
    domain_deal_engine.process_flights = MagicMock(return_value=[deal])

    response = await service.handle_message_async("user_1", "Flights to Thailand in August under 20000")
    assert "Thailand" in response

@pytest.mark.anyio
async def test_multiple_simultaneous_users():
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
        # User A Turn 1
        MagicMock(intent="ASK_CHEAPEST_FLIGHTS"),
        SearchFilters(country="Japan", month="September", budget=None),
        # User B Turn 1
        MagicMock(intent="ASK_CHEAPEST_FLIGHTS"),
        SearchFilters(country="Thailand", month="August", budget=None),
        # User A Turn 2
        SearchFilters(budget=30000.0),
        # User B Turn 2
        SearchFilters(budget=15000.0)
    ]

    f_japan = Flight(id="f_jp", origin="DEL", destination="NRT", departure_date=datetime(2026, 9, 15, tzinfo=timezone.utc), price=Decimal("28000"), airline="ANA", stops=0, duration_minutes=300)
    f_thai = Flight(id="f_th", origin="DEL", destination="BKK", departure_date=datetime(2026, 8, 15, tzinfo=timezone.utc), price=Decimal("12000"), airline="Thai", stops=0, duration_minutes=240)
    scanner_service.search_everywhere = AsyncMock(side_effect=lambda origins, max_budget, depart_months, destination_codes, destination_query: [f_japan] if destination_query == "Japan" else [f_thai])

    d_japan = DealResult(flight=f_japan, current_price=Decimal("28000"), historical_stats=PriceHistory(origin="DEL", destination="NRT", current_price=Decimal("28000"), lowest_price=Decimal("25000"), highest_price=Decimal("35000"), rolling_average=Decimal("32000"), first_seen=datetime.now(timezone.utc), last_seen=datetime.now(timezone.utc)), deal_score=90.0, deal_category="SUPER", savings=Decimal("4000"), percentage_below_average=12.5, recommendation="BOOK NOW", confidence=88, insights=[])
    d_thai = DealResult(flight=f_thai, current_price=Decimal("12000"), historical_stats=PriceHistory(origin="DEL", destination="BKK", current_price=Decimal("12000"), lowest_price=Decimal("10000"), highest_price=Decimal("15000"), rolling_average=Decimal("14000"), first_seen=datetime.now(timezone.utc), last_seen=datetime.now(timezone.utc)), deal_score=90.0, deal_category="SUPER", savings=Decimal("2000"), percentage_below_average=14.3, recommendation="BOOK NOW", confidence=88, insights=[])
    
    domain_deal_engine.process_flights = MagicMock(side_effect=lambda flights: [d_japan] if flights[0].destination == "NRT" else [d_thai])

    res_a1 = await service.handle_message_async("user_A", "Travel to Japan in September")
    assert res_a1 == "What is your budget?"
    state_a = repo.get("user_A")
    assert state_a.country == "Japan"
    assert state_a.pending_slot == "budget"

    res_b1 = await service.handle_message_async("user_B", "Flights to Thailand in August")
    assert res_b1 == "What is your budget?"
    state_b = repo.get("user_B")
    assert state_b.country == "Thailand"
    assert state_b.pending_slot == "budget"

    res_a2 = await service.handle_message_async("user_A", "30000")
    assert "Japan" in res_a2
    assert "₹28,000" in res_a2

    res_b2 = await service.handle_message_async("user_B", "15000")
    assert "Thailand" in res_b2
    assert "₹12,000" in res_b2
