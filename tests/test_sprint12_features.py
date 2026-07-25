import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from src.domain.entities import TravelGoal, Flight, DealResult, PriceHistory, User, Deal, Notification
from src.use_cases.notification_pipeline import NotificationPipeline
from src.domain.notification_formatter import NotificationFormatter


@pytest.fixture
def fixed_now():
    return datetime(2027, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_sprint12_hybrid_pipeline_integration(
    user_repo, travel_goal_repo, deal_repo, notification_repo, fixed_now
):
    # 1. Setup a mixed user: has both a Daily Summary subscription and an active Travel Goal
    user_mixed = User(id="user_mixed", notification_enabled=True, baseline_sent=True)
    user_repo.save(user_mixed)

    # 2. Setup a legacy user: has only a Daily Summary subscription (0 Travel Goals)
    user_legacy = User(id="user_legacy", notification_enabled=True, baseline_sent=True)
    user_repo.save(user_legacy)

    # Add active Travel Goals for user_mixed
    goal_jp = TravelGoal(
        id="goal_jp_123", user_id="user_mixed", country="Japan",
        start_date=datetime(2027, 9, 1, tzinfo=timezone.utc),
        end_date=datetime(2027, 9, 30, tzinfo=timezone.utc),
        budget_inr=Decimal("25000"), status="ACTIVE",
        created_at=fixed_now, updated_at=fixed_now
    )
    travel_goal_repo.create_goal(goal_jp)

    # Mock Scanner Service
    # Return one flight to Japan (matching goal) and one flight to Singapore (matching daily summary)
    flight_jp = Flight(
        id="flight_jp", origin="DEL", destination="NRT",
        departure_date=datetime(2027, 9, 15, 10, 0, tzinfo=timezone.utc),
        price=Decimal("20000"), airline="ANA", stops=0, duration_minutes=500
    )
    flight_sg = Flight(
        id="flight_sg", origin="DEL", destination="SIN",
        departure_date=datetime(2027, 2, 10, 10, 0, tzinfo=timezone.utc),
        price=Decimal("12000"), airline="Singapore Airlines", stops=0, duration_minutes=350
    )
    scanner_mock = MagicMock()
    scanner_mock.search_everywhere = AsyncMock(return_value=[flight_jp, flight_sg])

    # Mock Deal Engine
    deal_jp = DealResult(
        flight=flight_jp, current_price=Decimal("20000"),
        historical_stats=PriceHistory(
            origin="DEL", destination="NRT", current_price=Decimal("20000"),
            lowest_price=Decimal("20000"), highest_price=Decimal("30000"),
            rolling_average=Decimal("28000"), first_seen=fixed_now, last_seen=fixed_now
        ),
        deal_score=28.57, deal_category="GREAT", savings=Decimal("8000"), percentage_below_average=28.57
    )
    deal_sg = DealResult(
        flight=flight_sg, current_price=Decimal("12000"),
        historical_stats=PriceHistory(
            origin="DEL", destination="SIN", current_price=Decimal("12000"),
            lowest_price=Decimal("12000"), highest_price=Decimal("18000"),
            rolling_average=Decimal("16000"), first_seen=fixed_now, last_seen=fixed_now
        ),
        deal_score=25.0, deal_category="GREAT", savings=Decimal("4000"), percentage_below_average=25.0
    )
    
    deal_engine_mock = MagicMock()
    # Mock process_flights:
    # First call is Workflow 1 (Daily Scanner filtering by Singapore).
    # Second call is Workflow 2 (Goal Scanner filtering by Japan).
    def mock_process_flights(flights_list):
        destinations = {f.destination for f in flights_list}
        res = []
        if "SIN" in destinations:
            res.append(deal_sg)
        if "NRT" in destinations:
            res.append(deal_jp)
        return res

    deal_engine_mock.process_flights = MagicMock(side_effect=mock_process_flights)

    # Mock Telegram Sender to intercept sent notifications
    tg_sender_mock = MagicMock()
    tg_sender_mock.default_chat_id = "12345"
    sent_notifs = []
    
    def mock_send(notification, message_header, message_body):
        sent_notifs.append((notification, message_header, message_body))
        return True
    
    tg_sender_mock.send = MagicMock(side_effect=mock_send)

    # Set mock settings
    settings_mock = MagicMock()
    settings_mock.ALLOWED_DESTINATION_COUNTRIES = ["Singapore"]  # Only SG is allowed globally
    settings_mock.COUNTRY_MAX_BUDGETS = {"Singapore": 15000}
    settings_mock.MAX_DAYS_AHEAD = 365
    settings_mock.MAX_DEALS_PER_SCAN = 10

    pipeline = NotificationPipeline(
        scanner_service=scanner_mock,
        deal_engine=deal_engine_mock,
        notification_formatter=NotificationFormatter(),
        telegram_sender=tg_sender_mock,
        user_repo=user_repo,
        notification_repo=notification_repo,
        deal_repo=deal_repo,
        travel_goal_repo=travel_goal_repo,
        settings=settings_mock
    )

    # Run the hybrid execution
    await pipeline.execute()

    # --- ASSERTIONS ---
    # 1. Verify Daily Summary was sent to both user_mixed and user_legacy (Workflow 1)
    # The daily summary should only contain Singapore (SIN), since Japan (NRT) is not in ALLOWED_DESTINATION_COUNTRIES!
    daily_summaries = [n for n in sent_notifs if "Today's Best Flight Deals" in n[1]]
    assert len(daily_summaries) == 2
    
    # Assert Singapore is in daily summaries
    for _, header, body in daily_summaries:
        assert "Singapore" in body
        assert "Japan" not in body  # Japan must not appear in the daily summary!

    # 2. Verify Goal Match notification was sent ONLY to user_mixed (Workflow 2)
    # The Goal Match notification should contain Japan (NRT)
    goal_matches = [n for n in sent_notifs if "Travel Goal Matched" in n[1]]
    assert len(goal_matches) == 1
    goal_notification, header, body = goal_matches[0]
    assert goal_notification.user_id == "user_mixed"
    assert "Japan" in body
    assert "Singapore" not in body  # Singapore must not appear in the goal notification!

    # 3. Verify Goal isolation & Cooldown behavior
    # Verify that the DB query was isolated by goal_id
    last_sent_goal = notification_repo.get_last_sent_deal_for_route("user_mixed", "DEL", "NRT", goal_id="goal_jp_123")
    assert last_sent_goal is not None
    assert last_sent_goal.flight.destination == "NRT"

    # Last sent summary for user_mixed should be SIN
    last_sent_summary = notification_repo.get_last_sent_deal_for_route("user_mixed", "DEL", "SIN", goal_id=None)
    assert last_sent_summary is not None
    assert last_sent_summary.flight.destination == "SIN"
