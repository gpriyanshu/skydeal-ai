from datetime import datetime, timedelta

import pytest

from src.domain.entities import Deal, Flight, Notification, User
from src.domain.interfaces import NotificationSender
from src.use_cases.notify_users import NotifyUsersUseCase


class MockNotificationSender(NotificationSender):
    """Spy notification sender to track invocations."""
    def __init__(self):
        self.sent_notifications = []

    def send(self, notification: Notification, message_header: str, message_body: str) -> bool:
        self.sent_notifications.append((notification, message_header, message_body))
        return True


@pytest.fixture
def tg_sender():
    return MockNotificationSender()


@pytest.fixture
def email_sender():
    return MockNotificationSender()


def test_notification_pipeline_filters_and_sends(
    user_repo, notification_repo, deal_repo, tg_sender, email_sender
):
    now = datetime.utcnow()
    
    # 1. Active User matching DEL -> LHR, budget $500, economy
    user_matching = User(
        id="chat_match",
        username="matching_user",
        email="matching@example.com",
        preferred_countries=["United Kingdom"],
        preferred_airports=["DEL"],
        budget=50000.0,
        cabin_class="economy",
        notification_enabled=True
    )
    # 2. Active User with lower budget ($300) - should NOT get matching notifications
    user_low_budget = User(
        id="chat_low_budget",
        budget=300.0,
        notification_enabled=True
    )
    # 3. Active User but notification is disabled
    user_disabled = User(
        id="chat_disabled",
        budget=1000.0,
        notification_enabled=False
    )
    
    user_repo.save(user_matching)
    user_repo.save(user_low_budget)
    user_repo.save(user_disabled)

    # Setup matching flight & deal
    flight = Flight(
        id="flight_del_lhr",
        origin="DEL",
        destination="LHR",
        departure_date=now + timedelta(days=30),
        price=450.0,  # Below user_matching budget, above user_low_budget budget
        airline="Air India",
        stops=0,
        duration_minutes=540,
        cabin_class="economy",
        deep_link="https://skydeal.ai/book/del_lhr"
    )
    deal = Deal(
        id="deal_match",
        flight=flight,
        category="Great Deal",
        discount_percentage=25.0,
        historical_average=600.0,
        detected_at=now
    )
    deal_repo.save(deal)

    pipeline = NotifyUsersUseCase(
        user_repo=user_repo,
        notification_repo=notification_repo,
        telegram_sender=tg_sender,
        email_sender=email_sender,
        cooldown_seconds=3600
    )

    pipeline.execute([deal])

    # Check Telegram dispatch
    # Only user_matching should get it (1 Telegram message, 1 Email message)
    assert len(tg_sender.sent_notifications) == 1
    assert tg_sender.sent_notifications[0][0].user_id == "chat_match"
    assert "GREAT DEAL DETECTED" in tg_sender.sent_notifications[0][1]

    # Check Email dispatch
    assert len(email_sender.sent_notifications) == 1
    assert email_sender.sent_notifications[0][0].user_id == "matching@example.com"
    assert "SkyDeal AI Alert" in email_sender.sent_notifications[0][1]


def test_notification_pipeline_enforces_cooldown(
    user_repo, notification_repo, deal_repo, tg_sender, email_sender
):
    now = datetime.utcnow()
    user = User(
        id="chat_cooldown",
        budget=1000.0,
        notification_enabled=True
    )
    user_repo.save(user)

    flight = Flight(
        id="flight_cooldown",
        origin="BOM",
        destination="DXB",
        departure_date=now + timedelta(days=30),
        price=200.0,
        airline="Emirates",
        stops=0,
        duration_minutes=180,
        cabin_class="economy",
        deep_link="https://skydeal.ai/book/bom_dxb"
    )
    deal1 = Deal(
        id="deal_cooldown_1",
        flight=flight,
        category="Super Deal",
        discount_percentage=35.0,
        historical_average=308.0,
        detected_at=now
    )
    deal_repo.save(deal1)

    pipeline = NotifyUsersUseCase(
        user_repo=user_repo,
        notification_repo=notification_repo,
        telegram_sender=tg_sender,
        email_sender=email_sender,
        cooldown_seconds=3600
    )

    # First execute: notifies user
    pipeline.execute([deal1])
    assert len(tg_sender.sent_notifications) == 1

    # Clear spy sender records
    tg_sender.sent_notifications.clear()

    # Second execute: should trigger cooldown since route is BOM -> DXB and 3600s cooldown is active
    deal2 = Deal(
        id="deal_cooldown_2",
        flight=flight,
        category="Super Deal",
        discount_percentage=35.0,
        historical_average=308.0,
        detected_at=now
    )
    deal_repo.save(deal2)
    pipeline.execute([deal2])
    assert len(tg_sender.sent_notifications) == 0  # blocked by cooldown
