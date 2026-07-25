import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from src.domain.entities import ConversationState, Flight, DealResult, PriceHistory
from src.domain.travel_goal_parser import TravelGoalParser
from src.domain.conversation_service import ConversationService, SearchFilters
from src.adapters.database.conversation_state_repository import InMemoryConversationStateRepository
from src.adapters.ai.openai_provider import OpenAIProvider

# ==============================================================================
# BUG 1 TESTS - Month Extraction in TravelGoalParser
# ==============================================================================

@pytest.fixture
def parser():
    return TravelGoalParser()

@pytest.fixture
def fixed_now():
    # July 14, 2026
    return datetime(2026, 7, 14, 12, 0, 0, tzinfo=timezone.utc)

@pytest.fixture
def conversation_service():
    repo = InMemoryConversationStateRepository()
    return ConversationService(
        conversation_state_repo=repo,
        ai_provider=MagicMock(),
        travel_goal_service=MagicMock(),
        deal_engine=None,
        domain_deal_engine=None,
        scanner_service=None,
        settings=None
    )

def test_parser_all_months_and_abbreviations(conversation_service, fixed_now):
    test_cases = [
        ("I want to visit Japan in January", 1, 2027),
        ("Go to Japan in Feb", 2, 2027),
        ("Germany in March", 3, 2027),
        ("Vietnam in APR", 4, 2027),
        ("thailand in may", 5, 2027),
        ("Singapore in June", 6, 2027),
        ("Malaysia in july", 7, 2026),
        ("Korea in AUG", 8, 2026),
        ("visit Japan in September", 9, 2026),
        ("Japan in oct", 10, 2026),
        ("Thailand in November", 11, 2026),
        ("Italy in dec", 12, 2026),
    ]

    for query, expected_month, expected_year in test_cases:
        state = conversation_service.extract_and_save_slots("user_123", query, now=fixed_now)
        assert state.travel_date_window is not None
        p_start, p_end = state.travel_date_window.split(" to ")
        start_date = datetime.fromisoformat(p_start)
        end_date = datetime.fromisoformat(p_end)
        assert start_date.month == expected_month
        assert start_date.year == expected_year
        assert end_date.month == expected_month
        assert end_date.year == expected_year

def test_parser_mixed_case_months(conversation_service, fixed_now):
    mixed_queries = [
        ("Japan in SePtEmBeR", 9, 2026),
        ("Vietnam in jAn", 1, 2027),
        ("Thailand in OcToBeR", 10, 2026),
    ]
    for query, expected_month, expected_year in mixed_queries:
        state = conversation_service.extract_and_save_slots("user_123", query, now=fixed_now)
        assert state.travel_date_window is not None
        p_start, _ = state.travel_date_window.split(" to ")
        start_date = datetime.fromisoformat(p_start)
        assert start_date.month == expected_month
        assert start_date.year == expected_year

def test_parser_month_precedence_over_seasons(conversation_service, fixed_now):
    # Cherry blossom is normally March/April. Mentioning September must take precedence.
    state = conversation_service.extract_and_save_slots("user_123", "I want South Korea during Cherry Blossom season in September.", now=fixed_now)
    assert state.travel_date_window is not None
    p_start, _ = state.travel_date_window.split(" to ")
    start_date = datetime.fromisoformat(p_start)
    assert start_date.month == 9
    assert start_date.year == 2026
    
    # New Year is normally Dec 28 to Jan 5. Mentioning October explicitly must take precedence.
    state = conversation_service.extract_and_save_slots("user_123", "I want Dubai for New Year in October.", now=fixed_now)
    assert state.travel_date_window is not None
    p_start, _ = state.travel_date_window.split(" to ")
    start_date = datetime.fromisoformat(p_start)
    assert start_date.month == 10
    assert start_date.year == 2026


# ==============================================================================
# BUG 2 TESTS - Confirmation Context in ConversationService
# ==============================================================================

