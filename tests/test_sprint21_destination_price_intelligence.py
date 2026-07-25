import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock

from src.domain.destination_price_intelligence import DestinationPriceIntelligence
from src.domain.entities import Flight, PriceHistory, DealResult, User
from src.domain.deal_engine import DealEngine
from src.domain.deal_scoring_services import DealScoringService
from src.use_cases.notification_pipeline import NotificationPipeline

def test_price_intelligence_bands_and_scores():
    pi = DestinationPriceIntelligence()
    
    # 1. Japan excellent fare (<= 22000)
    assert pi.get_price_band("Japan", 22000) == "excellent"
    assert pi.calculate_absolute_fare_score("Japan", 22000) == 100.0
    
    # 2. Malaysia excellent fare (<= 8500)
    assert pi.get_price_band("Malaysia", 8500) == "excellent"
    assert pi.calculate_absolute_fare_score("Malaysia", 8500) == 100.0
    
    # 3. Thailand excellent fare (<= 8000)
    assert pi.get_price_band("Thailand", 8000) == "excellent"
    assert pi.calculate_absolute_fare_score("Thailand", 8000) == 100.0
    
    # 4. Singapore excellent fare (<= 9000)
    assert pi.get_price_band("Singapore", 9000) == "excellent"
    assert pi.calculate_absolute_fare_score("Singapore", 9000) == 100.0
    
    # 5. Vietnam excellent fare (<= 9000)
    assert pi.get_price_band("Vietnam", 9000) == "excellent"
    assert pi.calculate_absolute_fare_score("Vietnam", 9000) == 100.0
    
    # 6. High-priced flights (very expensive)
    assert pi.get_price_band("Japan", 45000) == "very expensive"
    assert pi.calculate_absolute_fare_score("Japan", 45000) == 0.0
    
    # 7. Boundary values (Japan)
    # excellent: <= 22000
    assert pi.get_price_band("Japan", 22000) == "excellent"
    assert pi.get_price_band("Japan", 22001) == "great"
    
    # great: <= 25000
    assert pi.get_price_band("Japan", 25000) == "great"
    assert pi.get_price_band("Japan", 25001) == "good"
    
    # good: <= 28000
    assert pi.get_price_band("Japan", 28000) == "good"
    assert pi.get_price_band("Japan", 28001) == "average"
    
    # average: <= 32000
    assert pi.get_price_band("Japan", 32000) == "average"
    assert pi.get_price_band("Japan", 32001) == "expensive"
    
    # expensive: <= average * 1.25 (32000 * 1.25 = 40000)
    assert pi.get_price_band("Japan", 40000) == "expensive"
    assert pi.get_price_band("Japan", 40001) == "very expensive"

def test_final_score_calculation():
    # Verify that DealScoringService uses all 6 weights correctly
    service = DealScoringService(
        weight_historical=0.15,
        weight_market=0.15,
        weight_percentile=0.15,
        weight_seasonality=0.10,
        weight_budget=0.10,
        weight_absolute=0.35
    )
    
    final_score = service.calculate_final_score(
        historical_score=100.0,
        market_score=80.0,
        percentile_score=90.0,
        seasonality_score=70.0,
        budget_score=60.0,
        absolute_score=100.0
    )
    
    # Hand calculation:
    # 100 * 0.35 (absolute) = 35.0
    # 100 * 0.15 (historical) = 15.0
    # 80 * 0.15 (market) = 12.0
    # 90 * 0.15 (percentile) = 13.5
    # 70 * 0.10 (seasonality) = 7.0
    # 60 * 0.10 (budget) = 6.0
    # Total = 35 + 15 + 12 + 13.5 + 7 + 6 = 88.5
    assert final_score == 88.5

def test_notification_explanations():
    pi = DestinationPriceIntelligence()
    
    explanations_jp_exc = pi.explain_price_quality("Japan", 21000)
    assert "Excellent fare for Japan" in explanations_jp_exc
    assert "Below typical Japan pricing" in explanations_jp_exc
    
    explanations_my_great = pi.explain_price_quality("Malaysia", 9500)
    assert "Great Malaysia fare" in explanations_my_great
    assert "Below typical Malaysia pricing" in explanations_my_great

@pytest.mark.anyio
async def test_daily_scanner_produces_good_deals_for_objectively_cheap_fares():
    # Verify that a Japan flight for ₹23,500 is categorized as GOOD even if historical avg is close (₹23,400)
    # Under old engine, this would be NORMAL (0% discount below historical average).
    # Under new engine, Absolute Score is 90 (GREAT band).
    # Let's run it through DealEngine.
    
    repo = MagicMock()
    # Mock history record showing average close to current price
    hist = PriceHistory(
        origin="DEL", destination="NRT",
        current_price=Decimal("23500"), lowest_price=Decimal("22000"), highest_price=Decimal("30000"),
        rolling_average=Decimal("23400"), first_seen=datetime.now(timezone.utc), last_seen=datetime.now(timezone.utc)
    )
    repo.get.return_value = hist
    
    f1 = Flight(
        id="mock_jp_deal", origin="DEL", destination="NRT",
        departure_date=datetime.now(timezone.utc) + timedelta(days=30),
        price=Decimal("23500"), airline="Japan Airlines", stops=0, duration_minutes=480
    )
    
    settings_mock = MagicMock()
    # Configuration with Sprint 21 default weights
    settings_mock.SCORING_WEIGHT_ABSOLUTE = 0.35
    settings_mock.SCORING_WEIGHT_HISTORICAL = 0.15
    settings_mock.SCORING_WEIGHT_MARKET = 0.15
    settings_mock.SCORING_WEIGHT_PERCENTILE = 0.15
    settings_mock.SCORING_WEIGHT_BUDGET = 0.10
    settings_mock.SCORING_WEIGHT_SEASONALITY = 0.10
    
    settings_mock.DEAL_THRESHOLD_SUPER = 90.0
    settings_mock.DEAL_THRESHOLD_GREAT = 75.0
    settings_mock.DEAL_THRESHOLD_GOOD = 60.0
    
    settings_mock.BOOK_NOW_THRESHOLD = 80.0
    settings_mock.WAIT_THRESHOLD = 45.0
    settings_mock.HIGH_VOLATILITY_LIMIT = 0.15
    settings_mock.CONFIDENCE_WEIGHT_HISTORY = 0.50
    settings_mock.CONFIDENCE_WEIGHT_TREND = 0.25
    settings_mock.CONFIDENCE_WEIGHT_VOLATILITY = 0.25
    
    settings_mock.COUNTRY_MAX_BUDGETS = {"japan": 25000}
    
    engine = DealEngine(
        price_history_repo=repo,
        settings=settings_mock
    )
    
    results = engine.process_flights([f1])
    assert len(results) == 1
    
    deal = results[0]
    # Check that it evaluates as GOOD or GREAT deal
    assert deal.deal_category in ["GOOD", "GREAT", "SUPER"]
    
    # Verify that explanations contains absolute price intelligence
    assert "Great Japan fare" in deal.explanation or "Excellent fare for Japan" in deal.explanation
