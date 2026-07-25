from datetime import datetime, timedelta

from src.domain.entities import Flight
from src.use_cases.detect_deals import DealEngine


def test_deal_engine_initializes_baseline(price_history_repo, deal_repo):
    engine = DealEngine(price_history_repo, deal_repo)
    now = datetime.utcnow()
    flight = Flight(
        id="flight_initial",
        origin="DEL",
        destination="LHR",
        departure_date=now + timedelta(days=30),
        price=600.0,
        airline="Air India",
        stops=0,
        duration_minutes=540,
        cabin_class="economy",
    )
    
    # First scan should establish history but return NO deals
    deals = engine.analyze_flights([flight])
    assert len(deals) == 0
    
    history = price_history_repo.get("DEL", "LHR")
    assert history is not None
    assert history.current_price == 600.0
    assert history.lowest_price == 600.0
    assert history.highest_price == 600.0
    assert history.rolling_average == 600.0


def test_deal_engine_detects_deals(price_history_repo, deal_repo):
    engine = DealEngine(price_history_repo, deal_repo, ema_alpha=0.20)
    now = datetime.utcnow()
    
    # Setup initial history
    history = PriceHistory(
        origin="DEL",
        destination="LHR",
        current_price=600.0,
        lowest_price=430.0,  # Lower than 440 to avoid triggering Super Deal on normal/good/great checks
        highest_price=600.0,
        rolling_average=600.0,
        first_seen=now - timedelta(days=1),
        last_seen=now - timedelta(days=1),
    )
    price_history_repo.save(history)

    # 1. Price is slightly lower (discount < 10% e.g. $570, discount is 5% off 600)
    flight_normal = Flight(
        id="flight_normal",
        origin="DEL",
        destination="LHR",
        departure_date=now + timedelta(days=30),
        price=570.0,
        airline="Air India",
        stops=0,
        duration_minutes=540,
        cabin_class="economy",
    )
    deals = engine.analyze_flights([flight_normal])
    assert len(deals) == 0  # Normal, no deal triggered

    # 2. Price drops to trigger "Good Deal" (10% - 20% off average: e.g. $520 is ~13.3% off 600)
    # Note that the previous analysis updated the rolling average slightly:
    # new_rolling = 570 * 0.2 + 600 * 0.8 = 594.0
    # $520 is (594-520)/594 = 12.4% discount, which is a Good Deal!
    flight_good = Flight(
        id="flight_good",
        origin="DEL",
        destination="LHR",
        departure_date=now + timedelta(days=30),
        price=520.0,
        airline="Air India",
        stops=0,
        duration_minutes=540,
        cabin_class="economy",
    )
    deals = engine.analyze_flights([flight_good])
    assert len(deals) == 1
    assert deals[0].category == "Good Deal"
    assert deals[0].discount_percentage == 12.46

    # 3. Price drops to trigger "Great Deal" (20% - 35% off average)
    # Rolling average updated to: 520 * 0.2 + 594 * 0.8 = 579.20
    # Price $440 is (579.20-440)/579.20 = 24.03% discount, which is a Great Deal!
    flight_great = Flight(
        id="flight_great",
        origin="DEL",
        destination="LHR",
        departure_date=now + timedelta(days=30),
        price=440.0,
        airline="Air India",
        stops=0,
        duration_minutes=540,
        cabin_class="economy",
    )
    deals = engine.analyze_flights([flight_great])
    assert len(deals) == 1
    assert deals[0].category == "Great Deal"

    # 4. Price drops below lowest_price to trigger "Super Deal"
    # Even if discount is small, dropping below lowest_price ($440) triggers Super Deal
    # Price is $400
    flight_super = Flight(
        id="flight_super",
        origin="DEL",
        destination="LHR",
        departure_date=now + timedelta(days=30),
        price=400.0,
        airline="Air India",
        stops=0,
        duration_minutes=540,
        cabin_class="economy",
    )
    deals = engine.analyze_flights([flight_super])
    assert len(deals) == 1
    assert deals[0].category == "Super Deal"
from src.domain.entities import PriceHistory
