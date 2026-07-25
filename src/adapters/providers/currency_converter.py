import time
from decimal import Decimal
import httpx
from loguru import logger


class CurrencyConverter:
    """
    Handles fetching, caching (for 12 hours), and converting exchange rates.
    Decoupled from Pydantic and directly consumes fallback dictionaries.
    """
    def __init__(self, fallback_rates: dict[str, float], cache_duration_seconds: int = 43200):
        self.fallback_rates = fallback_rates
        self.cache_duration_seconds = cache_duration_seconds
        self.rates: dict[str, float] = {}
        self.last_fetched: float = 0.0
        self.api_url = "https://open.er-api.com/v6/latest/USD"

    def _fetch_rates(self) -> None:
        now = time.time()
        # Cache for 12 hours
        if now - self.last_fetched < self.cache_duration_seconds and self.rates:
            return

        logger.info("Fetching fresh exchange rates from Open Exchange Rates API...")
        try:
            # Short timeout of 5 seconds to ensure we never block scanning
            response = httpx.get(self.api_url, timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                if data.get("result") == "success" and "rates" in data:
                    self.rates = data["rates"]
                    self.last_fetched = now
                    logger.info("Exchange rates updated successfully.")
                    return
                else:
                    logger.warning(f"Exchange rate API returned unsuccessful response: {data}")
            else:
                logger.warning(f"Exchange rate API returned HTTP status {response.status_code}")
        except Exception as e:
            logger.warning(f"Failed to fetch exchange rates from API: {e}")

        # Fallback to configured rates if first fetch failed or rates are empty
        if not self.rates:
            logger.warning("Using configured fallback exchange rates.")
            self.rates = self.fallback_rates

    def convert_to_inr(self, value: Decimal, from_currency: str) -> Decimal:
        self._fetch_rates()

        curr_upper = from_currency.upper()
        if curr_upper == "INR":
            return value

        # Convert using USD-based rates (USD is base 1.0)
        try:
            if curr_upper in self.rates and "INR" in self.rates:
                from_rate = self.rates[curr_upper]
                inr_rate = self.rates["INR"]
                usd_value = float(value) / from_rate
                inr_value = usd_value * inr_rate
                return Decimal(str(round(inr_value, 2)))
        except Exception as e:
            logger.warning(f"Error converting {curr_upper} to INR: {e}")

        # Fallback rates lookup
        try:
            from_rate = self.fallback_rates.get(curr_upper, 1.0)
            inr_rate = self.fallback_rates.get("INR", 83.5)
            usd_value = float(value) / from_rate
            inr_value = usd_value * inr_rate
            return Decimal(str(round(inr_value, 2)))
        except Exception as e:
            logger.error(f"Fallback exchange rate conversion failed for {curr_upper}: {e}")
            return value
