import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock

from src.config import Settings
from src.domain.entities import Deal, DealResult, Flight, PriceHistory, Notification, User
from src.domain.notification_formatter import NotificationFormatter
from src.use_cases.notification_pipeline import NotificationPipeline


@pytest.fixture
def summary_settings() -> Settings:
    return Settings(
        MAX_DEALS_PER_SCAN=5,
        ALLOWED_DESTINATION_COUNTRIES=[],
        TELEGRAM_COOLDOWN_SECONDS=3600,
        MIN_NOTIFICATION_CATEGORY="GOOD",
        FALLBACK_EXCHANGE_RATES={"USD": 1.0, "INR": 83.5, "RUB": 90.0, "EUR": 0.92}
    )


@pytest.mark.asyncio
async def test_summary_sorting_and_limit(summary_settings):
    # Tests that sorting order is correctly applied:
    # 1. Highest Deal Score
    # 2. Highest Savings %
    # 3. Lowest INR Price
    # And that the summary length is capped at MAX_DEALS_PER_SCAN (5)
    
    scanner = MagicMock()
    # Mocking search_everywhere returning 8 flights
    flights = [
        Flight(id="f1", origin="DEL", destination="BKK", departure_date=datetime.utcnow() + timedelta(days=10), price=Decimal("9000"), airline="AI", stops=0, duration_minutes=240),
        Flight(id="f2", origin="DEL", destination="SIN", departure_date=datetime.utcnow() + timedelta(days=10), price=Decimal("10000"), airline="AI", stops=0, duration_minutes=240),
        Flight(id="f3", origin="DEL", destination="KUL", departure_date=datetime.utcnow() + timedelta(days=10), price=Decimal("8000"), airline="AI", stops=0, duration_minutes=240),
        Flight(id="f4", origin="DEL", destination="HAN", departure_date=datetime.utcnow() + timedelta(days=10), price=Decimal("7000"), airline="AI", stops=0, duration_minutes=240),
        Flight(id="f5", origin="DEL", destination="DPS", departure_date=datetime.utcnow() + timedelta(days=10), price=Decimal("12000"), airline="AI", stops=0, duration_minutes=240),
        Flight(id="f6", origin="DEL", destination="NRT", departure_date=datetime.utcnow() + timedelta(days=10), price=Decimal("18000"), airline="AI", stops=0, duration_minutes=240),
        Flight(id="f7", origin="DEL", destination="CDG", departure_date=datetime.utcnow() + timedelta(days=10), price=Decimal("25000"), airline="AI", stops=0, duration_minutes=240),
        Flight(id="f8", origin="DEL", destination="FCO", departure_date=datetime.utcnow() + timedelta(days=10), price=Decimal("28000"), airline="AI", stops=0, duration_minutes=240),
    ]
    scanner.search_everywhere = AsyncMock(return_value=flights)

    # 8 deal results with varying scores and categories
    hist = PriceHistory(origin="DEL", destination="BKK", current_price=Decimal("1000"), lowest_price=Decimal("800"), highest_price=Decimal("2000"), rolling_average=Decimal("15000"), first_seen=datetime.utcnow(), last_seen=datetime.utcnow())
    
    deal_results = [
        # Deal score 90.0, Savings 40.0%
        DealResult(flight=flights[0], current_price=Decimal("9000"), historical_stats=hist, deal_score=90.0, deal_category="SUPER", savings=Decimal("6000"), percentage_below_average=40.0),
        # Deal score 95.0, Savings 45.0%
        DealResult(flight=flights[1], current_price=Decimal("10000"), historical_stats=hist, deal_score=95.0, deal_category="SUPER", savings=Decimal("8000"), percentage_below_average=45.0),
        # Deal score 95.0, Savings 45.0% but lower price (8000 vs 10000)
        DealResult(flight=flights[2], current_price=Decimal("8000"), historical_stats=hist, deal_score=95.0, deal_category="SUPER", savings=Decimal("8000"), percentage_below_average=45.0),
        # Deal score 80.0, Savings 30.0%
        DealResult(flight=flights[3], current_price=Decimal("7000"), historical_stats=hist, deal_score=80.0, deal_category="GREAT", savings=Decimal("3000"), percentage_below_average=30.0),
        # Deal score 70.0
        DealResult(flight=flights[4], current_price=Decimal("12000"), historical_stats=hist, deal_score=70.0, deal_category="GOOD", savings=Decimal("4000"), percentage_below_average=25.0),
        # Deal score 60.0
        DealResult(flight=flights[5], current_price=Decimal("18000"), historical_stats=hist, deal_score=60.0, deal_category="GOOD", savings=Decimal("2000"), percentage_below_average=10.0),
        # Deal score 50.0
        DealResult(flight=flights[6], current_price=Decimal("25000"), historical_stats=hist, deal_score=50.0, deal_category="GOOD", savings=Decimal("1000"), percentage_below_average=5.0),
        # Deal score 40.0
        DealResult(flight=flights[7], current_price=Decimal("28000"), historical_stats=hist, deal_score=40.0, deal_category="GOOD", savings=Decimal("500"), percentage_below_average=2.0),
    ]

    deal_engine = MagicMock()
    deal_engine.process_flights = MagicMock(return_value=deal_results)

    formatter = NotificationFormatter()
    telegram_sender = MagicMock()
    telegram_sender.default_chat_id = "12345"
    telegram_sender.send = MagicMock(return_value=True)

    user_repo = MagicMock()
    user_repo.get_all_active = MagicMock(return_value=[
        User(id="12345", username="Test User", notification_enabled=True, baseline_sent=True)
    ])

    notification_repo = MagicMock()
    # No last sent deals (first run)
    notification_repo.get_last_sent_deal_for_route = MagicMock(return_value=None)

    deal_repo = MagicMock()

    pipeline = NotificationPipeline(
        scanner_service=scanner,
        deal_engine=deal_engine,
        notification_formatter=formatter,
        telegram_sender=telegram_sender,
        user_repo=user_repo,
        notification_repo=notification_repo,
        deal_repo=deal_repo,
        min_notification_category="GOOD",
        cooldown_seconds=3600,
        settings=summary_settings
    )

    await pipeline.execute()

    # Verify formatting call received exactly top 5 deals in sorted order:
    # Top 5 should be:
    # 1. f3 (score 95, savings 45, price 8000)
    # 2. f2 (score 95, savings 45, price 10000)
    # 3. f1 (score 90)
    # 4. f4 (score 80)
    # 5. f5 (score 70)
    # verify formatter format_summary call args
    telegram_sender.send.assert_called_once()
    body_html = telegram_sender.send.call_args[1]["message_body"]
    
    assert "KUL" in body_html  # f3
    assert "SIN" in body_html  # f2
    assert "BKK" in body_html  # f1
    assert "HAN" in body_html  # f4
    assert "DPS" in body_html  # f5
    assert "NRT" not in body_html  # f6 (limit cap excluded it)


