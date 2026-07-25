import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

from src.domain.entities import Flight, PriceHistory
from src.domain.deal_scoring_services import (
    SeasonalityService,
    MarketRankingService,
    BudgetScoreService,
    DealScoringService,
)
from src.domain.deal_engine import DealEngine


@pytest.fixture
def fixed_now():
    return datetime(2027, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


def test_seasonality_scoring(fixed_now):
    # Japan Cherry Blossom (Peak: March 15 to April 30) -> Score 100
    peak_date_jp = datetime(2027, 4, 1, tzinfo=timezone.utc)
    score_jp_peak = SeasonalityService.calculate_score("NRT", peak_date_jp)
    assert score_jp_peak == 100.0

    # Japan May (Shoulder) -> Score 70
    shoulder_date_jp = datetime(2027, 5, 10, tzinfo=timezone.utc)
    score_jp_shoulder = SeasonalityService.calculate_score("NRT", shoulder_date_jp)
    assert score_jp_shoulder == 70.0

    # Japan June (Off-peak) -> Score 40
    offpeak_date_jp = datetime(2027, 6, 20, tzinfo=timezone.utc)
    score_jp_offpeak = SeasonalityService.calculate_score("NRT", offpeak_date_jp)
    assert score_jp_offpeak == 40.0

    # Thailand December (Peak) -> Score 100
    peak_date_th = datetime(2027, 12, 25, tzinfo=timezone.utc)
    score_th_peak = SeasonalityService.calculate_score("BKK", peak_date_th)
    assert score_th_peak == 100.0


def test_market_ranking_scoring():
    flight_1 = Flight(id="f1", origin="DEL", destination="BKK", departure_date=datetime.now(), price=Decimal("8900"), airline="AI", stops=0, duration_minutes=240)
    flight_2 = Flight(id="f2", origin="BLR", destination="BKK", departure_date=datetime.now(), price=Decimal("10500"), airline="AI", stops=0, duration_minutes=240)
    flight_3 = Flight(id="f3", origin="HYD", destination="BKK", departure_date=datetime.now(), price=Decimal("9600"), airline="AI", stops=0, duration_minutes=240)
    flight_4 = Flight(id="f4", origin="DEL", destination="BKK", departure_date=datetime.now(), price=Decimal("12000"), airline="AI", stops=0, duration_minutes=240)

    flights = [flight_1, flight_2, flight_3, flight_4]
    country_groups = {"thailand": flights}

    scores = MarketRankingService.calculate_scores(flights, country_groups)

    # CCU/f1 is cheapest (8900) -> should be 100
    assert scores["f1"] == 100.0
    # DEL/f4 is most expensive (12000) -> should be 0
    assert scores["f4"] == 0.0
    # Middle ones sorted: 8900, 9600, 10500, 12000 (4 unique prices)
    # P = 4. f3 (9600) is index 1. score = 100 - (1/3)*100 = 66.67
    assert scores["f3"] == 66.67
    # f2 (10500) is index 2. score = 100 - (2/3)*100 = 33.33
    assert scores["f2"] == 33.33


def test_destination_percentile_scoring():
    service = DealScoringService()
    # 10 flights with prices 10k to 19k (inclusive)
    prices = [Decimal(str(p)) for p in range(10000, 20000, 1000)]
    
    # Cheapest is 10000 (index 0, percentile 0.0) -> cheapest 10% -> 100.0
    assert service.calculate_percentile_score(Decimal("10000"), prices) == 100.0
    # Index 1 (11000, percentile 1/9 = 0.111) -> 10% to 20% -> 90.0
    assert service.calculate_percentile_score(Decimal("11000"), prices) == 90.0
    # Index 2 (12000, percentile 2/9 = 0.222) -> 20% to 30% -> 80.0
    assert service.calculate_percentile_score(Decimal("12000"), prices) == 80.0
    # Index 4 (14000, percentile 4/9 = 0.444) -> 30% to 50% -> 50.0
    assert service.calculate_percentile_score(Decimal("14000"), prices) == 50.0
    # Index 6 (16000, percentile 6/9 = 0.667) -> >50% -> 10.0
    assert service.calculate_percentile_score(Decimal("16000"), prices) == 10.0


def test_budget_attractiveness_scoring():
    # Budget 35000, price 21000 (40% discount) -> score (40/50)*100 = 80
    score_attr = BudgetScoreService.calculate_score(Decimal("21000"), Decimal("35000"))
    assert score_attr == 80.0

    # Price at or above budget -> 0
    assert BudgetScoreService.calculate_score(Decimal("35000"), Decimal("35000")) == 0.0
    assert BudgetScoreService.calculate_score(Decimal("36000"), Decimal("35000")) == 0.0

    # Missing budget -> 50 (neutral)
    assert BudgetScoreService.calculate_score(Decimal("21000"), None) == 50.0


def test_final_weighted_score_and_classification():
    service = DealScoringService(
        weight_historical=0.40,
        weight_market=0.20,
        weight_percentile=0.15,
        weight_seasonality=0.10,
        weight_budget=0.15,
        threshold_super=90.0,
        threshold_great=75.0,
        threshold_good=60.0
    )

    final_score = service.calculate_final_score(
        historical_score=100.0,
        market_score=100.0,
        percentile_score=100.0,
        seasonality_score=100.0,
        budget_score=100.0
    )
    assert final_score == 100.0
    assert service.classify_category(final_score) == "SUPER"

    final_score_normal = service.calculate_final_score(
        historical_score=20.0,
        market_score=50.0,
        percentile_score=50.0,
        seasonality_score=40.0,
        budget_score=30.0
    )
    # 20*0.4 + 50*0.2 + 50*0.15 + 40*0.1 + 30*0.15 = 8 + 10 + 7.5 + 4 + 4.5 = 34.0
    assert final_score_normal == 34.0
    assert service.classify_category(final_score_normal) == "NORMAL"


def test_configurable_thresholds_and_weights():
    # Test custom weights
    service = DealScoringService(
        weight_historical=0.50,
        weight_market=0.50,
        weight_percentile=0.0,
        weight_seasonality=0.0,
        weight_budget=0.0,
        threshold_super=95.0,
        threshold_great=85.0,
        threshold_good=70.0
    )
    score = service.calculate_final_score(100.0, 80.0, 0.0, 0.0, 0.0)
    assert score == 90.0  # 100*0.5 + 80*0.5
    assert service.classify_category(score) == "GREAT"  # 90 >= 85 (GREAT) but < 95 (SUPER)


def test_scoring_engine_full_flow(fixed_now):
    repo = MagicMock()
    repo.get = MagicMock(return_value=None)
    repo.save = MagicMock()

    engine = DealEngine(
        price_history_repo=repo,
        scoring_weights={
            "historical": 0.40,
            "market": 0.20,
            "percentile": 0.15,
            "seasonality": 0.10,
            "budget": 0.15
        },
        scoring_thresholds={
            "super": 90.0,
            "great": 75.0,
            "good": 60.0
        }
    )

    flight = Flight(
        id="flight_jp", origin="DEL", destination="NRT",
        departure_date=datetime(2027, 4, 15, tzinfo=timezone.utc),  # Cherry blossom peak
        price=Decimal("20000"), airline="ANA", stops=0, duration_minutes=500
    )

    # First run: baseline price history initialization
    results = engine.process_flights([flight])
    assert len(results) == 1
    deal = results[0]
    # Check that it calculates final score and categorizes even for baseline!
    assert deal.deal_score > 0.0
    assert deal.score_breakdown["Historical"] == 0.0  # No history yet
    assert deal.score_breakdown["Seasonality"] == 100.0  # Peak Season
    assert deal.score_breakdown["Market"] == 100.0  # Only flight in group
    assert deal.score_breakdown["Percentile"] == 100.0  # Only flight in group
    assert "Peak season pricing" in deal.explanation


def test_legacy_compatibility(fixed_now):
    repo = MagicMock()
    engine = DealEngine(price_history_repo=repo)
    # Check that legacy methods are fully present and functional
    assert engine.calculate_deal_score(Decimal("80"), Decimal("100")) == 20.0
    assert engine.classify_deal_category(Decimal("90"), Decimal("100"), Decimal("85")) == "GOOD"
    assert engine.classify_deal_category(Decimal("60"), Decimal("100"), Decimal("90")) == "SUPER"


def test_performance_large_dataset():
    repo = MagicMock()
    repo.get = MagicMock(return_value=None)
    repo.save = MagicMock()
    engine = DealEngine(price_history_repo=repo)
    
    # Generate 500 flights across 5 different destination countries
    destinations = ["BKK", "SIN", "NRT", "DXB", "KUL"]
    large_flights = []
    for i in range(500):
        large_flights.append(
            Flight(
                id=f"flight_{i}",
                origin="DEL",
                destination=destinations[i % len(destinations)],
                departure_date=datetime.now(timezone.utc) + timedelta(days=30),
                price=Decimal(str(10000 + (i * 20))),
                airline="AI",
                stops=0,
                duration_minutes=240
            )
        )
    
    start_time = datetime.now()
    results = engine.process_flights(large_flights)
    duration = (datetime.now() - start_time).total_seconds()
    
    assert len(results) == 500
    # Group sorting and scoring 500 flights must complete in less than 0.5 seconds
    assert duration < 0.5


def test_ux_notification_formatting():
    from src.domain.notification_formatter import NotificationFormatter
    from src.domain.entities import DealResult, Flight, PriceHistory

    flight = Flight(
        id="f_test", origin="DEL", destination="BKK",
        departure_date=datetime(2026, 8, 6, tzinfo=timezone.utc),  # A Thursday
        price=Decimal("8900"), airline="AirAsia", stops=0, duration_minutes=285
    )

    deal = DealResult(
        flight=flight,
        current_price=Decimal("8900"),
        historical_stats=PriceHistory(
            origin="DEL", destination="BKK", current_price=Decimal("8900"),
            lowest_price=Decimal("8900"), highest_price=Decimal("15000"),
            rolling_average=Decimal("15000"), first_seen=datetime.now(timezone.utc), last_seen=datetime.now(timezone.utc)
        ),
        deal_score=61.0,
        deal_category="GOOD",
        savings=Decimal("6100"),
        percentage_below_average=40.67,
        explanation="Cheapest flight today; 47% below Thailand budget; Historical average beaten"
    )

    formatter = NotificationFormatter()
    msg = formatter.format_summary([deal])

    # Check date formatting (Thursday)
    assert "06 Aug 2026 (Thursday)" in msg.body_text
    assert "06 Aug 2026 (Thursday)" in msg.body_html

    # Check Airline info
    assert "AirAsia" in msg.body_text
    assert "AirAsia" in msg.body_html

    # Check Duration (4h 45m)
    assert "4h 45m" in msg.body_text
    assert "4h 45m" in msg.body_html

    # Check Stops (Non-stop)
    assert "Non-stop" in msg.body_text
    assert "Non-stop" in msg.body_html

    # Check Deal Score formatting
    assert "61 / 100" in msg.body_text
    assert "61 / 100" in msg.body_html

    # Check double spaced bullets
    assert "✅ Cheapest flight today\n\n✅ 47% below Thailand budget" in msg.body_text

