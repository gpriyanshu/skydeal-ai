from datetime import datetime, timedelta

from src.domain.entities import Deal, Flight, Notification, PriceHistory, User


def test_user_repository_save_and_get(user_repo):
    user = User(
        id="user_abc",
        username="john_doe",
        email="john@example.com",
        preferred_countries=["United Kingdom", "Singapore"],
        preferred_airports=["DEL", "BOM"],
        preferred_airlines=["Emirates"],
        budget=800.0,
        max_stops=1,
        max_duration_minutes=600,
        cabin_class="business",
        notification_enabled=True,
    )
    user_repo.save(user)
    
    fetched = user_repo.get_by_id("user_abc")
    assert fetched is not None
    assert fetched.id == "user_abc"
    assert fetched.username == "john_doe"
    assert fetched.email == "john@example.com"
    assert fetched.preferred_countries == ["United Kingdom", "Singapore"]
    assert fetched.preferred_airports == ["DEL", "BOM"]
    assert fetched.preferred_airlines == ["Emirates"]
    assert fetched.budget == 800.0
    assert fetched.max_stops == 1
    assert fetched.max_duration_minutes == 600
    assert fetched.cabin_class == "business"
    assert fetched.notification_enabled is True


def test_user_repository_delete(user_repo):
    user = User(
        id="user_del",
        preferred_countries=[],
        preferred_airports=[],
        preferred_airlines=[],
        budget=None,
        max_stops=None,
        max_duration_minutes=None,
        cabin_class="economy",
        notification_enabled=True,
    )
    user_repo.save(user)
    assert user_repo.get_by_id("user_del") is not None
    
    user_repo.delete("user_del")
    assert user_repo.get_by_id("user_del") is None


def test_price_history_repository(price_history_repo):
    now = datetime.utcnow().replace(microsecond=0)
    history = PriceHistory(
        origin="DEL",
        destination="LHR",
        current_price=550.0,
        lowest_price=450.0,
        highest_price=700.0,
        rolling_average=580.0,
        first_seen=now - timedelta(days=5),
        last_seen=now,
    )
    price_history_repo.save(history)
    
    fetched = price_history_repo.get("DEL", "LHR")
    assert fetched is not None
    assert fetched.current_price == 550.0
    assert fetched.lowest_price == 450.0
    assert fetched.highest_price == 700.0
    assert fetched.rolling_average == 580.0
    assert fetched.first_seen == now - timedelta(days=5)
    assert fetched.last_seen == now


def test_deal_repository(deal_repo):
    now = datetime.utcnow().replace(microsecond=0)
    flight = Flight(
        id="flight_1",
        origin="BOM",
        destination="DXB",
        departure_date=now + timedelta(days=10),
        price=280.0,
        airline="Emirates",
        stops=0,
        duration_minutes=180,
        cabin_class="economy",
    )
    deal = Deal(
        id="deal_1",
        flight=flight,
        category="Great Deal",
        discount_percentage=22.5,
        historical_average=361.0,
        detected_at=now,
    )
    deal_repo.save(deal)
    
    fetched = deal_repo.get_by_id("deal_1")
    assert fetched is not None
    assert fetched.id == "deal_1"
    assert fetched.flight.price == 280.0
    assert fetched.category == "Great Deal"
    assert fetched.discount_percentage == 22.5
    assert fetched.historical_average == 361.0
    assert fetched.detected_at == now


def test_notification_repository_and_cooldown(notification_repo, deal_repo):
    now = datetime.utcnow().replace(microsecond=0)
    flight = Flight(
        id="flight_2",
        origin="BLR",
        destination="SIN",
        departure_date=now + timedelta(days=15),
        price=180.0,
        airline="Singapore Airlines",
        stops=0,
        duration_minutes=270,
        cabin_class="economy",
    )
    deal = Deal(
        id="deal_2",
        flight=flight,
        category="Super Deal",
        discount_percentage=40.0,
        historical_average=300.0,
        detected_at=now,
    )
    deal_repo.save(deal)

    notif = Notification(
        id="notif_tg_deal_2_user_1",
        user_id="user_1",
        deal_id="deal_2",
        provider="telegram",
        status="sent",
        last_attempt=now,
    )
    notification_repo.save(notif)
    
    # 1. Exact Duplicate Verification
    existing = notification_repo.get_sent_for_deal_and_user("deal_2", "user_1")
    assert existing is not None
    assert existing.status == "sent"
    
    # 2. Route Cooldown verification
    # Within cooldown window (last 30 minutes)
    since_active = now - timedelta(minutes=30)
    has_recent = notification_repo.has_recent_notification_for_route("user_1", "BLR", "SIN", since_active)
    assert has_recent is True
    
    # Outside cooldown window (looking since 2 hours ago, but notification sent now, so it should still match)
    # Let's test a negative check: since timestamp is in future
    since_future = now + timedelta(minutes=5)
    has_recent_future = notification_repo.has_recent_notification_for_route("user_1", "BLR", "SIN", since_future)
    assert has_recent_future is False
