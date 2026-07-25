from decimal import Decimal
from typing import Literal
from src.domain.interfaces import PriceHistoryRepository

class PriceTrendService:
    def __init__(self, price_history_repo: PriceHistoryRepository):
        self.price_history_repo = price_history_repo

    def detect_trend(
        self, origin: str, destination: str, current_price: Decimal | None = None
    ) -> Literal["FALLING", "RISING", "STABLE", "UNKNOWN"]:
        """
        Detects price trend (FALLING, RISING, STABLE, UNKNOWN) using linear regression on recent observations.
        """
        try:
            prices = self.price_history_repo.get_observations(origin, destination)
            if not isinstance(prices, list):
                prices = []
        except Exception:
            prices = []

        if not prices:
            history = self.price_history_repo.get(origin, destination)
            if history:
                prices = [history.current_price]
            elif current_price is not None:
                prices = [current_price]
            else:
                return "UNKNOWN"

        # Use the last 5 observations to determine the trend
        recent_prices = [float(p) for p in prices[-5:]]
        N = len(recent_prices)

        if N < 3:
            return "UNKNOWN"

        # Simple linear regression over indices 0 to N-1
        xs = list(range(N))
        ys = recent_prices

        mean_x = sum(xs) / N
        mean_y = sum(ys) / N

        num = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(N))
        den = sum((xs[i] - mean_x) ** 2 for i in range(N))

        if den == 0:
            return "STABLE"

        slope = num / den
        relative_slope = slope / mean_y if mean_y > 0 else 0.0

        # Deterministic trend threshold
        if relative_slope < -0.005:  # falling by more than 0.5% per observation
            return "FALLING"
        elif relative_slope > 0.005:  # rising by more than 0.5% per observation
            return "RISING"
        else:
            return "STABLE"