@pytest.mark.asyncio
async def test_country_diversity_cap(summary_settings):
    # Tests country diversity where max 2 deals per country are selected first.
    # We will simulate 6 deals, 4 to Thailand (BKK, DMK, HKT, KBV) and 2 to Vietnam (HAN, SGN).
    # Whitelist allows at most 2 to Thailand, so top 2 Thailand and 2 Vietnam should be selected (total 4).
    
    scanner = MagicMock()
    flights = [
        Flight(id="tp_bkk", origin="DEL", destination="BKK", departure_date=datetime.utcnow() + timedelta(days=10), price=Decimal("9000"), airline="AI", stops=0, duration_minutes=240),
        Flight(id="tp_dmk", origin="DEL", destination="DMK", departure_date=datetime.utcnow() + timedelta(days=10), price=Decimal("9500"), airline="AI", stops=0, duration_minutes=240),
        Flight(id="tp_hkt", origin="DEL", destination="HKT", departure_date=datetime.utcnow() + timedelta(days=10), price=Decimal("10000"), airline="AI", stops=0, duration_minutes=240),
        Flight(id="tp_kbv", origin="DEL", destination="KBV", departure_date=datetime.utcnow() + timedelta(days=10), price=Decimal("10500"), airline="AI", stops=0, duration_minutes=240),
        Flight(id="tp_han", origin="DEL", destination="HAN", departure_date=datetime.utcnow() + timedelta(days=10), price=Decimal("12000"), airline="AI", stops=0, duration_minutes=240),
        Flight(id="tp_sgn", origin="DEL", destination="SGN", departure_date=datetime.utcnow() + timedelta(days=10), price=Decimal("13000"), airline="AI", stops=0, duration_minutes=240),
    ]
    scanner.search_everywhere = AsyncMock(return_value=flights)

    hist = PriceHistory(origin="DEL", destination="BKK", current_price=Decimal("1000"), lowest_price=Decimal("800"), highest_price=Decimal("2000"), rolling_average=Decimal("15000"), first_seen=datetime.utcnow(), last_seen=datetime.utcnow())
    
    deal_results = [
        # Thailand deals (scores: 95, 90, 85, 80)
        DealResult(flight=flights[0], current_price=Decimal("9000"), historical_stats=hist, deal_score=95.0, deal_category="SUPER", savings=Decimal("6000"), percentage_below_average=40.0),
        DealResult(flight=flights[1], current_price=Decimal("9500"), historical_stats=hist, deal_score=90.0, deal_category="SUPER", savings=Decimal("5500"), percentage_below_average=35.0),
        DealResult(flight=flights[2], current_price=Decimal("10000"), historical_stats=hist, deal_score=85.0, deal_category="GREAT", savings=Decimal("5000"), percentage_below_average=30.0),
        DealResult(flight=flights[3], current_price=Decimal("10500"), historical_stats=hist, deal_score=80.0, deal_category="GREAT", savings=Decimal("4500"), percentage_below_average=25.0),
        # Vietnam deals (scores: 75, 70)
        DealResult(flight=flights[4], current_price=Decimal("12000"), historical_stats=hist, deal_score=75.0, deal_category="GOOD", savings=Decimal("3000"), percentage_below_average=20.0),
        DealResult(flight=flights[5], current_price=Decimal("13000"), historical_stats=hist, deal_score=70.0, deal_category="GOOD", savings=Decimal("2000"), percentage_below_average=15.0),
    ]

    deal_engine = MagicMock()
    deal_engine.process_flights = MagicMock(return_value=deal_results)

    formatter = NotificationFormatter()
    telegram_sender = MagicMock()
    telegram_sender.default_chat_id = "12345"
    telegram_sender.send = MagicMock(return_value=True)

    user_repo = MagicMock()
    user_repo.get_all_active = MagicMock(return_value=[
        User(id="12345", username="Test User", notification_enabled=True, baseline_sent=True)
    ])

    notification_repo = MagicMock()
    notification_repo.get_last_sent_deal_for_route = MagicMock(return_value=None)
    deal_repo = MagicMock()

    summary_settings.MAX_DEALS_PER_SCAN = 4

    pipeline = NotificationPipeline(
        scanner_service=scanner,
        deal_engine=deal_engine,
        notification_formatter=formatter,
        telegram_sender=telegram_sender,
        user_repo=user_repo,
        notification_repo=notification_repo,
        deal_repo=deal_repo,
        min_notification_category="GOOD",
        cooldown_seconds=3600,
        settings=summary_settings
    )

    await pipeline.execute()

    body_html = telegram_sender.send.call_args[1]["message_body"]
    
    # Thailand top 2 should be included (BKK, DMK)
    assert "BKK" in body_html
    assert "DMK" in body_html
    # HKT and KBV should NOT be in body_html because Vietnam deals (HAN, SGN) had priority over them to preserve diversity
    assert "HKT" not in body_html
    assert "KBV" not in body_html
    assert "HAN" in body_html
    assert "SGN" in body_html


