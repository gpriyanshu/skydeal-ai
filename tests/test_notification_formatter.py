from datetime import datetime
from decimal import Decimal

import pytest

from src.domain.entities import DealResult, Flight, PriceHistory
from src.domain.notification_formatter import NotificationFormatter


@pytest.fixture
def formatter() -> NotificationFormatter:
    return NotificationFormatter()


def test_every_deal_category(formatter):
    flight = Flight(
        id="f1",
        origin="DEL",
        destination="DXB",
        departure_date=datetime(2026, 8, 15),
        price=Decimal("90"),
        airline="Air India",
        stops=0,
        duration_minutes=240,
        deep_link="https://example.com/book"
    )

    history = PriceHistory(
        origin="DEL",
        destination="DXB",
        current_price=Decimal("90"),
        lowest_price=Decimal("80"),
        highest_price=Decimal("120"),
        rolling_average=Decimal("100"),
        first_seen=datetime.utcnow(),
        last_seen=datetime.utcnow(),
        observation_count=5
    )

    categories = ["NORMAL", "GOOD", "GREAT", "SUPER"]
    emojis = ["ℹ️", "📉", "🔥", "🚀"]  # noqa: RUF001

    for category, emoji in zip(categories, emojis, strict=True):
        deal = DealResult(
            flight=flight,
            current_price=Decimal("90"),
            historical_stats=history,
            deal_score=10.0,
            deal_category=category,
            savings=Decimal("10"),
            percentage_below_average=10.0
        )

        msg = formatter.format(deal, format_type="detailed")
        assert category in msg.subject
        assert emoji in msg.subject
        assert category in msg.body_text
        assert category in msg.body_html
        assert "Air India" in msg.body_text

        msg_short = formatter.format(deal, format_type="short")
        assert category in msg_short.subject
        assert emoji in msg_short.body_text
        assert emoji in msg_short.body_html


def test_missing_booking_url(formatter):
    flight = Flight(
        id="f1",
        origin="DEL",
        destination="DXB",
        departure_date=datetime(2026, 8, 15),
        price=Decimal("90"),
        airline="Air India",
        stops=0,
        duration_minutes=240,
        deep_link=None
    )

    history = PriceHistory(
        origin="DEL",
        destination="DXB",
        current_price=Decimal("90"),
        lowest_price=Decimal("80"),
        highest_price=Decimal("120"),
        rolling_average=Decimal("100"),
        first_seen=datetime.utcnow(),
        last_seen=datetime.utcnow(),
        observation_count=5
    )

    deal = DealResult(
        flight=flight,
        current_price=Decimal("90"),
        historical_stats=history,
        deal_score=10.0,
        deal_category="GOOD",
        savings=Decimal("10"),
        percentage_below_average=10.0
    )

    msg = formatter.format(deal, format_type="detailed")
    assert "No booking link available." in msg.body_text
    assert "No booking link available." in msg.body_html

    msg_short = formatter.format(deal, format_type="short")
    assert "No booking link available." in msg_short.body_text
    assert "No booking link available." in msg_short.body_html


def test_html_escaping(formatter):
    flight = Flight(
        id="f1",
        origin="<script>DEL</script>",
        destination="DXB",
        departure_date=datetime(2026, 8, 15),
        price=Decimal("90"),
        airline="Air <Malicious> India",
        stops=0,
        duration_minutes=240,
        deep_link="https://example.com/book?param=1&other=2"
    )

    history = PriceHistory(
        origin="DEL",
        destination="DXB",
        current_price=Decimal("90"),
        lowest_price=Decimal("80"),
        highest_price=Decimal("120"),
        rolling_average=Decimal("100"),
        first_seen=datetime.utcnow(),
        last_seen=datetime.utcnow(),
        observation_count=5
    )

    deal = DealResult(
        flight=flight,
        current_price=Decimal("90"),
        historical_stats=history,
        deal_score=10.0,
        deal_category="GOOD",
        savings=Decimal("10"),
        percentage_below_average=10.0
    )

    msg = formatter.format(deal, format_type="detailed")
    # Verify inputs are HTML-escaped in HTML body
    assert "<script>" not in msg.body_html
    assert "&lt;script&gt;" in msg.body_html
    assert "Air <Malicious> India" not in msg.body_html
    assert "Air &lt;Malicious&gt; India" in msg.body_html
    assert "param=1&amp;other=2" in msg.body_html


def test_long_airport_names(formatter):
    flight = Flight(
        id="f1",
        origin="DEL (Indira Gandhi International Airport, New Delhi)",
        destination="DXB (Dubai International Airport, United Arab Emirates)",
        departure_date=datetime(2026, 8, 15),
        price=Decimal("90"),
        airline="Air India",
        stops=0,
        duration_minutes=240,
        deep_link="https://example.com/book"
    )

    history = PriceHistory(
        origin="DEL",
        destination="DXB",
        current_price=Decimal("90"),
        lowest_price=Decimal("80"),
        highest_price=Decimal("120"),
        rolling_average=Decimal("100"),
        first_seen=datetime.utcnow(),
        last_seen=datetime.utcnow(),
        observation_count=5
    )

    deal = DealResult(
        flight=flight,
        current_price=Decimal("90"),
        historical_stats=history,
        deal_score=10.0,
        deal_category="GOOD",
        savings=Decimal("10"),
        percentage_below_average=10.0
    )

    msg = formatter.format(deal, format_type="detailed")
    assert "Indira Gandhi International Airport" in msg.body_text
    assert "Dubai International Airport" in msg.body_html


def test_telegram_html_tag_compatibility(formatter):
    flight = Flight(
        id="f1",
        origin="DEL",
        destination="DXB",
        departure_date=datetime(2026, 8, 15),
        price=Decimal("90"),
        airline="Air India",
        stops=0,
        duration_minutes=240,
        deep_link="https://example.com/book"
    )

    history = PriceHistory(
        origin="DEL",
        destination="DXB",
        current_price=Decimal("90"),
        lowest_price=Decimal("80"),
        highest_price=Decimal("120"),
        rolling_average=Decimal("100"),
        first_seen=datetime.utcnow(),
        last_seen=datetime.utcnow(),
        observation_count=5
    )

    deal = DealResult(
        flight=flight,
        current_price=Decimal("90"),
        historical_stats=history,
        deal_score=10.0,
        deal_category="GOOD",
        savings=Decimal("10"),
        percentage_below_average=10.0
    )

    forbidden_tags = ["h1", "h2", "h3", "h4", "div", "span", "table", "ul", "ol", "li", "p"]

    for fmt in ["short", "detailed"]:
        msg = formatter.format(deal, format_type=fmt)
        for tag in forbidden_tags:
            assert f"<{tag}>" not in msg.body_html
            assert f"<{tag} " not in msg.body_html
            assert f"</{tag}>" not in msg.body_html

