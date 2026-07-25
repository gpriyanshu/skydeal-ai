from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class User(BaseModel):
    id: str  # Typically the Telegram Chat ID
    username: str | None = None
    email: str | None = None
    preferred_countries: list[str] = Field(default_factory=list)
    preferred_airports: list[str] = Field(default_factory=list)
    preferred_airlines: list[str] = Field(default_factory=list)
    budget: Decimal | None = None
    max_stops: int | None = None
    max_duration_minutes: int | None = None
    cabin_class: Literal["economy", "premium_economy", "business", "first"] = "economy"
    notification_enabled: bool = True
    baseline_sent: bool = False


class Flight(BaseModel):
    id: str
    origin: str  # IATA Code
    destination: str  # IATA Code
    departure_date: datetime
    return_date: datetime | None = None
    price: Decimal
    airline: str
    stops: int
    duration_minutes: int
    cabin_class: Literal["economy", "premium_economy", "business", "first"] = "economy"
    deep_link: str | None = None


class FlightScan(BaseModel):
    id: str | None = None
    scan_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    origin: str
    destination: str
    flights: list[Flight] = Field(default_factory=list)


class PriceHistory(BaseModel):
    origin: str
    destination: str
    current_price: Decimal
    lowest_price: Decimal
    highest_price: Decimal
    rolling_average: Decimal
    first_seen: datetime
    last_seen: datetime
    observation_count: int = 1


class Deal(BaseModel):
    id: str
    flight: Flight
    category: Literal["Normal", "Good Deal", "Great Deal", "Super Deal"]
    discount_percentage: float
    historical_average: Decimal
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Notification(BaseModel):
    id: str
    user_id: str
    deal_id: str
    provider: Literal["telegram", "email"]
    status: Literal["pending", "sent", "failed"] = "pending"
    retry_count: int = 0
    last_attempt: datetime | None = None
    error_message: str | None = None


class DealResult(BaseModel):
    flight: Flight
    current_price: Decimal
    historical_stats: PriceHistory
    deal_score: float
    deal_category: Literal["NORMAL", "GOOD", "GREAT", "SUPER"]
    savings: Decimal
    percentage_below_average: float
    score_breakdown: dict[str, float] | None = None
    explanation: str | None = None
    recommendation: Literal["BOOK NOW", "GOOD TIME TO BOOK", "WAIT", "NOT ENOUGH DATA"] | None = None
    confidence: int | None = None
    insights: list[str] | None = None


class TravelGoal(BaseModel):
    id: str
    user_id: str
    country: str
    start_date: datetime
    end_date: datetime
    budget_inr: Decimal
    status: Literal["ACTIVE", "PAUSED"] = "ACTIVE"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TravelGoalDraft(BaseModel):
    country: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    budget_inr: Decimal | None = None
class ConversationState(BaseModel):
    user_id: str
    messages: list[dict[str, str]] = Field(default_factory=list)
    last_updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    extracted_preferences: dict = Field(default_factory=dict)
    
    # Temporarily stored preference slots (Sprint 17.1 / 17.4.1)
    country: str | None = None
    city: str | None = None
    month: str | None = None
    date_range: str | None = None
    budget: float | None = None
    preferred_origin: str | None = None
    travel_type: str | None = None
    pending_action: str | None = None
    pending_slot: str | None = None
    timestamp: datetime | None = None
    destination_codes: list[str] | None = None
    travel_date_window: str | None = None
    origin: str | None = None
    airline: str | None = None
    max_stops: int | None = None
    cabin_class: str | None = None


class PersonalRoute(BaseModel):
    id: str
    user_id: str
    origin_airport: str
    destination_airport: str
    enabled: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
