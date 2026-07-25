import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

from src.adapters.providers.constants import INDIAN_AIRPORTS, AIRPORT_TO_COUNTRY
from src.adapters.providers.mock import MockFlightProvider
from src.config import Settings
from src.domain.entities import DealResult, Flight, PriceHistory
from src.domain.notification_formatter import NotificationFormatter


@pytest.fixture
def base_settings() -> Settings:
    return Settings(
        ALLOWED_DESTINATION_COUNTRIES=["Thailand", "Vietnam", "Singapore", "Malaysia", "Indonesia", "Japan", "South Korea", "United Arab Emirates", "Germany", "France", "Italy"],
        MAX_DAYS_AHEAD=120,
        COUNTRY_MAX_BUDGETS={
            "thailand": 11000.0,
            "vietnam": 13000.0,
            "malaysia": 12000.0,
            "singapore": 12000.0,
            "indonesia": 12000.0,
            "united arab emirates": 12000.0,
            "japan": 20000.0,
            "south korea": 20000.0,
            "germany": 20000.0,
            "france": 20000.0,
            "italy": 20000.0,
        },
        FALLBACK_EXCHANGE_RATES={"USD": 1.0, "INR": 83.5, "RUB": 90.0, "EUR": 0.92}
    )


def test_allowed_country_filtering(base_settings):
    # Only allowed countries: Thailand, Singapore, Vietnam, etc.
    # We will test with a flight to LHR (United Kingdom - not in allowed countries list) and BKK (Thailand - in allowed list)
    provider = MockFlightProvider(settings=base_settings)
    flights = [
        Flight(
            id="f1", origin="DEL", destination="BKK", departure_date=datetime.utcnow() + timedelta(days=10),
            price=Decimal("9000"), airline="Indigo", stops=0, duration_minutes=240
        ),
        Flight(
            id="f2", origin="DEL", destination="LHR", departure_date=datetime.utcnow() + timedelta(days=10),
            price=Decimal("15000"), airline="Air India", stops=0, duration_minutes=540
        )
    ]
    filtered = provider._filter_and_sort_flights(flights)
    destinations = [f.destination for f in filtered]
    assert "BKK" in destinations
    assert "LHR" not in destinations


def test_empty_country_list(base_settings):
    # If ALLOWED_DESTINATION_COUNTRIES is empty, scan every international destination (including LHR)
    base_settings.ALLOWED_DESTINATION_COUNTRIES = []
    provider = MockFlightProvider(settings=base_settings)
    flights = [
        Flight(
            id="f1", origin="DEL", destination="BKK", departure_date=datetime.utcnow() + timedelta(days=10),
            price=Decimal("9000"), airline="Indigo", stops=0, duration_minutes=240
        ),
        Flight(
            id="f2", origin="DEL", destination="LHR", departure_date=datetime.utcnow() + timedelta(days=10),
            price=Decimal("15000"), airline="Air India", stops=0, duration_minutes=540
        )
    ]
    filtered = provider._filter_and_sort_flights(flights)
    destinations = [f.destination for f in filtered]
    assert "BKK" in destinations
    assert "LHR" in destinations


def test_country_budget_filtering(base_settings):
    # Thailand budget is 11,000. Singapore budget is 12,000.
    provider = MockFlightProvider(settings=base_settings)
    flights = [
        # BKK at 10,000 (<= 11,000) -> kept
        Flight(
            id="f1", origin="DEL", destination="BKK", departure_date=datetime.utcnow() + timedelta(days=10),
            price=Decimal("10000"), airline="Indigo", stops=0, duration_minutes=240
        ),
        # BKK at 12,000 (> 11,000) -> removed
        Flight(
            id="f2", origin="DEL", destination="BKK", departure_date=datetime.utcnow() + timedelta(days=10),
            price=Decimal("12000"), airline="Indigo", stops=0, duration_minutes=240
        ),
        # SIN at 12,000 (<= 12,000) -> kept
        Flight(
            id="f3", origin="DEL", destination="SIN", departure_date=datetime.utcnow() + timedelta(days=10),
            price=Decimal("12000"), airline="Singapore Airlines", stops=0, duration_minutes=280
        )
    ]
    filtered = provider._filter_and_sort_flights(flights)
    ids = [f.id for f in filtered]
    assert "f1" in ids
    assert "f2" not in ids
    assert "f3" in ids


