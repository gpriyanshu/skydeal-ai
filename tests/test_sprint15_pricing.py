import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

from src.domain.entities import Flight, PriceHistory, DealResult
from src.domain.price_history_service import PriceHistoryService
from src.domain.price_trend_service import PriceTrendService
from src.domain.booking_advisor import BookingAdvisor
from src.domain.notification_formatter import NotificationFormatter
from src.config import Settings

def test_price_history_no_history():
    repo = MagicMock()
    repo.get_observations.return_value = []
    repo.get.return_value = None

    service = PriceHistoryService(repo)
    stats = service.calculate_stats("DEL", "NRT")
    assert stats is None

def test_price_history_single_observation():
    repo = MagicMock()
    repo.get_observations.return_value = [Decimal("10000")]
    repo.get.return_value = None

    service = PriceHistoryService(repo)
    stats = service.calculate_stats("DEL", "NRT")
    assert stats is not None
    assert stats["lowest_price"] == Decimal("10000")
    assert stats["highest_price"] == Decimal("10000")
    assert stats["average_price"] == Decimal("10000")
    assert stats["median_price"] == Decimal("10000")
    assert stats["standard_deviation"] == Decimal("0")
    assert stats["price_volatility"] == Decimal("0")
    assert stats["number_of_observations"] == 1

def test_price_history_multiple_observations():
    repo = MagicMock()
    # Observations: [10000, 12000, 11000]
    # Mean: 11000
    # Median: 11000
    # Variance: ((10000-11000)^2 + (12000-11000)^2 + (11000-11000)^2) / 2 = 2,000,000 / 2 = 1,000,000
    # Std dev: sqrt(1,000,000) = 1000.0
    # Volatility: 1000.0 / 11000 = 0.0909
    repo.get_observations.return_value = [Decimal("10000"), Decimal("12000"), Decimal("11000")]
    repo.get.return_value = None

    service = PriceHistoryService(repo)
    stats = service.calculate_stats("DEL", "NRT")
    assert stats is not None
    assert stats["lowest_price"] == Decimal("10000")
    assert stats["highest_price"] == Decimal("12000")
    assert stats["average_price"] == Decimal("11000")
    assert stats["median_price"] == Decimal("11000")
    assert stats["standard_deviation"] == Decimal("1000.0")
    assert stats["price_volatility"] == Decimal("0.0909")
    assert stats["number_of_observations"] == 3

def test_price_trend_detection_unknown():
    repo = MagicMock()
    repo.get_observations.return_value = [Decimal("10000")] # fewer than 3 observations
    repo.get.return_value = None

    service = PriceTrendService(repo)
    assert service.detect_trend("DEL", "NRT") == "UNKNOWN"

def test_price_trend_detection_stable():
    repo = MagicMock()
    # Standard stable prices
    repo.get_observations.return_value = [Decimal("10000"), Decimal("10050"), Decimal("10020")]
    repo.get.return_value = None

    service = PriceTrendService(repo)
    assert service.detect_trend("DEL", "NRT") == "STABLE"

def test_price_trend_detection_rising():
    repo = MagicMock()
    # Standard rising prices: [10000, 11000, 12000, 13000, 14000]
    repo.get_observations.return_value = [
        Decimal("10000"), Decimal("11000"), Decimal("12000"), Decimal("13000"), Decimal("14000")
    ]
    repo.get.return_value = None

    service = PriceTrendService(repo)
    assert service.detect_trend("DEL", "NRT") == "RISING"

def test_price_trend_detection_falling():
    repo = MagicMock()
    # Standard falling prices: [14000, 13000, 12000, 11000, 10000]
    repo.get_observations.return_value = [
        Decimal("14000"), Decimal("13000"), Decimal("12000"), Decimal("11000"), Decimal("10000")
    ]
    repo.get.return_value = None

    service = PriceTrendService(repo)
    assert service.detect_trend("DEL", "NRT") == "FALLING"

def test_booking_advisor_not_enough_data():
    settings = Settings(
        BOOK_NOW_THRESHOLD=80.0,
        WAIT_THRESHOLD=45.0,
        HIGH_VOLATILITY_LIMIT=0.15,
        CONFIDENCE_WEIGHT_HISTORY=0.50,
        CONFIDENCE_WEIGHT_TREND=0.25,
        CONFIDENCE_WEIGHT_VOLATILITY=0.25
    )
    advisor = BookingAdvisor(settings)
    stats = {
        "lowest_price": Decimal("10000"),
        "highest_price": Decimal("10000"),
        "average_price": Decimal("10000"),
        "median_price": Decimal("10000"),
        "standard_deviation": Decimal("0"),
        "last_seen_price": Decimal("10000"),
        "first_seen_price": Decimal("10000"),
        "price_volatility": Decimal("0"),
        "number_of_observations": 2
    }
    res = advisor.advise(Decimal("10000"), stats, "UNKNOWN", 70.0, None, [Decimal("10000"), Decimal("10000")])
    assert res["recommendation"] == "NOT ENOUGH DATA"
    assert res["confidence"] == 0

