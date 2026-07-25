from typing import Literal
from pydantic import BaseModel, Field
from src.domain.interfaces import AIProvider

class IntentClassifierResult(BaseModel):
    intent: Literal[
        "CREATE_GOAL",
        "UPDATE_GOAL",
        "DELETE_GOAL",
        "PAUSE_GOAL",
        "RESUME_GOAL",
        "SHOW_GOALS",
        "ASK_CHEAPEST_FLIGHTS",
        "MIXED_INTENT",
        "EXPLAIN_RECOMMENDATION",
        "HELP",
        "GREETING",
        "ADD_PERSONAL_ROUTE",
        "REMOVE_PERSONAL_ROUTE",
        "PAUSE_PERSONAL_ROUTE",
        "RESUME_PERSONAL_ROUTE",
        "SHOW_PERSONAL_ROUTES",
        "UNKNOWN"
    ] = Field(description="The classified intent of the user message.")

class IntentClassifier:
    def __init__(self, ai_provider: AIProvider):
        self.ai_provider = ai_provider

    def classify_intent(self, user_message: str) -> str:
        """
        Classifies the user message into one of the supported intents.
        """
        msg_lower = user_message.lower()
        
        # Local overrides for Personal Route Watchlist commands
        cities = {"blr", "del", "lko", "maa", "bangalore", "lucknow", "chennai", "delhi", "bom", "mumbai", "ccu", "kolkata"}
        city_count = sum(1 for c in cities if c in msg_lower)
        
        if "show my routes" in msg_lower or "show routes" in msg_lower or "my routes" in msg_lower:
            return "SHOW_PERSONAL_ROUTES"
            
        if city_count >= 2:
            if (
                msg_lower.startswith("add ")
                or msg_lower.startswith("watch ")
                or msg_lower.startswith("monitor ")
            ):
                return "ADD_PERSONAL_ROUTE"
            if msg_lower.startswith("remove "):
                return "REMOVE_PERSONAL_ROUTE"
            if msg_lower.startswith("pause "):
                return "PAUSE_PERSONAL_ROUTE"
            if msg_lower.startswith("resume "):
                return "RESUME_PERSONAL_ROUTE"

        # Quick local override for common testing intents to ensure robust parsing
        if "and monitor" in msg_lower or "and track" in msg_lower or "search and monitor" in msg_lower:
            return "MIXED_INTENT"
        if msg_lower.startswith("monitor ") or msg_lower.startswith("track ") or "price alert" in msg_lower or "notify me when" in msg_lower:
            if "show" not in msg_lower and "find" not in msg_lower and "search" not in msg_lower:
                return "CREATE_GOAL"

        messages = [
            {
                "role": "system",
                "content": (
                    "You are an intent classifier for a conversational flight travel assistant. "
                    "Analyze the user's input and select the single most appropriate intent.\n\n"
                    "Classification Rules:\n"
                    "- If they ask to search/find flights AND ALSO monitor/track/alert/notify (e.g., 'Find flights to Japan in September under 25000 and monitor them', 'Search and track Malaysia prices'), classify as MIXED_INTENT.\n"
                    "- If they want to create/add a travel goal alert, monitor, track, notify, or alert (e.g. 'Monitor Japan', 'Create a goal for Japan', 'Notify me when Japan goes below 25000', 'Track Malaysia prices', 'Create a price alert', 'Alert me when tickets become cheaper'), but do NOT ask to search/find/show flights immediately, classify as CREATE_GOAL.\n"
                    "- If the user is asking to search flights, check prices immediately, find tickets, show deals, or specifies a destination/month/budget/origin (e.g., 'Cheapest flight to Japan', 'Malaysia in August under 15000', 'Flights to Thailand', 'Cheap tickets to Germany', 'Show flights to Singapore'), classify it as ASK_CHEAPEST_FLIGHTS.\n"
                    "- If the user wants to add/watch/monitor a personal home/work route (e.g. 'Add BLR to DEL', 'Watch Chennai to Delhi', 'Monitor BLR DEL'), classify as ADD_PERSONAL_ROUTE.\n"
                    "- If the user wants to remove/delete a personal route (e.g. 'Remove BLR DEL'), classify as REMOVE_PERSONAL_ROUTE.\n"
                    "- If the user wants to pause a personal route (e.g. 'Pause BLR DEL'), classify as PAUSE_PERSONAL_ROUTE.\n"
                    "- If the user wants to resume a personal route (e.g. 'Resume BLR DEL'), classify as RESUME_PERSONAL_ROUTE.\n"
                    "- If the user wants to list/show their watched personal routes (e.g. 'Show my routes'), classify as SHOW_PERSONAL_ROUTES.\n"
                    "- Otherwise classify standard greeting as GREETING, help requests as HELP, listing goals as SHOW_GOALS."
                )
            },
            {"role": "user", "content": user_message}
        ]
        
        from loguru import logger
        try:
            logger.info("AI provider called (Intent Classification)")
            result = self.ai_provider.generate_structured_response(messages, IntentClassifierResult)
            logger.info(f"Intent detected: {result.intent}")
            return result.intent
        except Exception as e:
            logger.error(f"Intent classification failed: {e}")
            return "UNKNOWN"
