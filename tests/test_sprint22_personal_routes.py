import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch

from src.config import Settings
from src.domain.entities import PersonalRoute, Flight, Deal, Notification, ConversationState, User
from src.adapters.database.connection import DatabaseManager
from src.adapters.database.repository import SQLitePersonalRouteRepository, SQLiteUserRepository
from src.domain.personal_route_service import PersonalRouteService
from src.domain.domestic_price_intelligence import DomesticPriceIntelligence
from src.use_cases.personal_route_scanner import PersonalRouteScanner
from src.domain.notification_formatter import NotificationFormatter
from src.domain.intent_classifier import IntentClassifier
from src.domain.conversation_service import ConversationService

@pytest.fixture
def temp_db_manager(tmp_path):
    db_file = tmp_path / "test_watchlist.db"
    db_manager = DatabaseManager(db_file)
    return db_manager

def test_personal_route_validation(temp_db_manager):
    user_repo = SQLiteUserRepository(temp_db_manager)
    user_repo.save(User(id="user1"))

    repo = SQLitePersonalRouteRepository(temp_db_manager)
    service = PersonalRouteService(repo)

    # 1. Invalid origin
    with pytest.raises(ValueError, match="Invalid origin airport code"):
        service.add_route("user1", "JFK", "DEL")

    # 2. Invalid destination
    with pytest.raises(ValueError, match="Invalid destination airport code"):
        service.add_route("user1", "BLR", "XYZ")

    # 3. Same origin and destination
    with pytest.raises(ValueError, match="Origin and destination airports cannot be the same"):
        service.add_route("user1", "BLR", "BLR")

    # 4. Valid route addition
    route = service.add_route("user1", "BLR", "DEL")
    assert route.origin_airport == "BLR"
    assert route.destination_airport == "DEL"
    assert route.enabled is True

def test_personal_route_crud_and_duplicates(temp_db_manager):
    user_repo = SQLiteUserRepository(temp_db_manager)
    user_repo.save(User(id="user2"))

    repo = SQLitePersonalRouteRepository(temp_db_manager)
    service = PersonalRouteService(repo)

    # Add route
    service.add_route("user2", "BLR", "LKO")
    
    # Verify duplicate prevention (should return same route and enable if disabled)
    route2 = service.add_route("user2", "BLR", "LKO")
    assert route2.origin_airport == "BLR"
    assert route2.destination_airport == "LKO"

    # Disable route
    service.disable_route("user2", "BLR", "LKO")
    routes = service.list_routes("user2")
    assert routes[0].enabled is False

    # Add again (re-enables)
    service.add_route("user2", "BLR", "LKO")
    routes = service.list_routes("user2")
    assert routes[0].enabled is True

    # Disable and enable route
    service.disable_route("user2", "BLR", "LKO")
    service.enable_route("user2", "BLR", "LKO")
    routes = service.list_routes("user2")
    assert routes[0].enabled is True

    # Remove route
    service.remove_route("user2", "BLR", "LKO")
    routes = service.list_routes("user2")
    assert len(routes) == 0

def test_domestic_price_intelligence():
    settings = Settings()
    intel = DomesticPriceIntelligence(settings)

    # BLR -> DEL price thresholds:
    # Excellent: < 4000 (SUPER)
    # Great: 4000-5000 (GREAT)
    # Good: 5000-6000 (GOOD)
    # Average: 6000-7500 (NORMAL)
    # Expensive: >= 7500 (NORMAL)

    assert intel.get_price_band("BLR", "DEL", Decimal("3500")) == "excellent"
    assert intel.classify_category("BLR", "DEL", Decimal("3500")) == "SUPER"
    assert intel.calculate_score("BLR", "DEL", Decimal("3500")) == 100

    assert intel.get_price_band("BLR", "DEL", Decimal("4500")) == "great"
    assert intel.classify_category("BLR", "DEL", Decimal("4500")) == "GREAT"
    assert intel.calculate_score("BLR", "DEL", Decimal("4500")) == 90

    assert intel.get_price_band("BLR", "DEL", Decimal("5500")) == "good"
    assert intel.classify_category("BLR", "DEL", Decimal("5500")) == "GOOD"
    assert intel.calculate_score("BLR", "DEL", Decimal("5500")) == 75

    assert intel.get_price_band("BLR", "DEL", Decimal("6500")) == "average"
    assert intel.classify_category("BLR", "DEL", Decimal("6500")) == "NORMAL"
    assert intel.calculate_score("BLR", "DEL", Decimal("6500")) == 50

    assert intel.get_price_band("BLR", "DEL", Decimal("8000")) == "expensive"
    assert intel.classify_category("BLR", "DEL", Decimal("8000")) == "NORMAL"
    assert intel.calculate_score("BLR", "DEL", Decimal("8000")) == 20