def test_japan_budget_higher_than_thailand(base_settings):
    # Japan budget: 20000. Thailand budget: 11000.
    # Flight to Japan at 18000 is KEPT. Flight to Thailand at 18000 is REMOVED.
    provider = MockFlightProvider(settings=base_settings)
    flights = [
        Flight(
            id="f_japan", origin="DEL", destination="NRT", departure_date=datetime.utcnow() + timedelta(days=10),
            price=Decimal("18000"), airline="JAL", stops=0, duration_minutes=480
        ),
        Flight(
            id="f_thai", origin="DEL", destination="BKK", departure_date=datetime.utcnow() + timedelta(days=10),
            price=Decimal("18000"), airline="Indigo", stops=0, duration_minutes=240
        )
    ]
    filtered = provider._filter_and_sort_flights(flights)
    ids = [f.id for f in filtered]
    assert "f_japan" in ids
    assert "f_thai" not in ids


def test_departure_window_filtering(base_settings):
    # MAX_DAYS_AHEAD is 120.
    # Departure in 10 days (<= 120) -> kept.
    # Departure in 130 days (> 120) -> removed.
    provider = MockFlightProvider(settings=base_settings)
    flights = [
        Flight(
            id="f_kept", origin="DEL", destination="BKK", departure_date=datetime.utcnow() + timedelta(days=10),
            price=Decimal("9000"), airline="Indigo", stops=0, duration_minutes=240
        ),
        Flight(
            id="f_removed", origin="DEL", destination="BKK", departure_date=datetime.utcnow() + timedelta(days=130),
            price=Decimal("9000"), airline="Indigo", stops=0, duration_minutes=240
        )
    ]
    filtered = provider._filter_and_sort_flights(flights)
    ids = [f.id for f in filtered]
    assert "f_kept" in ids
    assert "f_removed" not in ids


def test_cheapest_first_sorting(base_settings):
    provider = MockFlightProvider(settings=base_settings)
    flights = [
        Flight(
            id="f_mid", origin="DEL", destination="BKK", departure_date=datetime.utcnow() + timedelta(days=10),
            price=Decimal("10000"), airline="Indigo", stops=0, duration_minutes=240
        ),
        Flight(
            id="f_high", origin="DEL", destination="BKK", departure_date=datetime.utcnow() + timedelta(days=10),
            price=Decimal("11000"), airline="Indigo", stops=0, duration_minutes=240
        ),
        Flight(
            id="f_low", origin="DEL", destination="BKK", departure_date=datetime.utcnow() + timedelta(days=10),
            price=Decimal("8000"), airline="Indigo", stops=0, duration_minutes=240
        )
    ]
    filtered = provider._filter_and_sort_flights(flights)
    ids = [f.id for f in filtered]
    assert ids == ["f_low", "f_mid", "f_high"]


def test_telegram_notification_rendering():
    formatter = NotificationFormatter()
    flight = Flight(
        id="f1", origin="DEL", destination="BKK", departure_date=datetime(2026, 8, 15),
        price=Decimal("8950"), airline="Thai AirAsia", stops=0, duration_minutes=240,
        deep_link="https://example.com/book"
    )
    history = PriceHistory(
        origin="DEL", destination="BKK", current_price=Decimal("8950"),
        lowest_price=Decimal("8000"), highest_price=Decimal("16000"),
        rolling_average=Decimal("15700"), first_seen=datetime.utcnow(),
        last_seen=datetime.utcnow()
    )
    deal = DealResult(
        flight=flight, current_price=Decimal("8950"), historical_stats=history,
        deal_score=92.0, deal_category="SUPER", savings=Decimal("6750"),
        percentage_below_average=43.0
    )

    msg = formatter.format(deal, format_type="detailed")
    
    # Assert exact premium layout elements
    assert "🚀 <b>SUPER DEAL</b>" in msg.body_html
    assert "🇹🇭 <b>Thailand</b>" in msg.body_html
    assert "✈ Delhi (DEL)" in msg.body_html
    assert "➡ Bangkok (BKK)" in msg.body_html
    assert "━━━━━━━━━━━━━━" in msg.body_html
    assert "💰 <b>Price</b>\n₹8,950" in msg.body_html
    assert "📉 <b>Historical Average</b>\n₹15,700" in msg.body_html
    assert "💸 <b>You Save</b>\n₹6,750 (43.0%)" in msg.body_html
    assert "🛫 <b>Departure</b>\n15 Aug 2026" in msg.body_html
    assert "🛩 <b>Airline</b>\nThai AirAsia" in msg.body_html
    assert "🏷 <b>Deal Score</b>\n92 / 100" in msg.body_html
