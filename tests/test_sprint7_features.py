import time
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from src.adapters.providers.constants import INDIAN_AIRPORTS, AIRPORT_TO_COUNTRY
from src.adapters.providers.currency_converter import CurrencyConverter
from src.adapters.providers.mock import MockFlightProvider
from src.adapters.providers.travelpayouts import TravelPayoutsProvider
from src.config import Settings
from src.domain.entities import DealResult, Flight, PriceHistory
from src.domain.notification_formatter import NotificationFormatter


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        ALLOWED_DESTINATION_COUNTRIES=["Thailand", "Singapore", "Malaysia"],
        FALLBACK_EXCHANGE_RATES={"USD": 1.0, "INR": 83.5, "RUB": 90.0, "EUR": 0.92},
        COUNTRY_MAX_BUDGETS={}
    )


def test_domestic_flights_removed_and_international_retained(test_settings):
    # Verify that domestic flights are removed and international ones are retained
    provider = MockFlightProvider(settings=test_settings)
    flights = [
        Flight(
            id="f1", origin="DEL", destination="BOM", departure_date=datetime.utcnow(),
            price=Decimal("5000"), airline="Indigo", stops=0, duration_minutes=120
        ),
        Flight(
            id="f2", origin="DEL", destination="LKO", departure_date=datetime.utcnow(),
            price=Decimal("3000"), airline="Indigo", stops=0, duration_minutes=60
        ),
        Flight(
            id="f3", origin="DEL", destination="BKK", departure_date=datetime.utcnow(),
            price=Decimal("15000"), airline="Thai Airways", stops=0, duration_minutes=240
        ),
        # SIN is in Thailand/Singapore/Malaysia (allowed list)
        Flight(
            id="f4", origin="DEL", destination="SIN", departure_date=datetime.utcnow(),
            price=Decimal("12000"), airline="Singapore Airlines", stops=0, duration_minutes=280
        ),
        # LHR is international but United Kingdom is not in allowed list
        Flight(
            id="f5", origin="DEL", destination="LHR", departure_date=datetime.utcnow(),
            price=Decimal("45000"), airline="Air India", stops=0, duration_minutes=540
        )
    ]

    filtered = provider._filter_and_sort_flights(flights)
    destinations = [f.destination for f in filtered]
    
    assert "BOM" not in destinations
    assert "LKO" not in destinations
    assert "LHR" not in destinations
    assert "BKK" in destinations
    assert "SIN" in destinations


def test_inr_conversion(test_settings):
    # Test USD to INR and RUB to INR conversion
    converter = CurrencyConverter(fallback_rates=test_settings.FALLBACK_EXCHANGE_RATES)
    # Mock rates so we don't hit the API
    converter.rates = {"USD": 1.0, "INR": 80.0, "RUB": 90.0, "EUR": 0.9}
    converter.last_fetched = time.time()

    usd_val = Decimal("100")
    rub_val = Decimal("900")
    
    inr_from_usd = converter.convert_to_inr(usd_val, "USD")
    inr_from_rub = converter.convert_to_inr(rub_val, "RUB")
    
    # 100 USD = 8000 INR
    assert inr_from_usd == Decimal("8000.0")
    # 900 RUB = 10 USD = 800 INR
    assert inr_from_rub == Decimal("800.0")


def test_exchange_rate_cache(test_settings):
    # Test that rates are cached and not fetched again within 12 hours
    converter = CurrencyConverter(fallback_rates=test_settings.FALLBACK_EXCHANGE_RATES)
    
    with patch("httpx.get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"result": "success", "rates": {"USD": 1.0, "INR": 82.0}}
        )
        
        # First call fetches rates
        converter.convert_to_inr(Decimal("10"), "USD")
        assert mock_get.call_count == 1
        
        # Second call uses cache
        converter.convert_to_inr(Decimal("20"), "USD")
        assert mock_get.call_count == 1


def test_exchange_rate_fallback(test_settings):
    # Test that if API fails, fallback rates are used
    converter = CurrencyConverter(fallback_rates=test_settings.FALLBACK_EXCHANGE_RATES)
    
    with patch("httpx.get", side_effect=Exception("API Down")):
        # First call triggers fetch, fails, loads fallback rates
        inr_val = converter.convert_to_inr(Decimal("100"), "USD")
        # Fallback rate is 83.5
        assert inr_val == Decimal("8350.0")


def test_country_filtering(test_settings):
    # With allowed list: Thailand and Singapore allowed
    provider = MockFlightProvider(settings=test_settings)
    flights = [
        Flight(
            id="f1", origin="DEL", destination="BKK", departure_date=datetime.utcnow(),
            price=Decimal("150"), airline="AI", stops=0, duration_minutes=100
        ),
        Flight(
            id="f2", origin="DEL", destination="LHR", departure_date=datetime.utcnow(),
            price=Decimal("200"), airline="AI", stops=0, duration_minutes=100
        )
    ]
    filtered = provider._filter_and_sort_flights(flights)
    destinations = [f.destination for f in filtered]
    assert "BKK" in destinations
    assert "LHR" not in destinations

    # Without allowed list: all international allowed
    empty_settings = Settings(
        ALLOWED_DESTINATION_COUNTRIES=[],
        FALLBACK_EXCHANGE_RATES=test_settings.FALLBACK_EXCHANGE_RATES
    )
    provider_empty = MockFlightProvider(settings=empty_settings)
    filtered_all = provider_empty._filter_and_sort_flights(flights)
    destinations_all = [f.destination for f in filtered_all]
    assert "BKK" in destinations_all
    assert "LHR" in destinations_all


def test_cheapest_first_sorting(test_settings):
    provider = MockFlightProvider(settings=test_settings)
    flights = [
        Flight(
            id="f1", origin="DEL", destination="BKK", departure_date=datetime.utcnow(),
            price=Decimal("15000"), airline="AI", stops=0, duration_minutes=100
        ),
        Flight(
            id="f2", origin="DEL", destination="SIN", departure_date=datetime.utcnow(),
            price=Decimal("10000"), airline="AI", stops=0, duration_minutes=100
        ),
        Flight(
            id="f3", origin="DEL", destination="KUL", departure_date=datetime.utcnow(),
            price=Decimal("8000"), airline="AI", stops=0, duration_minutes=100
        )
    ]
    filtered = provider._filter_and_sort_flights(flights)
    prices = [f.price for f in filtered]
    # Prices should be: 8000, 10000, 15000
    assert prices == [Decimal("8000"), Decimal("10000"), Decimal("15000")]


def test_notification_formatting():
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
    
    # Assert elements of premium redesign are present
    assert "SUPER DEAL" in msg.body_html
    assert "🇹🇭 <b>Thailand</b>" in msg.body_html
    assert "Delhi (DEL)" in msg.body_html
    assert "Bangkok (BKK)" in msg.body_html
    assert "₹8,950" in msg.body_html
    assert "₹15,700" in msg.body_html
    assert "₹6,750 (43.0%)" in msg.body_html
    assert "15 Aug 2026" in msg.body_html
    assert "Thai AirAsia" in msg.body_html
    assert "92 / 100" in msg.body_html
