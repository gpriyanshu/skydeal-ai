from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.entities import Deal, DealResult, Flight, PriceHistory, User
from src.domain.exceptions import ProviderError
from src.domain.notification_formatter import NotificationMessage
from src.use_cases.notification_pipeline import NotificationPipeline


@pytest.fixture
def mock_scanner() -> MagicMock:
    service = MagicMock()
    service.search_everywhere = AsyncMock()
    return service


@pytest.fixture
def mock_deal_engine() -> MagicMock:
    engine = MagicMock()
    engine.process_flights = MagicMock()
    return engine


@pytest.fixture
def mock_formatter() -> MagicMock:
    formatter = MagicMock()
    formatter.format = MagicMock()
    return formatter


@pytest.fixture
def mock_telegram() -> MagicMock:
    sender = MagicMock()
    sender.send = MagicMock()
    sender.default_chat_id = "default_chat"
    return sender


@pytest.fixture
def mock_user_repo() -> MagicMock:
    repo = MagicMock()
    repo.get_all_active = MagicMock()
    return repo


@pytest.fixture
def mock_deal_repo() -> MagicMock:
    repo = MagicMock()
    repo.save = MagicMock()
    return repo


@pytest.fixture
def mock_notification_repo() -> MagicMock:
    repo = MagicMock()
    repo.has_recent_notification_for_route = MagicMock()
    repo.save = MagicMock()
    return repo


@pytest.mark.asyncio
async def test_pipeline_complete_execution_success(
    mock_scanner,
    mock_deal_engine,
    mock_formatter,
    mock_telegram,
    mock_user_repo,
    mock_notification_repo,
    mock_deal_repo
):
    flight = Flight(
        id="f1",
        origin="DEL",
        destination="DXB",
        departure_date=datetime(2026, 8, 15),
        price=Decimal("90"),
        airline="AI",
        stops=0,
        duration_minutes=240,
        deep_link="https://link"
    )
    mock_scanner.search_everywhere.return_value = [flight]

    history = PriceHistory(
        origin="DEL",
        destination="DXB",
        current_price=Decimal("90"),
        lowest_price=Decimal("80"),
        highest_price=Decimal("120"),
        rolling_average=Decimal("100"),
        first_seen=datetime.utcnow(),
        last_seen=datetime.utcnow(),
        observation_count=5
    )
    deal_result = DealResult(
        flight=flight,
        current_price=Decimal("90"),
        historical_stats=history,
        deal_score=10.0,
        deal_category="GOOD",
        savings=Decimal("10"),
        percentage_below_average=10.0
    )
    mock_deal_engine.process_flights.return_value = [deal_result]

    mock_formatter.format_summary.return_value = NotificationMessage(
        subject="🚀 GOOD DEAL: DEL to DXB for 90.00",
        body_text="Detailed text",
        body_html="<h3>Detailed HTML</h3>"
    )

    mock_user_repo.get_all_active.return_value = [
        User(id="user1", username="u1", notification_enabled=True, baseline_sent=True)
    ]
    mock_notification_repo.get_last_sent_deal_for_route.return_value = None
    mock_telegram.send.return_value = True

    pipeline = NotificationPipeline(
        scanner_service=mock_scanner,
        deal_engine=mock_deal_engine,
        notification_formatter=mock_formatter,
        telegram_sender=mock_telegram,
        user_repo=mock_user_repo,
        notification_repo=mock_notification_repo,
        deal_repo=mock_deal_repo,
        min_notification_category="GOOD",
        cooldown_seconds=3600,
        scan_origin="DEL"
    )

    await pipeline.execute()

    mock_scanner.search_everywhere.assert_called_once_with("DEL")
    mock_deal_engine.process_flights.assert_called_once_with([flight])
    mock_formatter.format_summary.assert_called_once_with([deal_result])
    mock_telegram.send.assert_called_once()
    assert mock_notification_repo.save.call_count >= 1


@pytest.mark.asyncio
async def test_pipeline_no_deals(
    mock_scanner,
    mock_deal_engine,
    mock_formatter,
    mock_telegram,
    mock_user_repo,
    mock_notification_repo,
    mock_deal_repo
):
    mock_scanner.search_everywhere.return_value = []
    mock_deal_engine.process_flights.return_value = []

    pipeline = NotificationPipeline(
        scanner_service=mock_scanner,
        deal_engine=mock_deal_engine,
        notification_formatter=mock_formatter,
        telegram_sender=mock_telegram,
        user_repo=mock_user_repo,
        notification_repo=mock_notification_repo,
        deal_repo=mock_deal_repo,
        min_notification_category="GOOD",
        cooldown_seconds=3600,
        scan_origin="DEL"
    )

    await pipeline.execute()

    mock_telegram.send.assert_not_called()


