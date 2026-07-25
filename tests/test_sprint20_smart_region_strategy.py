import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from src.domain.entities import ConversationState, Flight, DealResult, PriceHistory, TravelGoal, User
from src.domain.conversation_service import ConversationService, SearchFilters
from src.adapters.database.conversation_state_repository import InMemoryConversationStateRepository
from src.use_cases.notification_pipeline import NotificationPipeline

def make_mock_intent(intent_name):
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
async def test_manual_worldwide_searches_still_work():
    # Verify that live manual searches for Germany, France, Italy work regardless of default alert region
    countries = ["Germany", "France", "Italy"]
    destinations = {"Germany": "FRA", "France": "CDG", "Italy": "FCO"}
    
    for country in countries:
        repo = InMemoryConversationStateRepository()
        ai_mock = MagicMock()
        goal_service = MagicMock()
        deal_engine = MagicMock()
        domain_deal = MagicMock()
        scanner = MagicMock()

        ai_mock.generate_structured_response.side_effect = [
            make_mock_intent("ASK_CHEAPEST_FLIGHTS"),
            SearchFilters(country=country, month="September", budget=50000.0)
        ]

        dest_code = destinations[country]
        f1 = Flight(
            id=f"flight_{country.lower()}", origin="DEL", destination=dest_code,
            departure_date=datetime(2026, 9, 15, tzinfo=timezone.utc),
            price=Decimal("25000"), airline="Lufthansa" if country == "Germany" else "Air France",
            stops=0, duration_minutes=480, deep_link="https://book.com"
        )
        deal = DealResult(
            flight=f1, current_price=Decimal("25000"), deal_category="GREAT", deal_score=85.0, savings=Decimal("10000"),
            percentage_below_average=28.5, historical_stats=PriceHistory(
                origin="DEL", destination=dest_code, current_price=Decimal("25000"), lowest_price=Decimal("20000"),
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
            settings=MagicMock(
                SCAN_ORIGINS=["DEL"],
                MAX_CONVERSATIONAL_RESULTS=3,
                DEFAULT_ALERT_REGION=["Japan", "Singapore"]  # Default alert region is Asia
            )
        )

        response = await service.handle_message_async("user_123", f"Cheapest flights to {country} in September")
        assert "🥇 Best Choice" in response
        assert country in response or dest_code in response

@pytest.mark.anyio
async def test_asia_automatic_scan_excludes_europe_and_preserves_europe_goals():
    # 1. Setup mock database repositories
    user_repo = MagicMock()
    travel_goal_repo = MagicMock()
    deal_repo = MagicMock()
    notification_repo = MagicMock()
    notification_repo.get_last_sent_deal_for_route.return_value = None
    telegram_sender = MagicMock()
    telegram_sender.default_chat_id = "chat_123"
    
    user = User(id="chat_123", username="Test User", notification_enabled=True, baseline_sent=True)
    user_repo.get_all_active.return_value = [user]

    # Setup active goal for Germany (Europe) to verify override works
    goal_germany = TravelGoal(
        id="goal_de", user_id="chat_123", country="Germany",
        start_date=datetime.now(timezone.utc) - timedelta(days=5),
        end_date=datetime.now(timezone.utc) + timedelta(days=60),
        budget_inr=Decimal("50000"), status="ACTIVE"
    )
    travel_goal_repo.get_active_goals.return_value = [goal_germany]

    # Mock Scanner to return both an Asia flight (Japan) and Europe flights (Germany)
    f_japan = Flight(
        id="f_jp", origin="DEL", destination="NRT",
        departure_date=datetime.now(timezone.utc) + timedelta(days=30),
        price=Decimal("15000"), airline="ANA", stops=0, duration_minutes=480
    )
    f_germany = Flight(
        id="f_de", origin="DEL", destination="FRA",
        departure_date=datetime.now(timezone.utc) + timedelta(days=30),
        price=Decimal("30000"), airline="LH", stops=0, duration_minutes=500
    )
    
    scanner_mock = MagicMock()
    scanner_mock.search_everywhere = AsyncMock(return_value=[f_japan, f_germany])

    # Mock DealEngine & Formatter
    deal_jp = DealResult(
        flight=f_japan, current_price=Decimal("15000"), deal_score=90.0, deal_category="SUPER", savings=Decimal("10000"),
        percentage_below_average=40.0,
        historical_stats=PriceHistory(
            origin="DEL", destination="NRT", current_price=Decimal("15000"), rolling_average=Decimal("25000"),
            lowest_price=Decimal("15000"), highest_price=Decimal("30000"), first_seen=datetime.now(timezone.utc), last_seen=datetime.now(timezone.utc)
        )
    )
    deal_de = DealResult(
        flight=f_germany, current_price=Decimal("30000"), deal_score=80.0, deal_category="GREAT", savings=Decimal("10000"),
        percentage_below_average=25.0,
        historical_stats=PriceHistory(
            origin="DEL", destination="FRA", current_price=Decimal("30000"), rolling_average=Decimal("40000"),
            lowest_price=Decimal("30000"), highest_price=Decimal("45000"), first_seen=datetime.now(timezone.utc), last_seen=datetime.now(timezone.utc)
        )
    )
    
    deal_engine = MagicMock()
    # Workflow 1 (daily scanner) will only receive Japan flight
    # Workflow 2 (goal scanner) will filter raw_flights for Germany goal and send Germany flight
    deal_engine.process_flights = MagicMock(side_effect=lambda flights: [deal_jp] if "NRT" in {f.destination for f in flights} else [deal_de])
    
    settings_mock = MagicMock()
    settings_mock.DEFAULT_ALERT_REGION = ["Japan", "Singapore", "Thailand"]  # Asia default region
    settings_mock.ALLOWED_DESTINATION_COUNTRIES = ["Japan", "Singapore", "Thailand"]
    settings_mock.COUNTRY_MAX_BUDGETS = {"japan": 20000, "germany": 50000}
    settings_mock.MAX_DAYS_AHEAD = 365
    settings_mock.MAX_DEALS_PER_SCAN = 10

    formatter = MagicMock()
    formatter.format_goal_summary.return_value = MagicMock(subject="Trigger Alert", body_html="Better Flight Found", body_text="Better Flight Found")

    pipeline = NotificationPipeline(
        scanner_service=scanner_mock,
        deal_engine=deal_engine,
        notification_formatter=formatter,
        telegram_sender=telegram_sender,
        user_repo=user_repo,
        notification_repo=notification_repo,
        deal_repo=deal_repo,
        travel_goal_repo=travel_goal_repo,
        settings=settings_mock
    )

    await pipeline.execute()

    # Assertions
    # 1. Verify that Workflow 1 (Daily Scanner) was called with only Asia flights (Japan)
    daily_flights_scanned = deal_engine.process_flights.call_args_list[0][0][0]
    destinations_scanned = {f.destination for f in daily_flights_scanned}
    assert "NRT" in destinations_scanned
    assert "FRA" not in destinations_scanned  # Europe (Germany) must be excluded from daily automatic scanning!

    # 2. Verify that Workflow 2 (Goal Scanner) correctly monitored Germany (Europe) because of explicit goal
    goal_flights_scanned = deal_engine.process_flights.call_args_list[1][0][0]
    assert len(goal_flights_scanned) == 1
    assert goal_flights_scanned[0].destination == "FRA"  # Germany goal was successfully processed!

@pytest.mark.anyio
async def test_scheduled_scanner_only_scans_configured_region():
    # If DEFAULT_ALERT_REGION is configured to EUROPE, it should scan Europe and exclude Asia
    user_repo = MagicMock()
    travel_goal_repo = MagicMock()
    deal_repo = MagicMock()
    notification_repo = MagicMock()
    notification_repo.get_last_sent_deal_for_route.return_value = None
    telegram_sender = MagicMock()
    
    user = User(id="chat_123", username="Test User", notification_enabled=True, baseline_sent=True)
    user_repo.get_all_active.return_value = [user]
    travel_goal_repo.get_active_goals.return_value = []

    f_japan = Flight(
        id="f_jp", origin="DEL", destination="NRT",
        departure_date=datetime.now(timezone.utc) + timedelta(days=30),
        price=Decimal("15000"), airline="ANA", stops=0, duration_minutes=480
    )
    f_germany = Flight(
        id="f_de", origin="DEL", destination="FRA",
        departure_date=datetime.now(timezone.utc) + timedelta(days=30),
        price=Decimal("30000"), airline="LH", stops=0, duration_minutes=500
    )
    
    scanner_mock = MagicMock()
    scanner_mock.search_everywhere = AsyncMock(return_value=[f_japan, f_germany])
    deal_engine = MagicMock()
    
    settings_mock = MagicMock()
    settings_mock.DEFAULT_ALERT_REGION = ["Germany", "France", "Italy"]  # Region changed to Europe!
    settings_mock.ALLOWED_DESTINATION_COUNTRIES = ["Germany", "France", "Italy"]
    settings_mock.COUNTRY_MAX_BUDGETS = {"japan": 20000, "germany": 50000}
    settings_mock.MAX_DAYS_AHEAD = 365
    settings_mock.MAX_DEALS_PER_SCAN = 10

    pipeline = NotificationPipeline(
        scanner_service=scanner_mock,
        deal_engine=deal_engine,
        notification_formatter=MagicMock(),
        telegram_sender=telegram_sender,
        user_repo=user_repo,
        notification_repo=notification_repo,
        deal_repo=deal_repo,
        travel_goal_repo=travel_goal_repo,
        settings=settings_mock
    )

    await pipeline.execute()

    # Verify Workflow 1 (Daily Scanner) was called with only Europe flights (Germany)
    daily_flights_scanned = deal_engine.process_flights.call_args_list[0][0][0]
    destinations_scanned = {f.destination for f in daily_flights_scanned}
    assert "FRA" in destinations_scanned
    assert "NRT" not in destinations_scanned  # Asia (Japan) must be excluded when region is set to Europe!
