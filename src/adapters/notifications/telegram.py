import time
import html
import httpx
from loguru import logger

from src.domain.entities import Notification
from src.domain.interfaces import NotificationSender
from src.adapters.providers.constants import AIRPORT_TO_COUNTRY
from src.utils import mask_chat_id, mask_secret


def parse_message_body(message_body: str) -> tuple[str, list[str], str, str]:
    """
    Parses raw message body into header, individual deal cards, footer, and separator.
    """
    if "\n\n====================\n\n" in message_body:
        parts = message_body.split("\n\n====================\n\n")
        separator = "\n\n====================\n\n"
    elif "\n====================\n" in message_body:
        parts = message_body.split("\n====================\n")
        separator = "\n====================\n"
    elif "\n\n━━━━━━━━━━━━━━━━\n\n" in message_body:
        parts = message_body.split("\n\n━━━━━━━━━━━━━━━━\n\n")
        separator = "\n\n━━━━━━━━━━━━━━━━\n\n"
    elif "\n━━━━━━━━━━━━━━━━\n" in message_body:
        parts = message_body.split("\n━━━━━━━━━━━━━━━━\n")
        separator = "\n━━━━━━━━━━━━━━━━\n"
    else:
        if "━━━━━━━━━━━━━━━━" in message_body:
            parts = message_body.split("━━━━━━━━━━━━━━━━")
            separator = "━━━━━━━━━━━━━━━━"
        else:
            return "", [message_body], "", ""

    parts = [p.strip() for p in parts if p.strip()]
    if not parts:
        return "", [], "", separator

    header = ""
    footer = ""
    cards = []

    first_part = parts[0]
    is_header = (
        "Today's Best" in first_part
        or "Started" in first_part
        or "Goal Matched" in first_part
        or "Baseline" in first_part
    )
    if is_header:
        header = first_part
        cards = parts[1:]
    else:
        cards = parts

    if cards:
        last_part = cards[-1]
        is_footer = (
            "Open App" in last_part
            or "booking link" not in last_part
        )
        if is_footer and "Open App for More Details" in last_part:
            footer = last_part
            cards = cards[:-1]

    return header, cards, footer, separator


def chunk_message(message_header: str, message_body: str, limit: int = 3800) -> list[str]:
    """
    Splits message_body into chunks, ensuring no deal cards are split, and headers/footers are preserved.
    """
    header, cards, footer, separator = parse_message_body(message_body)
    
    if not cards:
        full_msg = f"<b>{message_header}</b>\n\n{message_body}"
        return [full_msg]

    def render_chunk_html(chunk_idx: int, num_chunks: int, chunk_cards: list[str]) -> str:
        if num_chunks == 1:
            if "Today's Best Flight Deals" in header or "Today's Best Deals" in header:
                rendered_header = f"🔥 <b>Today's Best Deals</b>\n{len(cards)} deals found\nShowing all results"
            else:
                rendered_header = header
        else:
            if "Today's Best Flight Deals" in header or "Today's Best Deals" in header:
                if chunk_idx == 1:
                    rendered_header = f"🔥 <b>Today's Best Deals</b>\n{len(cards)} deals found\nShowing all results\n(Message 1 of {num_chunks})"
                else:
                    rendered_header = f"🔥 <b>Today's Best Deals</b>\n(Message {chunk_idx} of {num_chunks})"
            else:
                if "<b>" in header and "</b>" in header:
                    idx_end = header.find("</b>")
                    title = header[:idx_end]
                    rest = header[idx_end:]
                    rendered_header = f"{title} (Message {chunk_idx} of {num_chunks}){rest}"
                else:
                    rendered_header = f"{header} (Message {chunk_idx} of {num_chunks})" if header else f"(Message {chunk_idx} of {num_chunks})"
                    
        body_str = separator.join(chunk_cards)
        main_header = f"<b>{message_header}</b>"
        
        parts = [main_header]
        if rendered_header:
            parts.append(rendered_header)
        parts.append(body_str)
        
        if chunk_idx == num_chunks and footer:
            parts.append(footer)
            
        return "\n\n".join(parts)

    # Greedy packing
    chunks = []
    current_chunk = []
    
    for card in cards:
        test_chunk = current_chunk + [card]
        rendered_len = len(render_chunk_html(len(chunks) + 1, 99, test_chunk))
        if rendered_len > limit and current_chunk:
            chunks.append(current_chunk)
            current_chunk = [card]
        else:
            current_chunk.append(card)
    if current_chunk:
        chunks.append(current_chunk)
        
    # Render final chunks
    rendered_messages = []
    for i, chunk_cards in enumerate(chunks):
        rendered_messages.append(render_chunk_html(i + 1, len(chunks), chunk_cards))
        
    return rendered_messages


