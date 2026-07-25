from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from src.domain.deal_engine import DealEngine
from src.domain.entities import Flight, PriceHistory
from src.domain.price_statistics_service import PriceStatisticsService


@pytest.fixture
def mock_repo() -> MagicMock:
    repo = MagicMock()
    store = {}

    def save_impl(history):
        store[(history.origin, history.destination)] = history

    def get_impl(origin, destination):
        return store.get((origin, destination))

    repo.save = save_impl
    repo.get = get_impl
    return repo


def test_price_statistics_service_calculations():
    # Test EMA
    ema = PriceStatisticsService.calculate_ema(
        Decimal("90.0"), Decimal("100.0"), Decimal("0.2")
    )
    assert ema == Decimal("98.00")

    # Test Delta
    delta = PriceStatisticsService.calculate_delta(Decimal("90.0"), Decimal("100.0"))
    assert delta == Decimal("-10.0")

    # Test Percentage Difference
    pct = PriceStatisticsService.calculate_percentage_difference(
        Decimal("90.0"), Decimal("100.0")
    )
    assert pct == 10.0

    # Test zero Division check
    assert (
        PriceStatisticsService.calculate_percentage_difference(
            Decimal("90.0"), Decimal("0.0")
        )
        == 0.0
    )


def test_new_route_baseline(mock_repo):
    engine = DealEngine(
        mock_repo,
        good_deal_threshold=0.1,
        great_deal_threshold=0.2,
        super_deal_threshold=0.35
    )

    flight = Flight(
        id="tp_del_dxb_20260815_0",
        origin="DEL",
        destination="DXB",
        departure_date=datetime(2026, 8, 15),
        price=Decimal("100"),
        airline="AI",
        stops=0,
        duration_minutes=240
    )

    results = engine.process_flights([flight])
    assert len(results) == 1

    res = results[0]
    assert res.deal_category == "NORMAL"
    assert res.deal_score == 0.0
    assert res.savings == Decimal("0")

    # Verify baseline price history was saved correctly
    history = mock_repo.get("DEL", "DXB")
    assert history is not None
    assert history.current_price == Decimal("100")
    assert history.lowest_price == Decimal("100")
    assert history.highest_price == Decimal("100")
    assert history.rolling_average == Decimal("100")
    assert history.observation_count == 1


def test_existing_route_update_and_deal_classification(mock_repo):
    engine = DealEngine(
        mock_repo,
        good_deal_threshold=0.1,
        great_deal_threshold=0.2,
        super_deal_threshold=0.35,
        ema_alpha=0.2
    )

    # Seed history with lowest price = 80, rolling average = 100
    history = PriceHistory(
        origin="DEL",
        destination="DXB",
        current_price=Decimal("100"),
        lowest_price=Decimal("80"),
        highest_price=Decimal("120"),
        rolling_average=Decimal("100"),
        first_seen=datetime.utcnow() - timedelta(days=2),
        last_seen=datetime.utcnow() - timedelta(days=2),
        observation_count=5
    )
    mock_repo.save(history)

    # 10% discount below baseline (100) -> 90. 90 is not below lowest (80), so GOOD
    flight2 = Flight(
        id="f2",
        origin="DEL",
        destination="DXB",
        departure_date=datetime(2026, 8, 15),
        price=Decimal("90"),
        airline="AI",
        stops=0,
        duration_minutes=240
    )

    results = engine.process_flights([flight2])
    assert len(results) == 1
    res = results[0]

    assert res.deal_category == "GOOD"
    assert res.deal_score == 10.0
    assert res.savings == Decimal("10")
    assert res.percentage_below_average == 10.0

    updated_history = mock_repo.get("DEL", "DXB")
    assert updated_history.rolling_average == Decimal("98.00")
    assert updated_history.observation_count == 6
    assert updated_history.lowest_price == Decimal("80")