@pytest.mark.asyncio
async def test_pipeline_duplicate_deals_filtered(
    mock_scanner,
    mock_deal_engine,
    mock_formatter,
    mock_telegram,
    mock_user_repo,
    mock_notification_repo,
    mock_deal_repo
):
    flight = Flight(
        id="f1",
        origin="DEL",
        destination="DXB",
        departure_date=datetime(2026, 8, 15),
        price=Decimal("90"),
        airline="AI",
        stops=0,
        duration_minutes=240,
        deep_link="https://link"
    )
    mock_scanner.search_everywhere.return_value = [flight]

    history = PriceHistory(
        origin="DEL",
        destination="DXB",
        current_price=Decimal("90"),
        lowest_price=Decimal("80"),
        highest_price=Decimal("120"),
        rolling_average=Decimal("100"),
        first_seen=datetime.utcnow(),
        last_seen=datetime.utcnow(),
        observation_count=5
    )
    deal_result = DealResult(
        flight=flight,
        current_price=Decimal("90"),
        historical_stats=history,
        deal_score=10.0,
        deal_category="GOOD",
        savings=Decimal("10"),
        percentage_below_average=10.0
    )
    mock_deal_engine.process_flights.return_value = [deal_result]

    mock_user_repo.get_all_active.return_value = [
        User(id="user1", username="u1", notification_enabled=True, baseline_sent=True)
    ]
    # Simulate a recently sent matching deal
    last_sent = Deal(
        id="f1",
        flight=flight,
        category="Good Deal",
        discount_percentage=10.0,
        historical_average=Decimal("100"),
        detected_at=datetime.utcnow()
    )
    mock_notification_repo.get_last_sent_deal_for_route.return_value = last_sent

    pipeline = NotificationPipeline(
        scanner_service=mock_scanner,
        deal_engine=mock_deal_engine,
        notification_formatter=mock_formatter,
        telegram_sender=mock_telegram,
        user_repo=mock_user_repo,
        notification_repo=mock_notification_repo,
        deal_repo=mock_deal_repo,
        min_notification_category="GOOD",
        cooldown_seconds=3600,
        scan_origin="DEL"
    )

    await pipeline.execute()

    mock_telegram.send.assert_not_called()


@pytest.mark.asyncio
async def test_pipeline_telegram_failure_does_not_crash(
    mock_scanner,
    mock_deal_engine,
    mock_formatter,
    mock_telegram,
    mock_user_repo,
    mock_notification_repo,
    mock_deal_repo
):
    flight = Flight(
        id="f1",
        origin="DEL",
        destination="DXB",
        departure_date=datetime(2026, 8, 15),
        price=Decimal("90"),
        airline="AI",
        stops=0,
        duration_minutes=240,
        deep_link="https://link"
    )
    mock_scanner.search_everywhere.return_value = [flight]

    history = PriceHistory(
        origin="DEL",
        destination="DXB",
        current_price=Decimal("90"),
        lowest_price=Decimal("80"),
        highest_price=Decimal("120"),
        rolling_average=Decimal("100"),
        first_seen=datetime.utcnow(),
        last_seen=datetime.utcnow(),
        observation_count=5
    )
    deal_result = DealResult(
        flight=flight,
        current_price=Decimal("90"),
        historical_stats=history,
        deal_score=10.0,
        deal_category="GOOD",
        savings=Decimal("10"),
        percentage_below_average=10.0
    )
    mock_deal_engine.process_flights.return_value = [deal_result]
    mock_formatter.format_summary.return_value = NotificationMessage(
        subject="sub", body_text="text", body_html="html"
    )

    mock_user_repo.get_all_active.return_value = [
        User(id="user1", username="u1", notification_enabled=True, baseline_sent=True)
    ]
    mock_notification_repo.get_last_sent_deal_for_route.return_value = None

    mock_telegram.send.side_effect = Exception("Telegram Timeout")

    pipeline = NotificationPipeline(
        scanner_service=mock_scanner,
        deal_engine=mock_deal_engine,
        notification_formatter=mock_formatter,
        telegram_sender=mock_telegram,
        user_repo=mock_user_repo,
        notification_repo=mock_notification_repo,
        deal_repo=mock_deal_repo,
        min_notification_category="GOOD",
        cooldown_seconds=3600,
        scan_origin="DEL"
    )

    await pipeline.execute()

    # Verify notification save calls. At least one must be the summary status (failed).
    saves = [call[0][0] for call in mock_notification_repo.save.call_args_list]
    failed_notifs = [n for n in saves if n.status == "failed"]
    assert len(failed_notifs) >= 1


@pytest.mark.asyncio
async def test_pipeline_provider_failure_does_not_crash(
    mock_scanner,
    mock_deal_engine,
    mock_formatter,
    mock_telegram,
    mock_user_repo,
    mock_notification_repo,
    mock_deal_repo
):
    mock_scanner.search_everywhere.side_effect = ProviderError("GQL Server Error")

    pipeline = NotificationPipeline(
        scanner_service=mock_scanner,
        deal_engine=mock_deal_engine,
        notification_formatter=mock_formatter,
        telegram_sender=mock_telegram,
        user_repo=mock_user_repo,
        notification_repo=mock_notification_repo,
        deal_repo=mock_deal_repo,
        min_notification_category="GOOD",
        cooldown_seconds=3600,
        scan_origin="DEL"
    )

    await pipeline.execute()

    mock_deal_engine.process_flights.assert_not_called()