@pytest.mark.asyncio
async def test_personal_route_scanner_workflow(temp_db_manager):
    user_repo = SQLiteUserRepository(temp_db_manager)
    user_repo.save(User(id="user_scan"))

    route_repo = SQLitePersonalRouteRepository(temp_db_manager)
    service = PersonalRouteService(route_repo)
    service.add_route("user_scan", "BLR", "DEL")

    scanner_service = MagicMock()
    mock_flight = Flight(
        id="mock_dom_f1",
        origin="BLR",
        destination="DEL",
        departure_date=datetime(2026, 8, 15, tzinfo=timezone.utc),
        price=Decimal("4200"),
        airline="I5",
        stops=0,
        duration_minutes=150
    )
    scanner_service.search_route = AsyncMock(return_value=[mock_flight])

    telegram_sender = MagicMock()
    telegram_sender.send = MagicMock(return_value=True)

    notification_repo = MagicMock()
    deal_repo = MagicMock()
    notification_formatter = NotificationFormatter()
    domestic_price_intelligence = DomesticPriceIntelligence()

    scanner = PersonalRouteScanner(
        personal_route_repo=route_repo,
        scanner_service=scanner_service,
        telegram_sender=telegram_sender,
        notification_repo=notification_repo,
        deal_repo=deal_repo,
        notification_formatter=notification_formatter,
        domestic_price_intelligence=domestic_price_intelligence
    )

    results = await scanner.execute(departure_dates=["2026-08-15"])
    assert results["routes_loaded"] == 1
    assert results["flights_found"] == 1
    assert results["deals_generated"] == 1
    assert results["notifications_sent"] == 1

    # Verify deal saving
    deal_repo.save.assert_called_once()
    # Verify notification saving
    assert notification_repo.save.call_count == 2 # 1 for pending, 1 for sent update
    # Verify telegram send
    telegram_sender.send.assert_called_once()

def test_conversational_commands_intent_classification():
    ai_provider = MagicMock()
    classifier = IntentClassifier(ai_provider)

    assert classifier.classify_intent("Add BLR to DEL") == "ADD_PERSONAL_ROUTE"
    assert classifier.classify_intent("Add Bangalore to Lucknow") == "ADD_PERSONAL_ROUTE"
    assert classifier.classify_intent("Watch Chennai to Delhi") == "ADD_PERSONAL_ROUTE"
    assert classifier.classify_intent("Monitor BLR DEL") == "ADD_PERSONAL_ROUTE"

    assert classifier.classify_intent("Remove BLR DEL") == "REMOVE_PERSONAL_ROUTE"
    assert classifier.classify_intent("Pause BLR DEL") == "PAUSE_PERSONAL_ROUTE"
    assert classifier.classify_intent("Resume BLR DEL") == "RESUME_PERSONAL_ROUTE"
    assert classifier.classify_intent("Show my routes") == "SHOW_PERSONAL_ROUTES"

@pytest.mark.asyncio
async def test_conversational_commands_handling():
    state_repo = MagicMock()
    state_repo.get = MagicMock(return_value=ConversationState(user_id="user_cmd"))
    
    ai_provider = MagicMock()
    travel_goal_service = MagicMock()
    deal_engine = MagicMock()

    personal_route_service = MagicMock()
    personal_route_service.list_routes.return_value = [
        PersonalRoute(id="r1", user_id="user_cmd", origin_airport="BLR", destination_airport="DEL", enabled=True, created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
    ]

    conv_service = ConversationService(
        conversation_state_repo=state_repo,
        ai_provider=ai_provider,
        travel_goal_service=travel_goal_service,
        deal_engine=deal_engine,
        personal_route_service=personal_route_service
    )

    # 1. ADD_PERSONAL_ROUTE command handling
    response = await conv_service.handle_message_async("user_cmd", "Add BLR to DEL")
    personal_route_service.add_route.assert_called_once_with("user_cmd", "BLR", "DEL")
    assert "Route Watchlist Added!" in response

    # 2. REMOVE_PERSONAL_ROUTE command handling
    personal_route_service.remove_route.return_value = True
    response = await conv_service.handle_message_async("user_cmd", "Remove BLR DEL")
    personal_route_service.remove_route.assert_called_once_with("user_cmd", "BLR", "DEL")
    assert "Route Removed!" in response

    # 3. PAUSE_PERSONAL_ROUTE command handling
    personal_route_service.disable_route.return_value = True
    response = await conv_service.handle_message_async("user_cmd", "Pause BLR DEL")
    personal_route_service.disable_route.assert_called_once_with("user_cmd", "BLR", "DEL")
    assert "Route Paused!" in response

    # 4. RESUME_PERSONAL_ROUTE command handling
    personal_route_service.enable_route.return_value = True
    response = await conv_service.handle_message_async("user_cmd", "Resume BLR DEL")
    personal_route_service.enable_route.assert_called_once_with("user_cmd", "BLR", "DEL")
    assert "Route Resumed!" in response

    # 5. SHOW_PERSONAL_ROUTES command handling
    response = await conv_service.handle_message_async("user_cmd", "Show my routes")
    assert "Your Monitored Routes:" in response
    assert "BLR → DEL" in response
