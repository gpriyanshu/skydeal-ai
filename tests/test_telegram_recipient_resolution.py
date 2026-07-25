import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock

from src.domain.entities import DealResult, Flight, PriceHistory, User, Deal, Notification
from src.use_cases.notification_pipeline import NotificationPipeline
from src.use_cases.notify_users import NotifyUsersUseCase


@pytest.fixture
def mock_scanner():
    service = MagicMock()
    service.search_everywhere = AsyncMock()
    return service


@pytest.fixture
def mock_deal_engine():
    engine = MagicMock()
    engine.process_flights = MagicMock()
    return engine


@pytest.fixture
def mock_formatter():
    formatter = MagicMock()
    formatter.format = MagicMock()
    formatter.format.return_value.subject = "Test Subject"
    formatter.format.return_value.body_html = "Test HTML"
    return formatter


@pytest.fixture
def mock_telegram():
    sender = MagicMock()
    sender.send = MagicMock(return_value=True)
    sender.default_chat_id = "123456789"
    return sender


@pytest.fixture
def mock_email_sender():
    sender = MagicMock()
    sender.send = MagicMock(return_value=True)
    return sender


def get_test_deal():
    flight = Flight(
        id="f_test",
        origin="DEL",
        destination="DXB",
        departure_date=datetime.utcnow() + timedelta(days=30),
        price=Decimal("90"),
        airline="AI",
        stops=0,
        duration_minutes=240,
        cabin_class="economy",
        deep_link="https://link"
    )
    return Deal(
        id="deal_test",
        flight=flight,
        category="Super Deal",
        discount_percentage=35.0,
        historical_average=Decimal("150"),
        detected_at=datetime.utcnow()
    )


def get_test_deal_result():
    flight = Flight(
        id="f_test",
        origin="DEL",
        destination="DXB",
        departure_date=datetime.utcnow() + timedelta(days=30),
        price=Decimal("90"),
        airline="AI",
        stops=0,
        duration_minutes=240,
        cabin_class="economy",
        deep_link="https://link"
    )
    history = PriceHistory(
        origin="DEL",
        destination="DXB",
        current_price=Decimal("90"),
        lowest_price=Decimal("80"),
        highest_price=Decimal("120"),
        rolling_average=Decimal("150"),
        first_seen=datetime.utcnow(),
        last_seen=datetime.utcnow(),
        observation_count=5
    )
    return DealResult(
        flight=flight,
        current_price=Decimal("90"),
        historical_stats=history,
        deal_score=10.0,
        deal_category="SUPER",
        savings=Decimal("60"),
        percentage_below_average=40.0
    )


@pytest.mark.asyncio
async def test_pipeline_valid_configured_chat_id_no_users(
    user_repo, deal_repo, notification_repo, mock_scanner, mock_deal_engine, mock_formatter, mock_telegram
):
    # Setup: No users registered in user_repo.
    # Default chat ID is configured.
    mock_telegram.default_chat_id = "123456789"
    
    deal_result = get_test_deal_result()
    mock_scanner.search_everywhere.return_value = [deal_result.flight]
    mock_deal_engine.process_flights.return_value = [deal_result]

    # Save deal to database to satisfy foreign key constraint
    deal = Deal(
        id=deal_result.flight.id,
        flight=deal_result.flight,
        category="Super Deal",
        discount_percentage=35.0,
        historical_average=Decimal("150"),
        detected_at=datetime.utcnow()
    )
    deal_repo.save(deal)

    pipeline = NotificationPipeline(
        scanner_service=mock_scanner,
        deal_engine=mock_deal_engine,
        notification_formatter=mock_formatter,
        telegram_sender=mock_telegram,
        user_repo=user_repo,
        notification_repo=notification_repo,
        deal_repo=deal_repo,
        min_notification_category="GOOD",
        cooldown_seconds=3600,
        scan_origin="DEL"
    )

    await pipeline.execute()

    # Verify message sent to default chat ID
    mock_telegram.send.assert_called_once()
    sent_notif = mock_telegram.send.call_args.kwargs.get('notification') or mock_telegram.send.call_args[0][0]
    assert sent_notif.user_id == "123456789"
    assert sent_notif.status == "sent"


@pytest.mark.asyncio
async def test_pipeline_missing_chat_id_no_users(
    user_repo, deal_repo, notification_repo, mock_scanner, mock_deal_engine, mock_formatter, mock_telegram
):
    # Setup: No users registered. TELEGRAM_DEFAULT_CHAT_ID is missing.
    mock_telegram.default_chat_id = None
    
    deal_result = get_test_deal_result()
    mock_scanner.search_everywhere.return_value = [deal_result.flight]
    mock_deal_engine.process_flights.return_value = [deal_result]

    # Save deal to database to satisfy foreign key constraint
    deal = Deal(
        id=deal_result.flight.id,
        flight=deal_result.flight,
        category="Super Deal",
        discount_percentage=35.0,
        historical_average=Decimal("150"),
        detected_at=datetime.utcnow()
    )
    deal_repo.save(deal)

    pipeline = NotificationPipeline(
        scanner_service=mock_scanner,
        deal_engine=mock_deal_engine,
        notification_formatter=mock_formatter,
        telegram_sender=mock_telegram,
        user_repo=user_repo,
        notification_repo=notification_repo,
        deal_repo=deal_repo,
        min_notification_category="GOOD",
        cooldown_seconds=3600,
        scan_origin="DEL"
    )

    await pipeline.execute()

    # Verify no message sent
    mock_telegram.send.assert_not_called()


