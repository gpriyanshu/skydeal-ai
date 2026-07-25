import asyncio
import httpx
from loguru import logger
from src.adapters.telegram_command_handler import TelegramCommandHandler
from src.adapters.notifications.telegram import TelegramNotificationSender
from src.domain.entities import Notification

class TelegramBotListener:
    """
    Background worker that runs a long-polling updates loop to fetch
    incoming user messages from Telegram, dispatches them to the AI 
    conversation service, and replies back.
    """
    def __init__(
        self,
        bot_token: str | None,
        command_handler: TelegramCommandHandler,
        telegram_sender: TelegramNotificationSender
    ):
        self.bot_token = bot_token
        self.command_handler = command_handler
        self.telegram_sender = telegram_sender
        self.offset = 0
        self._running = False

    async def start_polling(self) -> None:
        if not self.bot_token or self.bot_token == "YOUR_TELEGRAM_BOT_TOKEN" or not self.bot_token.strip():
            logger.warning("Telegram Bot Token is not configured. Polling listener will not start.")
            return

        self._running = True
        logger.info("Telegram polling/webhook running: Starting Telegram Bot long-polling updates listener...")

        async with httpx.AsyncClient(timeout=15.0) as client:
            while self._running:
                try:
                    url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
                    params = {"offset": self.offset, "timeout": 10}
                    response = await client.get(url, params=params)

                    if response.status_code != 200:
                        logger.error(f"Telegram getUpdates failed: status={response.status_code}, body={response.text}")
                        await asyncio.sleep(5)
                        continue

                    data = response.json()
                    updates = data.get("result", [])

                    for update in updates:
                        update_id = update["update_id"]
                        self.offset = update_id + 1

                        logger.info(f"Update received: {update_id}")

                        message = update.get("message")
                        if not message:
                            continue

                        chat = message.get("chat")
                        if not chat:
                            continue

                        chat_id = str(chat["id"])
                        text = message.get("text")

                        if not text:
                            continue

                        logger.info(f"Message text: {text}")

                        # Route to Command Handler & Conversation Service
                        try:
                            # 1. Process message
                            response_text = await self.command_handler.handle_command_async(chat_id, text)
                            logger.info(f"Response generated: {response_text}")

                            # 2. Build Notification entity
                            notification = Notification(
                                id=f"reply_{update_id}",
                                user_id=chat_id,
                                deal_id="conversational_reply",
                                provider="telegram",
                                status="pending"
                            )

                            # 3. Send response back
                            from src.utils import mask_chat_id
                            logger.info(f"Telegram send invoked for user {mask_chat_id(chat_id)}")
                            self.telegram_sender.send(notification, "SkyDeal AI", response_text)

                        except Exception as e:
                            from src.utils import mask_chat_id
                            logger.error(f"Error handling conversational reply for user {mask_chat_id(chat_id)}: {e}")
                            try:
                                fallback_notif = Notification(
                                    id=f"fallback_{update_id}",
                                    user_id=chat_id,
                                    deal_id="error_fallback",
                                    provider="telegram",
                                    status="pending"
                                )
                                self.telegram_sender.send(
                                    fallback_notif,
                                    "SkyDeal AI",
                                    "⚠️ Sorry, I encountered an unexpected error while processing your request. Please try again later."
                                )
                            except Exception as ex:
                                logger.critical(f"Failed to send error fallback to Telegram: {ex}")

                except httpx.RequestError as exc:
                    logger.warning(f"Connection issue during Telegram getUpdates: {exc}")
                    await asyncio.sleep(5)
                except Exception as e:
                    logger.error(f"Unexpected error in getUpdates long-polling loop: {e}")
                    await asyncio.sleep(5)

    def stop(self) -> None:
        self._running = False
        logger.info("Telegram Bot listener stopped.")
