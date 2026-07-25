import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

from src.domain.entities import TravelGoal, TravelGoalDraft, User
from src.domain.travel_goal_parser import TravelGoalParser
from src.domain.conversation_service import ConversationService
from src.adapters.database.conversation_state_repository import InMemoryConversationStateRepository


# --- Parser & Extractor Tests ---

@pytest.fixture
def parser():
    return TravelGoalParser()


@pytest.fixture
def fixed_now():
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


def test_parser_validation_valid(parser, fixed_now):
    draft = TravelGoalDraft(
        country="Japan",
        start_date=datetime(2026, 9, 1, tzinfo=timezone.utc),
        end_date=datetime(2026, 9, 30, tzinfo=timezone.utc),
        budget_inr=Decimal("30000")
    )
    validated = parser.parse(draft, now=fixed_now)
    assert validated.country == "Japan"
    assert validated.start_date.month == 9
    assert validated.budget_inr == Decimal("30000")


def test_parser_validation_missing_country(parser, fixed_now):
    draft = TravelGoalDraft(
        country=None,
        start_date=datetime(2026, 9, 1, tzinfo=timezone.utc),
        end_date=datetime(2026, 9, 30, tzinfo=timezone.utc),
        budget_inr=Decimal("30000")
    )
    with pytest.raises(ValueError, match="Could not extract a supported destination country"):
        parser.parse(draft, now=fixed_now)


def test_parser_validation_missing_dates(parser, fixed_now):
    draft = TravelGoalDraft(
        country="Japan",
        start_date=None,
        end_date=None,
        budget_inr=Decimal("30000")
    )
    with pytest.raises(ValueError, match="Could not extract a valid travel date window or season"):
        parser.parse(draft, now=fixed_now)


def test_parser_validation_negative_budget(parser, fixed_now):
    draft = TravelGoalDraft(
        country="Japan",
        start_date=datetime(2026, 9, 1, tzinfo=timezone.utc),
        end_date=datetime(2026, 9, 30, tzinfo=timezone.utc),
        budget_inr=Decimal("-1000")
    )
    with pytest.raises(ValueError, match="Budget cannot be negative"):
        parser.parse(draft, now=fixed_now)


def test_conversation_service_country_extraction(conversation_service, fixed_now):
    # Japan
    state = conversation_service.extract_and_save_slots("user_123", "I want to visit Japan next September.", now=fixed_now)
    assert state.country == "Japan"

    # Thailand
    state = conversation_service.extract_and_save_slots("user_123", "I want Thailand in December under 15000.", now=fixed_now)
    assert state.country == "Thailand"

    # Germany
    state = conversation_service.extract_and_save_slots("user_123", "I want to go Germany next May.", now=fixed_now)
    assert state.country == "Germany"

    # Dubai -> United Arab Emirates
    state = conversation_service.extract_and_save_slots("user_123", "I want Dubai for New Year.", now=fixed_now)
    assert state.country == "United Arab Emirates"

    # South Korea
    state = conversation_service.extract_and_save_slots("user_123", "I want South Korea during Cherry Blossom season.", now=fixed_now)
    assert state.country == "South Korea"


def test_conversation_service_date_window_extraction(conversation_service, fixed_now):
    # September (future month in 2026)
    state = conversation_service.extract_and_save_slots("user_123", "I want to visit Japan next September.", now=fixed_now)
    assert state.travel_date_window == "2026-09-01 to 2026-09-30"

    # May (past month in 2026, resolves to 2027)
    state = conversation_service.extract_and_save_slots("user_123", "I want to go Germany next May.", now=fixed_now)
    assert state.travel_date_window == "2027-05-01 to 2027-05-31"

    # New Year
    state = conversation_service.extract_and_save_slots("user_123", "I want Dubai for New Year.", now=fixed_now)
    assert state.travel_date_window == "2026-12-28 to 2027-01-05"

    # Cherry Blossom (past spring season in 2026, resolves to 2027)
    state = conversation_service.extract_and_save_slots("user_123", "I want South Korea during Cherry Blossom season.", now=fixed_now)
    assert state.travel_date_window == "2027-03-20 to 2027-04-20"


def test_conversation_service_budget_extraction(conversation_service, fixed_now):
    # Under 15000
    state = conversation_service.extract_and_save_slots("user_123", "I want Thailand in December under 15000.", now=fixed_now)
    assert state.budget == 15000.0

    # Raw number
    state = conversation_service.extract_and_save_slots("user_123", "Japan in December 25000.", now=fixed_now)
    assert state.budget == 25000.0

    # No budget
    state = conversation_service.extract_and_save_slots("user_123", "I want Germany next May.", now=fixed_now)
    assert state.budget is None


# --- Repository Tests ---

def test_travel_goal_repository_lifecycle(travel_goal_repo, user_repo):
    test_user = User(
        id="user_tg_test",
        preferred_countries=[],
        preferred_airports=[],
        preferred_airlines=[],
        cabin_class="economy"
    )
    user_repo.save(test_user)

    now = datetime.now(timezone.utc).replace(microsecond=0)
    goal = TravelGoal(
        id="goal_1",
        user_id="user_tg_test",
        country="Japan",
        start_date=now,
        end_date=now,
        budget_inr=Decimal("50000"),
        status="ACTIVE",
        created_at=now,
        updated_at=now
    )

    # 1. Create goal
    created = travel_goal_repo.create_goal(goal)
    assert created.id == "goal_1"
    assert created.country == "Japan"
    assert created.budget_inr == Decimal("50000")
    assert created.status == "ACTIVE"

    # 2. Get list of goals
    goals = travel_goal_repo.list_goals("user_tg_test")
    assert len(goals) == 1
    assert goals[0].id == "goal_1"
    assert goals[0].country == "Japan"

    # 3. Get active goals
    active_goals = travel_goal_repo.get_active_goals("user_tg_test")
    assert len(active_goals) == 1
    assert active_goals[0].id == "goal_1"

    # 4. Update goal (Pause it)
    goal.status = "PAUSED"
    updated = travel_goal_repo.update_goal(goal)
    assert updated.status == "PAUSED"

    assert len(travel_goal_repo.get_active_goals("user_tg_test")) == 0
    assert len(travel_goal_repo.list_goals("user_tg_test")) == 1

    # 5. Delete goal
    deleted = travel_goal_repo.delete_goal("goal_1")
    assert deleted is True
    assert len(travel_goal_repo.list_goals("user_tg_test")) == 0

    assert travel_goal_repo.delete_goal("non_existent") is False
