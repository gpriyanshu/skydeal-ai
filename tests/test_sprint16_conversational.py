import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

from src.domain.entities import ConversationState, Flight, Deal, PriceHistory
from src.domain.conversation_service import ConversationService, ExtractedPreferences
from src.domain.response_builder import ResponseBuilder
from src.adapters.database.conversation_state_repository import InMemoryConversationStateRepository
from src.adapters.ai.openai_provider import OpenAIProvider
from src.config import Settings

def test_intent_detection():
    # Verify that the OpenAIProvider mock maps text to intents correctly
    provider = OpenAIProvider(api_key=None)
    
    # 1. Create Goal
    from src.domain.intent_classifier import IntentClassifierResult
    res = provider.generate_structured_response([{"role": "user", "content": "I want to visit Japan in September"}], IntentClassifierResult)
    assert res.intent == "CREATE_GOAL"

def test_conversation_timeout():
    repo = InMemoryConversationStateRepository(timeout_seconds=60)
    state = ConversationState(user_id="user_test")
    repo.save(state)
    
    # Not expired
    assert repo.get("user_test") is not None
    
    # Manually expire state
    state.last_updated_at = datetime.now(timezone.utc) - timedelta(seconds=120)
    repo.states["user_test"] = state
    
    # Retrieve should yield None and delete
    assert repo.get("user_test") is None

def test_response_formatting():
    # Verify ResponseBuilder HTML generation
    created_html = ResponseBuilder.build_goal_created("Japan", "2026-09-01 to 2026-09-30", 35000.0)
    assert "Goal Created Successfully!" in created_html
    assert "Japan" in created_html
    assert "35,000" in created_html

    deleted_html = ResponseBuilder.build_goal_deleted("Thailand")
    assert "Goal Deleted" in deleted_html
    assert "Thailand" in deleted_html

    paused_html = ResponseBuilder.build_goal_paused("Vietnam")
    assert "Goal Paused" in paused_html
    assert "Vietnam" in paused_html

    resumed_html = ResponseBuilder.build_goal_resumed("Vietnam")
    assert "Goal Resumed" in resumed_html

def test_explain_recommendation_conversational():
    # Mock services
    repo = InMemoryConversationStateRepository()
    provider = OpenAIProvider(api_key=None)
    goal_service = MagicMock()
    deal_engine = MagicMock()
    
    # Seed a mock deal result that has recommendation, confidence and insights
    mock_deal = MagicMock()
    mock_deal.flight.origin = "DEL"
    mock_deal.flight.destination = "NRT"
    mock_deal.recommendation = "BOOK NOW"
    mock_deal.confidence = 94
    mock_deal.insights = ["Lowest fare seen", "31% below average"]
    deal_engine.get_recent_deals.return_value = [mock_deal]
    
    service = ConversationService(repo, provider, goal_service, deal_engine)
    
    # Classify intent to EXPLAIN_RECOMMENDATION
    provider.generate_structured_response = MagicMock(return_value=MagicMock(intent="EXPLAIN_RECOMMENDATION"))
    
    reply = service.handle_message("user_1", "Why did you say Book Now?")
    assert "Recommendation: <b>BOOK NOW</b>" in reply
    assert "Confidence: <b>94%</b>" in reply
    assert "Lowest fare seen" in reply

def test_multi_turn_goal_creation():
    repo = InMemoryConversationStateRepository()
    provider = OpenAIProvider(api_key=None)
    goal_service = MagicMock()
    deal_engine = MagicMock()
    
    service = ConversationService(repo, provider, goal_service, deal_engine)
    
    # Turn 1: User says "I want to visit Japan"
    # Intent: CREATE_GOAL
    # Extracted Preferences: Country="Japan"
    provider.generate_structured_response = MagicMock()
    provider.generate_structured_response.side_effect = [
        MagicMock(intent="CREATE_GOAL"),  # Intent classification
        ExtractedPreferences(country="Japan")  # Preferences extraction
    ]
    
    reply1 = service.handle_message("user_1", "I want to visit Japan")
    assert "destination country" not in reply1
    assert "travel dates" in reply1 or "budget" in reply1
    
    # Turn 2: User says "September"
    # Preferences: start_date="2026-09-01", end_date="2026-09-30"
    provider.generate_structured_response.side_effect = [
        MagicMock(intent="CREATE_GOAL"),
        ExtractedPreferences(start_date="2026-09-01", end_date="2026-09-30")
    ]
    reply2 = service.handle_message("user_1", "September")
    assert "budget" in reply2
    
    # Turn 3: User says "35000"
    # Preferences: budget_inr=35000.0
    mock_goal = MagicMock()
    mock_goal.country = "Japan"
    mock_goal.start_date = datetime(2026, 9, 1)
    mock_goal.end_date = datetime(2026, 9, 30)
    mock_goal.budget_inr = Decimal("35000")
    goal_service.create_goal.return_value = mock_goal
    
    provider.generate_structured_response.side_effect = [
        MagicMock(intent="CREATE_GOAL"),
        ExtractedPreferences(budget_inr=35000.0)
    ]
    reply3 = service.handle_message("user_1", "35000")
    assert "Goal Created Successfully!" in reply3
    assert "Japan" in reply3
    assert "35,000" in reply3

def test_goal_updates_conversational():
    repo = InMemoryConversationStateRepository()
    provider = OpenAIProvider(api_key=None)
    goal_service = MagicMock()
    deal_engine = MagicMock()
    
    mock_goal = MagicMock()
    mock_goal.country = "Japan"
    mock_goal.budget_inr = Decimal("35000")
    goal_service.list_goals.return_value = [mock_goal]
    
    service = ConversationService(repo, provider, goal_service, deal_engine)
    
    provider.generate_structured_response = MagicMock()
    provider.generate_structured_response.side_effect = [
        MagicMock(intent="UPDATE_GOAL"),  # Intent
        ExtractedPreferences(country="Japan", budget_inr=40000.0, start_date="2026-10-01", end_date="2026-10-31")  # Updates
    ]
    
    reply = service.handle_message("user_1", "Increase budget for Japan to 40000 and make it October")
    assert "Goal Updated!" in reply
    assert "₹40,000" in reply
    goal_service.update_goal.assert_called_once()

@pytest.mark.anyio
async def test_telegram_bot_listener_polling():
    from src.adapters.notifications.telegram_bot_listener import TelegramBotListener
    import httpx
    
    # Mock handlers and senders
    from unittest.mock import AsyncMock
    cmd_handler = MagicMock()
    cmd_handler.handle_command_async = AsyncMock(return_value="Hello back!")
    
    sender = MagicMock()
    
    listener = TelegramBotListener(
        bot_token="test_token",
        command_handler=cmd_handler,
        telegram_sender=sender
    )
    
    # Mock getUpdates response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "result": [
            {
                "update_id": 1000,
                "message": {
                    "chat": {"id": 12345},
                    "text": "Hi"
                }
            }
        ]
    }
    
    async def mock_get(self_client, url, *args, **kwargs):
        listener._running = False # Stop loop after this request
        return mock_response
        
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(httpx.AsyncClient, "get", mock_get)
        await listener.start_polling()
        
    cmd_handler.handle_command_async.assert_called_once_with("12345", "Hi")
    sender.send.assert_called_once()