@pytest.mark.asyncio
async def test_pipeline_registered_users_present(
    user_repo, deal_repo, notification_repo, mock_scanner, mock_deal_engine, mock_formatter, mock_telegram
):
    # Setup: Active users in database. Default chat ID configured.
    user = User(id="registered_user_id", username="test_user", notification_enabled=True)
    user_repo.save(user)
    mock_telegram.default_chat_id = "123456789"
    
    deal_result = get_test_deal_result()
    mock_scanner.search_everywhere.return_value = [deal_result.flight]
    mock_deal_engine.process_flights.return_value = [deal_result]

    # Save deal to database to satisfy foreign key constraint
    deal = Deal(
        id=deal_result.flight.id,
        flight=deal_result.flight,
        category="Super Deal",
        discount_percentage=35.0,
        historical_average=Decimal("150"),
        detected_at=datetime.utcnow()
    )
    deal_repo.save(deal)

    pipeline = NotificationPipeline(
        scanner_service=mock_scanner,
        deal_engine=mock_deal_engine,
        notification_formatter=mock_formatter,
        telegram_sender=mock_telegram,
        user_repo=user_repo,
        notification_repo=notification_repo,
        deal_repo=deal_repo,
        min_notification_category="GOOD",
        cooldown_seconds=3600,
        scan_origin="DEL"
    )

    await pipeline.execute()

    # Verify message sent only to the registered user, not to the default chat ID
    mock_telegram.send.assert_called_once()
    sent_notif = mock_telegram.send.call_args.kwargs.get('notification') or mock_telegram.send.call_args[0][0]
    assert sent_notif.user_id == "registered_user_id"
    assert sent_notif.user_id != "123456789"


@pytest.mark.asyncio
async def test_pipeline_send_failure(
    user_repo, deal_repo, notification_repo, mock_scanner, mock_deal_engine, mock_formatter, mock_telegram
):
    # Setup: No users registered. Send fails.
    mock_telegram.default_chat_id = "123456789"
    mock_telegram.send.return_value = False
    
    deal_result = get_test_deal_result()
    mock_scanner.search_everywhere.return_value = [deal_result.flight]
    mock_deal_engine.process_flights.return_value = [deal_result]

    # Save deal to database to satisfy foreign key constraint
    deal = Deal(
        id=deal_result.flight.id,
        flight=deal_result.flight,
        category="Super Deal",
        discount_percentage=35.0,
        historical_average=Decimal("150"),
        detected_at=datetime.utcnow()
    )
    deal_repo.save(deal)

    pipeline = NotificationPipeline(
        scanner_service=mock_scanner,
        deal_engine=mock_deal_engine,
        notification_formatter=mock_formatter,
        telegram_sender=mock_telegram,
        user_repo=user_repo,
        notification_repo=notification_repo,
        deal_repo=deal_repo,
        min_notification_category="GOOD",
        cooldown_seconds=3600,
        scan_origin="DEL"
    )

    await pipeline.execute()

    # Verify message attempt was logged with failure
    mock_telegram.send.assert_called_once()
    sent_notif = mock_telegram.send.call_args.kwargs.get('notification') or mock_telegram.send.call_args[0][0]
    assert sent_notif.status == "failed"


def test_usecase_valid_configured_chat_id_no_users(
    user_repo, deal_repo, notification_repo, mock_telegram, mock_email_sender
):
    # Setup: No users registered in database. Default chat ID configured.
    mock_telegram.default_chat_id = "123456789"
    deal = get_test_deal()
    deal_repo.save(deal)

    usecase = NotifyUsersUseCase(
        user_repo=user_repo,
        notification_repo=notification_repo,
        telegram_sender=mock_telegram,
        email_sender=mock_email_sender,
        cooldown_seconds=3600
    )

    usecase.execute([deal])

    # Verify Telegram notification sent to default chat ID
    mock_telegram.send.assert_called_once()
    sent_notif = mock_telegram.send.call_args[0][0]
    assert sent_notif.user_id == "123456789"
    assert sent_notif.status == "sent"
    # Email sender should not be called since there is no user email config
    mock_email_sender.send.assert_not_called()


def test_usecase_missing_chat_id_no_users(
    user_repo, deal_repo, notification_repo, mock_telegram, mock_email_sender
):
    # Setup: No users registered, default chat ID missing.
    mock_telegram.default_chat_id = None
    deal = get_test_deal()
    deal_repo.save(deal)

    usecase = NotifyUsersUseCase(
        user_repo=user_repo,
        notification_repo=notification_repo,
        telegram_sender=mock_telegram,
        email_sender=mock_email_sender,
        cooldown_seconds=3600
    )

    usecase.execute([deal])

    mock_telegram.send.assert_not_called()


def test_usecase_registered_users_present(
    user_repo, deal_repo, notification_repo, mock_telegram, mock_email_sender
):
    # Setup: Registered user present.
    user = User(id="registered_user_id", username="test_user", notification_enabled=True)
    user_repo.save(user)
    mock_telegram.default_chat_id = "123456789"
    deal = get_test_deal()
    deal_repo.save(deal)

    usecase = NotifyUsersUseCase(
        user_repo=user_repo,
        notification_repo=notification_repo,
        telegram_sender=mock_telegram,
        email_sender=mock_email_sender,
        cooldown_seconds=3600
    )

    usecase.execute([deal])

    # Verify Telegram notification sent to registered user, NOT default chat ID
    mock_telegram.send.assert_called_once()
    sent_notif = mock_telegram.send.call_args[0][0]
    assert sent_notif.user_id == "registered_user_id"