@pytest.mark.asyncio
async def test_duplicate_suppression_and_cooldown(summary_settings):
    # Verify that:
    # 1. If flight has not changed price/score, it's suppressed during cooldown.
    # 2. If price changes, it's allowed.
    # 3. If score improves, it's allowed.
    # 4. If cooldown expires, it's allowed.
    
    scanner = MagicMock()
    flights = [
        # Route 1: BKK (same price, same score) -> suppressed
        Flight(id="f1", origin="DEL", destination="BKK", departure_date=datetime.utcnow() + timedelta(days=10), price=Decimal("9000"), airline="AI", stops=0, duration_minutes=240),
        # Route 2: SIN (price changed: 12000 -> 10000) -> allowed
        Flight(id="f2", origin="DEL", destination="SIN", departure_date=datetime.utcnow() + timedelta(days=10), price=Decimal("10000"), airline="AI", stops=0, duration_minutes=240),
        # Route 3: KUL (score improved: 60.0 -> 80.0) -> allowed
        Flight(id="f3", origin="DEL", destination="KUL", departure_date=datetime.utcnow() + timedelta(days=10), price=Decimal("8000"), airline="AI", stops=0, duration_minutes=240),
        # Route 4: HAN (cooldown expired: last sent was 2 hours ago) -> allowed
        Flight(id="f4", origin="DEL", destination="HAN", departure_date=datetime.utcnow() + timedelta(days=10), price=Decimal("12000"), airline="AI", stops=0, duration_minutes=240),
    ]
    scanner.search_everywhere = AsyncMock(return_value=flights)

    hist = PriceHistory(origin="DEL", destination="BKK", current_price=Decimal("1000"), lowest_price=Decimal("800"), highest_price=Decimal("2000"), rolling_average=Decimal("15000"), first_seen=datetime.utcnow(), last_seen=datetime.utcnow())
    
    deal_results = [
        DealResult(flight=flights[0], current_price=Decimal("9000"), historical_stats=hist, deal_score=90.0, deal_category="SUPER", savings=Decimal("6000"), percentage_below_average=40.0),
        DealResult(flight=flights[1], current_price=Decimal("10000"), historical_stats=hist, deal_score=95.0, deal_category="SUPER", savings=Decimal("8000"), percentage_below_average=45.0),
        DealResult(flight=flights[2], current_price=Decimal("8000"), historical_stats=hist, deal_score=80.0, deal_category="GREAT", savings=Decimal("8000"), percentage_below_average=40.0),
        DealResult(flight=flights[3], current_price=Decimal("12000"), historical_stats=hist, deal_score=75.0, deal_category="GOOD", savings=Decimal("3000"), percentage_below_average=20.0),
    ]

    deal_engine = MagicMock()
    deal_engine.process_flights = MagicMock(return_value=deal_results)

    formatter = NotificationFormatter()
    telegram_sender = MagicMock()
    telegram_sender.default_chat_id = "12345"
    telegram_sender.send = MagicMock(return_value=True)

    user_repo = MagicMock()
    user_repo.get_all_active = MagicMock(return_value=[
        User(id="12345", username="Test User", notification_enabled=True, baseline_sent=True)
    ])

    # Stub notification repo historical deals
    last_sent_bkk = Deal(id="f1", flight=flights[0], category="Super Deal", discount_percentage=90.0, historical_average=Decimal("15000"), detected_at=datetime.utcnow() - timedelta(minutes=15))
    last_sent_sin = Deal(id="f2", flight=Flight(id="f2_old", origin="DEL", destination="SIN", departure_date=datetime.utcnow(), price=Decimal("12000"), airline="AI", stops=0, duration_minutes=240), category="Super Deal", discount_percentage=45.0, historical_average=Decimal("15000"), detected_at=datetime.utcnow() - timedelta(minutes=15))
    last_sent_kul = Deal(id="f3", flight=flights[2], category="Great Deal", discount_percentage=30.0, historical_average=Decimal("15000"), detected_at=datetime.utcnow() - timedelta(minutes=15))
    last_sent_han = Deal(id="f4", flight=flights[3], category="Good Deal", discount_percentage=20.0, historical_average=Decimal("15000"), detected_at=datetime.utcnow() - timedelta(hours=2))

    def mock_get_last_sent(user_id, origin, destination):
        if destination == "BKK":
            return last_sent_bkk
        elif destination == "SIN":
            return last_sent_sin
        elif destination == "KUL":
            return last_sent_kul
        elif destination == "HAN":
            return last_sent_han
        return None

    notification_repo = MagicMock()
    notification_repo.get_last_sent_deal_for_route = MagicMock(side_effect=mock_get_last_sent)
    deal_repo = MagicMock()

    pipeline = NotificationPipeline(
        scanner_service=scanner,
        deal_engine=deal_engine,
        notification_formatter=formatter,
        telegram_sender=telegram_sender,
        user_repo=user_repo,
        notification_repo=notification_repo,
        deal_repo=deal_repo,
        min_notification_category="GOOD",
        cooldown_seconds=3600,  # 1 hour cooldown
        settings=summary_settings
    )

    await pipeline.execute()

    body_html = telegram_sender.send.call_args[1]["message_body"]
    
    assert "BKK" not in body_html  # Route 1: suppressed due to active cooldown with identical details
    assert "SIN" in body_html      # Route 2: price changed, allowed!
    assert "KUL" in body_html      # Route 3: score improved, allowed!
    assert "HAN" in body_html      # Route 4: cooldown expired, allowed!


