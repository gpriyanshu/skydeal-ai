import os
from pathlib import Path
from typing import Literal
from src.destination_regions import DEFAULT_ALERT_REGION as REGION_DEFAULTS

from pydantic import Field, field_validator, model_validator, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.exceptions import SettingsError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def __init__(self, *args, **kwargs):
        try:
            super().__init__(*args, **kwargs)
        except ValidationError as e:
            errors_str = str(e)
            if "Invalid scan origin" in errors_str:
                raise SettingsError(
                    "Invalid scan origin format. "
                    "Scan origins must be 3-letter alphabetical IATA airport codes (e.g. DEL, BOM)."
                ) from e
            raise

    @model_validator(mode="before")
    @classmethod
    def parse_scan_origins(cls, data):
        if not isinstance(data, dict):
            return data

        # 1. Retrieve the raw value for SCAN_ORIGINS or SCAN_ORIGIN
        origins_raw = data.get("SCAN_ORIGINS")
        origin_raw = data.get("SCAN_ORIGIN")

        # Check OS environment directly if not in data dictionary
        if origins_raw is None:
            origins_raw = os.getenv("SCAN_ORIGINS")
        if origin_raw is None:
            origin_raw = os.getenv("SCAN_ORIGIN")

        # 2. Determine final origins list before parsing
        origins = []
        if origins_raw:
            if isinstance(origins_raw, str):
                origins = [o.strip() for o in origins_raw.split(",") if o.strip()]
            elif isinstance(origins_raw, list):
                origins = [str(o).strip() for o in origins_raw if str(o).strip()]

        if not origins and origin_raw:
            if isinstance(origin_raw, str):
                origins = [o.strip() for o in origin_raw.split(",") if o.strip()]
            elif isinstance(origin_raw, list):
                origins = [str(o).strip() for o in origin_raw if str(o).strip()]

        if not origins:
            origins = ["DEL"]

        # 3. Validate and normalize elements
        normalized_origins = []
        for org in origins:
            if not org.isalpha() or len(org) != 3:
                raise ValueError(
                    f"Invalid scan origin format: '{org}'. "
                    f"Scan origins must be 3-letter alphabetical IATA airport codes (e.g. DEL, BOM)."
                )
            normalized_origins.append(org.upper())

        # Deduplicate while preserving order
        unique_origins = []
        for org in normalized_origins:
            if org not in unique_origins:
                unique_origins.append(org)

        # Update data dict
        data["SCAN_ORIGINS"] = unique_origins
        
        # Keep backward compatibility
        if not data.get("SCAN_ORIGIN") and unique_origins:
            data["SCAN_ORIGIN"] = unique_origins[0]

        return data

    @field_validator("DEFAULT_ALERT_REGION", mode="before")
    @classmethod
    def parse_default_alert_region(cls, v):
        if isinstance(v, str):
            if not v.strip():
                return []
            return [country.strip() for country in v.split(",") if country.strip()]
        return v

    @field_validator("ALLOWED_DESTINATION_COUNTRIES", mode="before")
    @classmethod
    def parse_allowed_countries(cls, v):
        if isinstance(v, str):
            if not v.strip():
                return []
            return [country.strip() for country in v.split(",") if country.strip()]
        return v

    @field_validator("COUNTRY_MAX_BUDGETS", mode="before")
    @classmethod
    def parse_country_budgets(cls, v):
        if isinstance(v, str):
            if not v.strip():
                return {}
            result = {}
            for item in v.split(","):
                if ":" in item:
                    k, val = item.split(":", 1)
                    result[k.strip().lower()] = float(val.strip())
            return result
        return v

    # General
    ENV: Literal["development", "production", "test"] = "development"
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # Database
    DB_PATH: Path = Field(default=Path("data/skydeal.db"))

    # Scanner / Scheduler
    SCAN_INTERVAL_HOURS: int = 1
    FLIGHT_PROVIDER: Literal["mock", "skyscanner", "travelpayouts"] = "mock"
    SCAN_ORIGIN: str = "DEL"
    SCAN_ORIGINS: list[str] | str = Field(default_factory=list)

    # TravelPayouts API Settings
    TRAVELPAYOUTS_API_TOKEN: str | None = None
    TRAVELPAYOUTS_BASE_URL: str = "https://api.travelpayouts.com/graphql/v1/query"
    GRAPHQL_TIMEOUT_SECONDS: int = 15

    # Deal Thresholds (percentage discount below rolling average)
    GOOD_DEAL_THRESHOLD: float = 0.10
    GREAT_DEAL_THRESHOLD: float = 0.20
    SUPER_DEAL_THRESHOLD: float = 0.35
    MIN_NOTIFICATION_CATEGORY: Literal["NORMAL", "GOOD", "GREAT", "SUPER"] = "GOOD"

    # Deal Scoring Engine Config (Sprint 21)
    SCORING_WEIGHT_ABSOLUTE: float = 0.35
    SCORING_WEIGHT_HISTORICAL: float = 0.15
    SCORING_WEIGHT_MARKET: float = 0.15
    SCORING_WEIGHT_PERCENTILE: float = 0.15
    SCORING_WEIGHT_BUDGET: float = 0.10
    SCORING_WEIGHT_SEASONALITY: float = 0.10

    DEAL_THRESHOLD_SUPER: float = 90.0
    DEAL_THRESHOLD_GREAT: float = 75.0
    DEAL_THRESHOLD_GOOD: float = 60.0

    # Price Intelligence Engine Config (Sprint 15)
    BOOK_NOW_THRESHOLD: float = 80.0
    WAIT_THRESHOLD: float = 45.0
    HIGH_VOLATILITY_LIMIT: float = 0.15
    CONFIDENCE_WEIGHT_HISTORY: float = 0.50
    CONFIDENCE_WEIGHT_TREND: float = 0.25
    CONFIDENCE_WEIGHT_VOLATILITY: float = 0.25

    # Conversational AI settings (Sprint 16)
    OPENAI_API_KEY: str | None = None
    LLM_PROVIDER: str = "openai"
    MODEL_NAME: str = "gpt-4o-mini"
    CONVERSATION_TIMEOUT: int = 900  # 15 minutes in seconds
    MAX_CONTEXT_MESSAGES: int = 10
    TEMPERATURE: float = 0.7
    MAX_CONVERSATIONAL_RESULTS: int = 3

    # Telegram Notification Settings
    TELEGRAM_BOT_TOKEN: str | None = None
    TELEGRAM_DEFAULT_CHAT_ID: str | None = None
    TELEGRAM_COOLDOWN_SECONDS: int = 3600  # Default 1 hour cooldown per deal/route

    # Filter & Currency settings
    ALLOWED_DESTINATION_COUNTRIES: list[str] | str = Field(
        default_factory=lambda: [
            "Thailand", "Vietnam", "Singapore", "Malaysia", "Indonesia",
            "Japan", "South Korea", "United Arab Emirates", "Germany", "France", "Italy"
        ]
    )
    DEFAULT_ALERT_REGION: list[str] | str = Field(
        default_factory=lambda: REGION_DEFAULTS
    )
    MAX_DAYS_AHEAD: int = 120
    COUNTRY_MAX_BUDGETS: dict[str, float] | str = Field(
        default_factory=lambda: {
            "thailand": 11000.0,
            "vietnam": 13000.0,
            "malaysia": 12000.0,
            "singapore": 12000.0,
            "indonesia": 12000.0,
            "united arab emirates": 12000.0,
            "japan": 20000.0,
            "south korea": 20000.0,
            "germany": 20000.0,
            "france": 20000.0,
            "italy": 20000.0,
        }
    )
    FALLBACK_EXCHANGE_RATES: dict[str, float] = Field(
        default_factory=lambda: {"USD": 1.0, "INR": 83.5, "RUB": 90.0, "EUR": 0.92}
    )
    TRAVELPAYOUTS_PAGE_SIZE: int = 300
    MAX_DEALS_PER_SCAN: int = 10
    DEFAULT_PERSONAL_ROUTES: list[tuple[str, str]] = Field(
        default_factory=lambda: [
            ("BLR", "DEL"), ("DEL", "BLR"),
            ("BLR", "LKO"), ("LKO", "BLR"),
            ("MAA", "DEL"), ("DEL", "MAA"),
            ("MAA", "LKO"), ("LKO", "MAA")
        ]
    )

    # Email Notification Settings (Secondary)
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM_EMAIL: str | None = None

    @property
    def db_dir(self) -> Path:
        """Returns the directory containing the SQLite database file, creating it if necessary."""
        directory = self.DB_PATH.parent
        os.makedirs(directory, exist_ok=True)
        return directory


# Global settings loader (initialized per-run/container start, injected where needed)
def get_settings() -> Settings:
    return Settings()