def test_price_increase_handling(mock_repo):
    engine = DealEngine(
        mock_repo,
        good_deal_threshold=0.1,
        great_deal_threshold=0.2,
        super_deal_threshold=0.35,
        ema_alpha=0.2
    )

    flight1 = Flight(
        id="f1",
        origin="DEL",
        destination="DXB",
        departure_date=datetime(2026, 8, 15),
        price=Decimal("100"),
        airline="AI",
        stops=0,
        duration_minutes=240
    )
    engine.process_flights([flight1])

    # Price increase to 120 -> should trigger NORMAL category
    flight2 = Flight(
        id="f2",
        origin="DEL",
        destination="DXB",
        departure_date=datetime(2026, 8, 15),
        price=Decimal("120"),
        airline="AI",
        stops=0,
        duration_minutes=240
    )

    results = engine.process_flights([flight2])
    res = results[0]

    assert res.deal_category == "NORMAL"
    assert res.deal_score == 0.0
    assert res.savings == Decimal("0")

    history = mock_repo.get("DEL", "DXB")
    assert history.rolling_average == Decimal("104.00")
    assert history.highest_price == Decimal("120")
    assert history.lowest_price == Decimal("100")


def test_new_lowest_price_triggers_super_deal(mock_repo):
    engine = DealEngine(
        mock_repo,
        good_deal_threshold=0.1,
        great_deal_threshold=0.2,
        super_deal_threshold=0.35,
        ema_alpha=0.2
    )

    flight1 = Flight(
        id="f1",
        origin="DEL",
        destination="DXB",
        departure_date=datetime(2026, 8, 15),
        price=Decimal("100"),
        airline="AI",
        stops=0,
        duration_minutes=240
    )
    engine.process_flights([flight1])

    # Dropping below absolute lowest price (100) -> elevates to SUPER Deal
    flight2 = Flight(
        id="f2",
        origin="DEL",
        destination="DXB",
        departure_date=datetime(2026, 8, 15),
        price=Decimal("95"),
        airline="AI",
        stops=0,
        duration_minutes=240
    )

    results = engine.process_flights([flight2])
    res = results[0]
    assert res.deal_category == "SUPER"


def test_duplicate_flights_deduplicated(mock_repo):
    engine = DealEngine(
        mock_repo,
        good_deal_threshold=0.1,
        great_deal_threshold=0.2,
        super_deal_threshold=0.35
    )

    flight1 = Flight(
        id="f1",
        origin="DEL",
        destination="DXB",
        departure_date=datetime(2026, 8, 15),
        price=Decimal("100"),
        airline="AI",
        stops=0,
        duration_minutes=240
    )
    flight2 = Flight(
        id="f2",
        origin="DEL",
        destination="DXB",
        departure_date=datetime(2026, 8, 15),
        price=Decimal("100"),
        airline="AI",
        stops=0,
        duration_minutes=240
    )

    results = engine.process_flights([flight1, flight2])
    assert len(results) == 1  # Deduplicated

    history = mock_repo.get("DEL", "DXB")
    assert history.observation_count == 1


def test_configuration_threshold_changes(mock_repo):
    engine = DealEngine(
        mock_repo,
        good_deal_threshold=0.05,
        great_deal_threshold=0.15,
        super_deal_threshold=0.25
    )

    # Seed history with lowest price = 70, rolling average = 100
    history = PriceHistory(
        origin="DEL",
        destination="DXB",
        current_price=Decimal("100"),
        lowest_price=Decimal("70"),
        highest_price=Decimal("120"),
        rolling_average=Decimal("100"),
        first_seen=datetime.utcnow() - timedelta(days=2),
        last_seen=datetime.utcnow() - timedelta(days=2),
        observation_count=5
    )
    mock_repo.save(history)

    # 20% discount (80) -> great threshold is 15%, so classified as GREAT
    flight2 = Flight(
        id="f2",
        origin="DEL",
        destination="DXB",
        departure_date=datetime(2026, 8, 15),
        price=Decimal("80"),
        airline="AI",
        stops=0,
        duration_minutes=240
    )

    results = engine.process_flights([flight2])
    assert results[0].deal_category == "GREAT"