@pytest.mark.asyncio
async def test_baseline_notification_new_user_first_scan(summary_settings):
    # Tests that a new user (baseline_sent=False) receives the special "SkyDeal AI Started" summary on their first scan
    scanner = MagicMock()
    flights = [
        Flight(id="f1", origin="DEL", destination="BKK", departure_date=datetime.now(timezone.utc) + timedelta(days=10), price=Decimal("9000"), airline="AI", stops=0, duration_minutes=240),
        Flight(id="f2", origin="DEL", destination="SIN", departure_date=datetime.now(timezone.utc) + timedelta(days=10), price=Decimal("10000"), airline="AI", stops=0, duration_minutes=240),
    ]
    scanner.search_everywhere = AsyncMock(return_value=flights)

    hist = PriceHistory(origin="DEL", destination="BKK", current_price=Decimal("1000"), lowest_price=Decimal("800"), highest_price=Decimal("2000"), rolling_average=Decimal("9000"), first_seen=datetime.now(timezone.utc), last_seen=datetime.now(timezone.utc))
    
    deal_results = [
        DealResult(flight=flights[0], current_price=Decimal("9000"), historical_stats=hist, deal_score=0.0, deal_category="NORMAL", savings=Decimal("0"), percentage_below_average=0.0),
        DealResult(flight=flights[1], current_price=Decimal("10000"), historical_stats=hist, deal_score=0.0, deal_category="NORMAL", savings=Decimal("0"), percentage_below_average=0.0),
    ]

    deal_engine = MagicMock()
    deal_engine.process_flights = MagicMock(return_value=deal_results)

    formatter = NotificationFormatter()
    telegram_sender = MagicMock()
    telegram_sender.default_chat_id = "12345"
    telegram_sender.send = MagicMock(return_value=True)

    # User with baseline_sent=False
    new_user = User(id="user_new", username="New Subscriber", notification_enabled=True, baseline_sent=False)
    user_repo = MagicMock()
    user_repo.get_all_active = MagicMock(return_value=[new_user])
    user_repo.save = MagicMock()

    notification_repo = MagicMock()
    deal_repo = MagicMock()

    pipeline = NotificationPipeline(
        scanner_service=scanner,
        deal_engine=deal_engine,
        notification_formatter=formatter,
        telegram_sender=telegram_sender,
        user_repo=user_repo,
        notification_repo=notification_repo,
        deal_repo=deal_repo,
        min_notification_category="GOOD",
        cooldown_seconds=3600,
        settings=summary_settings
    )

    await pipeline.execute()

    # Verify Telegram notification is sent
    telegram_sender.send.assert_called_once()
    header = telegram_sender.send.call_args[1]["message_header"]
    assert header == "🚀 SkyDeal AI Started"
    
    body = telegram_sender.send.call_args[1]["message_body"]
    assert "Flight monitoring has started successfully!" in body
    assert "Baseline Price: <b>₹9,000</b>" in body
    
    # Verify user baseline_sent is updated and saved
    user_repo.save.assert_called()
    saved_user = next(call[0][0] for call in user_repo.save.call_args_list if isinstance(call[0][0], User))
    assert saved_user.baseline_sent is True


