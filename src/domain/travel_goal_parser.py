import calendar
import re
from datetime import datetime, timezone
from decimal import Decimal

from src.domain.entities import TravelGoalDraft


# Keep for reference and fallback parsing in ConversationService
COUNTRY_MAP = {
    r"\bthailand\b": "Thailand",
    r"\bvietnam\b": "Vietnam",
    r"\bsingapore\b": "Singapore",
    r"\bmalaysia\b": "Malaysia",
    r"\bindonesia\b": "Indonesia",
    r"\bjapan\b": "Japan",
    r"\bsouth\s+korea\b": "South Korea",
    r"\bkorea\b": "South Korea",
    r"\bunited\s+arab\s+emirates\b": "United Arab Emirates",
    r"\buae\b": "United Arab Emirates",
    r"\bdubai\b": "United Arab Emirates",
    r"\bgermany\b": "Germany",
    r"\bfrance\b": "France",
    r"\bitaly\b": "Italy",
}

MONTH_MAP = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}


class TravelGoalParser:
    """
    Parser service to validate structured travel goal data.
    """
    def parse(self, draft: TravelGoalDraft, now: datetime | None = None) -> TravelGoalDraft:
        """
        Validates already-extracted structured TravelGoalDraft.
        """
        if not draft:
            raise ValueError("Input query cannot be empty.")

        # 1. Validate Country
        if not draft.country:
            raise ValueError("Could not extract a supported destination country from the request.")

        # 2. Validate Date Window
        if not draft.start_date or not draft.end_date:
            raise ValueError("Could not extract a valid travel date window or season from the request.")

        # 3. Validate Budget
        if draft.budget_inr is not None and draft.budget_inr < 0:
            raise ValueError("Budget cannot be negative.")

        return draft
