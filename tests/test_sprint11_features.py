import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from src.domain.entities import TravelGoal, Flight, DealResult, PriceHistory, User
from src.domain.travel_goal_parser import TravelGoalParser
from src.use_cases.travel_goal_service import TravelGoalService
from src.adapters.telegram_command_handler import TelegramCommandHandler
from src.use_cases.notification_pipeline import NotificationPipeline
from src.domain.notification_formatter import NotificationFormatter


@pytest.fixture
def parser():
    return TravelGoalParser()


@pytest.fixture
def travel_service(travel_goal_repo, parser):
    return TravelGoalService(travel_goal_repo, parser)


@pytest.fixture
def cmd_handler(travel_service):
    return TelegramCommandHandler(travel_service)


@pytest.fixture
def fixed_now():
    return datetime(2027, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


def test_duplicate_goal_prevention(travel_service, user_repo, fixed_now):
    user_id = "user_dup_test"
    user_repo.save(User(id=user_id, cabin_class="economy"))

    # Add goal first time
    travel_service.create_goal(user_id, "I want to visit Japan next September.", now=fixed_now)

    # Attempt to add identical goal
    with pytest.raises(ValueError, match="Goal already exists."):
        travel_service.create_goal(user_id, "I want to visit Japan next September.", now=fixed_now)


def test_command_handler_duplicate_response(cmd_handler, user_repo, fixed_now):
    user_id = "user_cmd_dup_test"
    user_repo.save(User(id=user_id, cabin_class="economy"))

    # First add
    cmd_handler.handle_command(user_id, "Japan next September")

    # Duplicate add
    res = cmd_handler.handle_command(user_id, "Japan next September")
    assert res == "Goal already exists."


def test_pause_resume_delete_goal(travel_service, user_repo, fixed_now):
    user_id = "user_lifecycle_test"
    user_repo.save(User(id=user_id, cabin_class="economy"))

    # Create Goal
    goal = travel_service.create_goal(user_id, "Germany next May", now=fixed_now)
    assert goal.status == "ACTIVE"

    # Pause
    travel_service.pause_goal(user_id, goal.id, now=fixed_now)
    goals = travel_service.list_goals(user_id)
    assert goals[0].status == "PAUSED"

    # Resume
    travel_service.resume_goal(user_id, goal.id, now=fixed_now)
    goals = travel_service.list_goals(user_id)
    assert goals[0].status == "ACTIVE"

    # Delete
    deleted = travel_service.delete_goal(user_id, goal.id)
    assert deleted is True
    assert len(travel_service.list_goals(user_id)) == 0


def test_multiple_goals_and_users(travel_service, user_repo, fixed_now):
    user1 = "user_mult_1"
    user2 = "user_mult_2"
    user_repo.save(User(id=user1, cabin_class="economy"))
    user_repo.save(User(id=user2, cabin_class="economy"))

    # User 1 has multiple goals
    travel_service.create_goal(user1, "Japan next September", now=fixed_now)
    travel_service.create_goal(user1, "Thailand December under 15000", now=fixed_now)

    # User 2 has different goals
    travel_service.create_goal(user2, "Germany next May", now=fixed_now)

    # Assert segregation
    assert len(travel_service.list_goals(user1)) == 2
    assert len(travel_service.list_goals(user2)) == 1


def test_notification_mapping(parser, fixed_now):
    from src.domain.entities import TravelGoalDraft
    draft = TravelGoalDraft(
        country="Japan",
        start_date=datetime(2027, 9, 1, tzinfo=timezone.utc),
        end_date=datetime(2027, 9, 30, tzinfo=timezone.utc),
        budget_inr=Decimal("25000")
    )
    goal = TravelGoal(
        id="goal_123",
        user_id="user_1",
        country=draft.country,
        start_date=draft.start_date,
        end_date=draft.end_date,
        budget_inr=Decimal("25000"),
        status="ACTIVE"
    )

    flight = Flight(
        id="f1",
        origin="BLR",
        destination="NRT",
        departure_date=fixed_now + timedelta(days=235),  # September 2027
        price=Decimal("22500"),
        airline="ANA",
        stops=0,
        duration_minutes=480,
    )
    deal = DealResult(
        flight=flight,
        current_price=Decimal("22500"),
        historical_stats=PriceHistory(
            origin="BLR", destination="NRT", current_price=Decimal("22500"),
            lowest_price=Decimal("22500"), highest_price=Decimal("28500"),
            rolling_average=Decimal("28500"), first_seen=fixed_now, last_seen=fixed_now
        ),
        deal_score=21.05,
        deal_category="GREAT",
        savings=Decimal("6000"),
        percentage_below_average=21.05
    )

    formatter = NotificationFormatter()
    msg = formatter.format_goal_summary(goal, [deal])
    
    assert "🎯 <b>Travel Goal Matched</b>" in msg.body_html
    assert "Japan" in msg.body_html
    assert "September 2027" in msg.body_html
    assert "BLR" in msg.body_html
    assert "NRT" in msg.body_html
    assert "₹22,500" in msg.body_html
    assert "₹6,000" in msg.body_html


@pytest.mark.asyncio
async def test_caching_identical_goals_in_pipeline(
    user_repo, travel_goal_repo, deal_repo, notification_repo, fixed_now
):
    # Two active users with identical goals
    u1_id = "user_cache_1"
    u2_id = "user_cache_2"
    user_repo.save(User(id=u1_id, notification_enabled=True))
    user_repo.save(User(id=u2_id, notification_enabled=True))

    goal1 = TravelGoal(
        id="goal_c1", user_id=u1_id, country="Japan",
        start_date=datetime(2027, 9, 1, tzinfo=timezone.utc),
        end_date=datetime(2027, 9, 30, tzinfo=timezone.utc),
        budget_inr=Decimal("25000"), status="ACTIVE",
        created_at=fixed_now, updated_at=fixed_now
    )
    goal2 = TravelGoal(
        id="goal_c2", user_id=u2_id, country="Japan",
        start_date=datetime(2027, 9, 1, tzinfo=timezone.utc),
        end_date=datetime(2027, 9, 30, tzinfo=timezone.utc),
        budget_inr=Decimal("25000"), status="ACTIVE",
        created_at=fixed_now, updated_at=fixed_now
    )
    travel_goal_repo.create_goal(goal1)
    travel_goal_repo.create_goal(goal2)

    # Mock scanner service and deal engine
    scanner_mock = MagicMock()
    # Return one flight to Japan
    japan_flight = Flight(
        id="flight_jp", origin="DEL", destination="NRT",
        departure_date=datetime(2027, 9, 15, 10, 0, tzinfo=timezone.utc),
        price=Decimal("20000"), airline="Japan Airlines", stops=0, duration_minutes=500
    )
    scanner_mock.search_everywhere = AsyncMock(return_value=[japan_flight])

    deal_engine_mock = MagicMock()
    # Monitor invocations of process_flights
    deal_result = DealResult(
        flight=japan_flight, current_price=Decimal("20000"),
        historical_stats=PriceHistory(
            origin="DEL", destination="NRT", current_price=Decimal("20000"),
            lowest_price=Decimal("20000"), highest_price=Decimal("30000"),
            rolling_average=Decimal("28000"), first_seen=fixed_now, last_seen=fixed_now
        ),
        deal_score=28.57, deal_category="GREAT", savings=Decimal("8000"), percentage_below_average=28.57
    )
    deal_engine_mock.process_flights = MagicMock(return_value=[deal_result])

    tg_sender_mock = MagicMock()
    tg_sender_mock.default_chat_id = "some_chat"
    tg_sender_mock.send = MagicMock(return_value=True)

    pipeline = NotificationPipeline(
        scanner_service=scanner_mock,
        deal_engine=deal_engine_mock,
        notification_formatter=NotificationFormatter(),
        telegram_sender=tg_sender_mock,
        user_repo=user_repo,
        notification_repo=notification_repo,
        deal_repo=deal_repo,
        travel_goal_repo=travel_goal_repo
    )

    await pipeline.execute()

    # Verify DealEngine.process_flights was called exactly ONCE due to caching!
    assert deal_engine_mock.process_flights.call_count == 1
    # Verify Telegram send was called for both users
    assert tg_sender_mock.send.call_count == 2
