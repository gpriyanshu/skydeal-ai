import pytest
from unittest.mock import MagicMock, patch
import httpx
from src.domain.entities import Notification
from src.adapters.notifications.telegram import (
    TelegramNotificationSender,
    chunk_message,
    parse_message_body
)

def test_parse_message_body():
    # Test parsing with daily best deals separator
    body = (
        "🔥 <b>Today's Best Flight Deals</b>\n\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "Card 1: DEL -> BKK\nBooking Link: <a href='http://link1'>Book</a>\n\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "Card 2: DEL -> KUL\nBooking Link: <a href='http://link2'>Book</a>\n\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "🔗 <b>Open App for More Details</b>"
    )
    header, cards, footer, separator = parse_message_body(body)
    assert "Today's Best Flight Deals" in header
    assert len(cards) == 2
    assert "Open App for More Details" in footer
    assert "━━━━━━━━━━━━━━━━" in separator

def test_chunking_various_sizes():
    # 1. Test 1 deal
    header = "Today's Best Flight Deals"
    single_deal_body = (
        "🔥 <b>Today's Best Flight Deals</b>\n\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "Card 1: DEL -> BKK\nBooking Link: <a href='http://link1'>Book</a>\n\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "🔗 <b>Open App for More Details</b>"
    )
    chunks = chunk_message(header, single_deal_body, limit=3800)
    assert len(chunks) == 1
    assert "1 deals found" in chunks[0]
    
    # 2. Test 5 deals (still fits in 1 chunk)
    five_deals_body = (
        "🔥 <b>Today's Best Flight Deals</b>\n\n"
        "━━━━━━━━━━━━━━━━\n\n"
        + "\n\n━━━━━━━━━━━━━━━━\n\n".join(f"Card {i}: DEL -> BKK\nBooking Link: <a href='http://link/{i}'>Book</a>" for i in range(5))
        + "\n\n━━━━━━━━━━━━━━━━\n\n🔗 <b>Open App for More Details</b>"
    )
    chunks = chunk_message(header, five_deals_body, limit=3800)
    assert len(chunks) == 1
    assert "5 deals found" in chunks[0]

    # 3. Test 20 deals
    twenty_deals_body = (
        "🔥 <b>Today's Best Flight Deals</b>\n\n"
        "━━━━━━━━━━━━━━━━\n\n"
        + "\n\n━━━━━━━━━━━━━━━━\n\n".join(f"Card {i}: DEL -> BKK\nBooking Link: <a href='http://link/{i}'>Book</a>" for i in range(20))
        + "\n\n━━━━━━━━━━━━━━━━\n\n🔗 <b>Open App for More Details</b>"
    )
    # Use smaller limit to force chunking on 20 deals
    chunks = chunk_message(header, twenty_deals_body, limit=1000)
    assert len(chunks) > 1
    # Verify no deal card is split across chunk boundaries
    for idx, c in enumerate(chunks):
        assert "Message" in c
        # Ensure HTML links and tags are intact in each chunk
        assert c.count("<a>") == c.count("</a>") or c.count("<a href") == c.count("</a>")
        assert c.count("<b>") == c.count("</b>")

def test_invalid_chat_skipped():
    sender = TelegramNotificationSender("token", "default_chat")
    
    # Skip test_user
    n_test = Notification(id="1", user_id="test_user", deal_id="deal1", provider="telegram")
    assert sender.send(n_test, "Header", "Body") is False
    
    # Skip trace_user_123
    n_trace = Notification(id="2", user_id="trace_user_123", deal_id="deal1", provider="telegram")
    assert sender.send(n_trace, "Header", "Body") is False
    
    # Skip dummy_user
    n_dummy = Notification(id="3", user_id="dummy_user", deal_id="deal1", provider="telegram")
    assert sender.send(n_dummy, "Header", "Body") is False
    
    # Skip mock_user
    n_mock = Notification(id="4", user_id="mock_user_abc", deal_id="deal1", provider="telegram")
    assert sender.send(n_mock, "Header", "Body") is False

@patch("httpx.Client")
def test_retry_policy_transient(mock_client_class):
    # Mock transient failure (500) followed by 200 success
    mock_client = MagicMock()
    mock_client_class.return_value.__enter__.return_value = mock_client
    
    response_500 = MagicMock()
    response_500.status_code = 500
    response_500.text = "Internal Server Error"
    
    response_200 = MagicMock()
    response_200.status_code = 200
    response_200.text = "OK"
    
    mock_client.post.side_effect = [response_500, response_200]
    
    sender = TelegramNotificationSender("valid_token", "valid_chat")
    n = Notification(id="1", user_id="123456", deal_id="deal1", provider="telegram")
    
    with patch("time.sleep") as mock_sleep:  # Prevent actual delays in tests
        res = sender.send(n, "Header", "Body")
        assert res is True
        assert mock_client.post.call_count == 2

@patch("httpx.Client")
def test_retry_policy_non_transient(mock_client_class):
    # Mock non-transient failure (403 Forbidden - e.g. bot blocked)
    mock_client = MagicMock()
    mock_client_class.return_value.__enter__.return_value = mock_client
    
    response_403 = MagicMock()
    response_403.status_code = 403
    response_403.text = '{"ok":false,"error_code":403,"description":"Forbidden: bot was blocked by the user"}'
    
    mock_client.post.return_value = response_403
    
    sender = TelegramNotificationSender("valid_token", "valid_chat")
    n = Notification(id="1", user_id="123456", deal_id="deal1", provider="telegram")
    
    with patch("time.sleep") as mock_sleep:
        res = sender.send(n, "Header", "Body")
        assert res is False
        # Should abort immediately on 403 without retrying
        assert mock_client.post.call_count == 1
