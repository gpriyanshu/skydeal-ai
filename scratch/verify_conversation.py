import sys
from loguru import logger
from src.config import get_settings
from src.infrastructure.di_container import DIContainer
from src.domain.entities import Notification

# Initialize Loguru for stdout formatting
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level:7}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO"
)

settings = get_settings()
container = DIContainer(settings)

# Simulate user: "Hi"
user_id = "12345678"
user_msg = "Hi"

logger.info("Update received: 9999")
logger.info(f"Message text: {user_msg}")

# Dispatch
response_text = container.telegram_command_handler.handle_command(user_id, user_msg)
logger.info(f"Response generated: {response_text}")

notification = Notification(
    id="reply_9999",
    user_id=user_id,
    deal_id="conversational_reply",
    provider="telegram",
    status="pending"
)

logger.info(f"Telegram send invoked for user {user_id}")
container.telegram_sender.send(notification, "SkyDeal AI", response_text)