@pytest.mark.anyio
async def test_yes_creates_pending_goal():
    repo = InMemoryConversationStateRepository(timeout_seconds=900)
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
        settings=MagicMock(SCAN_ORIGINS=["DEL"], CONVERSATION_TIMEOUT=900)
    )

    # Pre-populate pending state directly in ConversationState slots
    state = ConversationState(user_id="user_yes")
    state.country = "Japan"
    state.city = None
    state.month = "September"
    state.date_range = "2026-09-01 to 2026-09-30"
    state.budget = 30000.0
    state.pending_action = "create_goal"
    state.timestamp = datetime.now(timezone.utc)
    repo.save(state)

    mock_goal = MagicMock()
    mock_goal.country = "Japan"
    mock_goal.start_date = datetime(2026, 9, 1, tzinfo=timezone.utc)
    mock_goal.end_date = datetime(2026, 9, 30, tzinfo=timezone.utc)
    mock_goal.budget_inr = Decimal("30000")
    goal_service.create_goal.return_value = mock_goal

    # User sends "YES"
    response = await service.handle_message_async("user_yes", "YES")
    
    # Assertions
    goal_service.create_goal.assert_called_once_with(
        "user_yes", "visit Japan from 2026-09-01 to 2026-09-30 with a budget of 30000.0"
    )
    assert "Goal Created Successfully!" in response
    
    # Check that pending slots are cleared
    updated_state = repo.get("user_yes")
    assert updated_state.pending_action is None
    assert updated_state.country is None

@pytest.mark.anyio
async def test_no_cancels_pending_goal():
    repo = InMemoryConversationStateRepository(timeout_seconds=900)
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
        settings=MagicMock(SCAN_ORIGINS=["DEL"], CONVERSATION_TIMEOUT=900)
    )

    state = ConversationState(user_id="user_no")
    state.country = "Japan"
    state.month = "September"
    state.date_range = "2026-09-01 to 2026-09-30"
    state.budget = 30000.0
    state.pending_action = "create_goal"
    state.timestamp = datetime.now(timezone.utc)
    repo.save(state)

    # User sends "NO"
    response = await service.handle_message_async("user_no", "NO")
    
    # Assertions
    goal_service.create_goal.assert_not_called()
    assert "cancelled" in response.lower()
    
    # Check that pending slots are cleared
    updated_state = repo.get("user_no")
    assert updated_state.pending_action is None
    assert updated_state.country is None

@pytest.mark.anyio
async def test_expired_confirmation_state():
    repo = InMemoryConversationStateRepository(timeout_seconds=900)
    provider = MagicMock()
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
        settings=MagicMock(SCAN_ORIGINS=["DEL"], CONVERSATION_TIMEOUT=900)
    )

    state = ConversationState(user_id="user_expired")
    state.country = "Japan"
    state.month = "September"
    state.date_range = "2026-09-01 to 2026-09-30"
    state.budget = 30000.0
    state.pending_action = "create_goal"
    # Set timestamp in the past (1000 seconds ago, timeout is 900)
    state.timestamp = datetime.now(timezone.utc) - timedelta(seconds=1000)
    repo.save(state)

    # If expired, YES should be treated as a normal NL message. Mock the provider to return intent
    provider.generate_structured_response.side_effect = [
        MagicMock(intent="ASK_CHEAPEST_FLIGHTS"),
        SearchFilters(country="Japan", month="September", budget=30000.0)
    ]

    # Process message
    await service.handle_message_async("user_expired", "YES")
    
    # Since it was expired, create_goal should not have been called
    goal_service.create_goal.assert_not_called()

@pytest.mark.anyio
async def test_multiple_simultaneous_users():
    repo = InMemoryConversationStateRepository(timeout_seconds=900)
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
        settings=MagicMock(SCAN_ORIGINS=["DEL"], CONVERSATION_TIMEOUT=900)
    )

    # Setup User 1: awaiting confirmation
    state1 = ConversationState(user_id="user_1")
    state1.country = "Japan"
    state1.month = "September"
    state1.date_range = "2026-09-01 to 2026-09-30"
    state1.budget = 30000.0
    state1.pending_action = "create_goal"
    state1.timestamp = datetime.now(timezone.utc)
    repo.save(state1)

    # Setup User 2: awaiting confirmation
    state2 = ConversationState(user_id="user_2")
    state2.country = "Thailand"
    state2.month = "December"
    state2.date_range = "2026-12-01 to 2026-12-31"
    state2.budget = 25000.0
    state2.pending_action = "create_goal"
    state2.timestamp = datetime.now(timezone.utc)
    repo.save(state2)

    # User 1 confirms YES
    mock_goal1 = MagicMock(country="Japan", start_date=datetime(2026, 9, 1), end_date=datetime(2026, 9, 30), budget_inr=Decimal("30000"))
    goal_service.create_goal.return_value = mock_goal1
    response1 = await service.handle_message_async("user_1", "YES")
    
    # User 2 cancels NO
    response2 = await service.handle_message_async("user_2", "NO")

    # Assertions
    assert "Goal Created Successfully!" in response1
    assert "cancelled" in response2.lower()

    # User 1's goal created for Japan
    goal_service.create_goal.assert_called_once_with(
        "user_1", "visit Japan from 2026-09-01 to 2026-09-30 with a budget of 30000.0"
    )