def test_booking_advisor_book_now():
    settings = Settings(
        BOOK_NOW_THRESHOLD=80.0,
        WAIT_THRESHOLD=45.0,
        HIGH_VOLATILITY_LIMIT=0.15
    )
    advisor = BookingAdvisor(settings)
    stats = {
        "lowest_price": Decimal("8000"),
        "highest_price": Decimal("12000"),
        "average_price": Decimal("11000"),
        "median_price": Decimal("11000"),
        "standard_deviation": Decimal("1000"),
        "last_seen_price": Decimal("8000"),
        "first_seen_price": Decimal("12000"),
        "price_volatility": Decimal("0.0909"),
        "number_of_observations": 10
    }
    # Score 85 satisfies BOOK NOW
    res = advisor.advise(Decimal("8000"), stats, "FALLING", 85.0, Decimal("10000"), [Decimal("12000"), Decimal("10000"), Decimal("8000")])
    assert res["recommendation"] == "BOOK NOW"
    assert res["confidence"] > 0
    assert any("below historical average" in bullet for bullet in res["insights"])

def test_booking_advisor_wait():
    settings = Settings(
        BOOK_NOW_THRESHOLD=80.0,
        WAIT_THRESHOLD=45.0,
        HIGH_VOLATILITY_LIMIT=0.15
    )
    advisor = BookingAdvisor(settings)
    stats = {
        "lowest_price": Decimal("8000"),
        "highest_price": Decimal("12000"),
        "average_price": Decimal("10000"),
        "median_price": Decimal("10000"),
        "standard_deviation": Decimal("1000"),
        "last_seen_price": Decimal("9500"),
        "first_seen_price": Decimal("12000"),
        "price_volatility": Decimal("0.1000"),
        "number_of_observations": 10
    }
    # Score 50 (below 80 but above 45) with FALLING trend => WAIT
    res = advisor.advise(Decimal("9500"), stats, "FALLING", 50.0, Decimal("10000"), [Decimal("12000"), Decimal("10000"), Decimal("9500")])
    assert res["recommendation"] == "WAIT"

def test_booking_advisor_good_time_to_book():
    settings = Settings(
        BOOK_NOW_THRESHOLD=80.0,
        WAIT_THRESHOLD=45.0,
        HIGH_VOLATILITY_LIMIT=0.15
    )
    advisor = BookingAdvisor(settings)
    stats = {
        "lowest_price": Decimal("8000"),
        "highest_price": Decimal("12000"),
        "average_price": Decimal("10000"),
        "median_price": Decimal("10000"),
        "standard_deviation": Decimal("1000"),
        "last_seen_price": Decimal("10500"),
        "first_seen_price": Decimal("12000"),
        "price_volatility": Decimal("0.1000"),
        "number_of_observations": 10
    }
    # Score 60 (below 80 but above 45) with RISING trend => GOOD TIME TO BOOK
    res = advisor.advise(Decimal("10500"), stats, "RISING", 60.0, Decimal("12000"), [Decimal("9000"), Decimal("10000"), Decimal("10500")])
    assert res["recommendation"] == "GOOD TIME TO BOOK"

def test_booking_advisor_confidence_calculation():
    settings = Settings(
        CONFIDENCE_WEIGHT_HISTORY=0.50,
        CONFIDENCE_WEIGHT_TREND=0.30,
        CONFIDENCE_WEIGHT_VOLATILITY=0.20
    )
    advisor = BookingAdvisor(settings)
    stats = {
        "lowest_price": Decimal("8000"),
        "highest_price": Decimal("12000"),
        "average_price": Decimal("10000"),
        "median_price": Decimal("10000"),
        "standard_deviation": Decimal("500"),
        "last_seen_price": Decimal("10000"),
        "first_seen_price": Decimal("10000"),
        "price_volatility": Decimal("0.0500"), # 5% volatility
        "number_of_observations": 15 # 15/30 = 50% history score
    }
    # c_history = (15/30) * 100 = 50
    # c_volatility = 100 - (0.05 * 200) = 90
    # c_trend = 100 (since trend is not UNKNOWN)
    # Expected confidence = 50 * 0.5 + 90 * 0.2 + 100 * 0.3 = 25 + 18 + 30 = 73
    res = advisor.advise(Decimal("10000"), stats, "STABLE", 75.0, None, [Decimal("10000")]*15)
    assert res["confidence"] == 73

def test_sprint15_notification_formatting():
    from src.domain.notification_formatter import NotificationFormatter
    from src.domain.entities import Flight, PriceHistory

    flight = Flight(
        id="f_s15", origin="DEL", destination="NRT",
        departure_date=datetime(2026, 9, 14, tzinfo=timezone.utc), # A Monday
        price=Decimal("24900"), airline="Japan Airlines", stops=0, duration_minutes=360
    )

    deal = DealResult(
        flight=flight,
        current_price=Decimal("24900"),
        historical_stats=PriceHistory(
            origin="DEL", destination="NRT", current_price=Decimal("24900"),
            lowest_price=Decimal("24100"), highest_price=Decimal("35000"),
            rolling_average=Decimal("33800"), first_seen=datetime.now(timezone.utc), last_seen=datetime.now(timezone.utc)
        ),
        deal_score=88.0,
        deal_category="GREAT",
        savings=Decimal("8900"),
        percentage_below_average=26.3,
        recommendation="BOOK NOW",
        confidence=94,
        insights=["Lowest fare seen", "31% below average", "Stable pricing", "Excellent budget match"]
    )

    formatter = NotificationFormatter()
    msg = formatter.format_summary([deal])

    # Assert new sections are present
    assert "🤖 Recommendation" in msg.body_text
    assert "✅ BOOK NOW" in msg.body_text
    assert "Confidence\n94%" in msg.body_text
    assert "📈 Price Insights" in msg.body_text
    assert "• Lowest fare seen" in msg.body_text