@pytest.mark.asyncio
async def test_baseline_notification_subsequent_scans_existing_user(summary_settings):
    # Tests that an existing user (baseline_sent=True) does NOT receive baseline notifications,
    # and since normal category deals do not qualify, no alert is sent.
    scanner = MagicMock()
    flights = [
        Flight(id="f1", origin="DEL", destination="BKK", departure_date=datetime.now(timezone.utc) + timedelta(days=10), price=Decimal("9000"), airline="AI", stops=0, duration_minutes=240),
    ]
    scanner.search_everywhere = AsyncMock(return_value=flights)

    hist = PriceHistory(origin="DEL", destination="BKK", current_price=Decimal("1000"), lowest_price=Decimal("800"), highest_price=Decimal("2000"), rolling_average=Decimal("9000"), first_seen=datetime.now(timezone.utc), last_seen=datetime.now(timezone.utc))
    
    deal_results = [
        DealResult(flight=flights[0], current_price=Decimal("9000"), historical_stats=hist, deal_score=0.0, deal_category="NORMAL", savings=Decimal("0"), percentage_below_average=0.0),
    ]

    deal_engine = MagicMock()
    deal_engine.process_flights = MagicMock(return_value=deal_results)

    formatter = NotificationFormatter()
    telegram_sender = MagicMock()
    telegram_sender.default_chat_id = "12345"
    telegram_sender.send = MagicMock(return_value=True)

    # Existing user with baseline_sent=True
    existing_user = User(id="user_existing", username="Existing Subscriber", notification_enabled=True, baseline_sent=True)
    user_repo = MagicMock()
    user_repo.get_all_active = MagicMock(return_value=[existing_user])
    user_repo.save = MagicMock()

    notification_repo = MagicMock()
    notification_repo.get_last_sent_deal_for_route = MagicMock(return_value=None)
    deal_repo = MagicMock()

    pipeline = NotificationPipeline(
        scanner_service=scanner,
        deal_engine=deal_engine,
        notification_formatter=formatter,
        telegram_sender=telegram_sender,
        user_repo=user_repo,
        notification_repo=notification_repo,
        deal_repo=deal_repo,
        min_notification_category="GOOD",
        cooldown_seconds=3600,
        settings=summary_settings
    )

    await pipeline.execute()

    # No Telegram alert since no deals qualify and baseline is already sent
    telegram_sender.send.assert_not_called()