class TelegramNotificationSender(NotificationSender):
    """
    Sends rich HTML messages to Telegram users using the Telegram Bot HTTP API.
    Features automatic message chunking, invalid chat protection, and transient-only retries.
    """
    def __init__(self, bot_token: str | None, default_chat_id: str | None):
        self.bot_token = bot_token
        self.default_chat_id = default_chat_id
        self.api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage" if bot_token else None

    def send(self, notification: Notification, message_header: str, message_body: str) -> bool:
        chat_id = notification.user_id or self.default_chat_id
        if not chat_id:
            logger.error("No Telegram Chat ID found for dispatching notification.")
            return False

        # 1. Invalid Chat Detection
        chat_id_str = str(chat_id).lower()
        is_invalid = (
            chat_id_str.startswith("trace_user")
            or "test_user" in chat_id_str
            or "dummy_user" in chat_id_str
            or "mock_user" in chat_id_str
        )
        if is_invalid:
            logger.info(
                f"Skipping invalid chat ID ({mask_chat_id(chat_id)})\n"
                f"Reason:\n"
                f"Non-Telegram test user"
            )
            return False

        # 2. Chunking & Size Calculation
        original_formatted = f"<b>{message_header}</b>\n\n{message_body}"
        original_length = len(original_formatted)
        
        if original_length <= 3800:
            rendered_chunks = [original_formatted]
        else:
            rendered_chunks = chunk_message(message_header, message_body, limit=3800)
            
        # Logging Chunk statistics
        logger.info(
            f"\nMessage Length\n"
            f"{original_length} chars\n\n"
            f"Chunks\n"
            f"{len(rendered_chunks)}"
            + "".join(f"\n\nChunk {i+1}\n{len(c)} chars" for i, c in enumerate(rendered_chunks))
        )

        if not self.bot_token or not self.api_url:
            logger.warning(
                f"Telegram credentials not set. Simulated send to {mask_chat_id(chat_id)}: "
                f"Sent {len(rendered_chunks)} chunks."
            )
            return True

        # Send chunks
        max_retries = 3
        backoff_factor = 2.0
        all_success = True
        
        with httpx.Client(timeout=10.0) as client:
            for chunk_idx, chunk_text in enumerate(rendered_chunks):
                payload = {
                    "chat_id": chat_id,
                    "text": chunk_text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": False
                }
                
                chunk_sent = False
                for attempt in range(1, max_retries + 1):
                    try:
                        response = client.post(self.api_url, json=payload)
                        logger.info(f"Telegram API response: status={response.status_code}")
                        
                        if response.status_code == 200:
                            logger.info(f"Telegram notification chunk {chunk_idx+1}/{len(rendered_chunks)} sent successfully to user {mask_chat_id(chat_id)} (Attempt {attempt}).")
                            chunk_sent = True
                            break
                        
                        # Parse description to identify non-transient errors
                        resp_json = {}
                        try:
                            resp_json = response.json()
                        except Exception:
                            pass
                        
                        description = resp_json.get("description", "").lower()
                        is_non_transient = (
                            response.status_code in [400, 401, 403, 404]
                            or "chat not found" in description
                            or "message too long" in description
                            or "invalid chat" in description
                            or "forbidden" in description
                            or "blocked" in description
                            or "unauthorized" in description
                        )
                        
                        if is_non_transient:
                            logger.error(
                                f"Non-transient Telegram API error: status={response.status_code}. "
                                f"Aborting retries immediately."
                            )
                            all_success = False
                            break
                        
                        if response.status_code == 429:
                            retry_after = int(response.headers.get("Retry-After", 5))
                            logger.warning(f"Telegram API Rate Limited. Retrying after {retry_after} seconds...")
                            time.sleep(retry_after)
                            continue
                            
                        logger.error(
                            f"Telegram API returned status {response.status_code} (Attempt {attempt})."
                        )
                        
                    except httpx.RequestError as exc:
                        logger.warning(f"Connection failure on Telegram notification send: {exc} (Attempt {attempt}).")
                    
                    if attempt < max_retries:
                        sleep_time = backoff_factor ** attempt
                        time.sleep(sleep_time)
                
                if not chunk_sent:
                    all_success = False
                    logger.error(f"Failed to send Telegram notification chunk {chunk_idx+1} to {mask_chat_id(chat_id)} after {max_retries} attempts.")
                    break
                    
        return all_success
