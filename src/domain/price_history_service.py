import math
from decimal import Decimal
from typing import TypedDict
from src.domain.interfaces import PriceHistoryRepository

class RouteStats(TypedDict):
    lowest_price: Decimal
    highest_price: Decimal
    average_price: Decimal
    median_price: Decimal
    standard_deviation: Decimal
    last_seen_price: Decimal
    first_seen_price: Decimal
    price_volatility: Decimal
    number_of_observations: int

class PriceHistoryService:
    def __init__(self, price_history_repo: PriceHistoryRepository):
        self.price_history_repo = price_history_repo

    def calculate_stats(self, origin: str, destination: str, current_price: Decimal | None = None) -> RouteStats | None:
        """
        Calculates historical statistics for a route using all saved observations.
        """
        try:
            prices = self.price_history_repo.get_observations(origin, destination)
            if not isinstance(prices, list):
                prices = []
        except Exception:
            prices = []
        
        history = self.price_history_repo.get(origin, destination)
        
        if not prices:
            if history:
                prices = [history.current_price]
            elif current_price is not None:
                prices = [current_price]
            else:
                return None
        
        # Ensure we round all incoming prices
        prices_float = [float(p) for p in prices]
        N = len(prices_float)
        
        lowest = Decimal(str(min(prices_float)))
        highest = Decimal(str(max(prices_float)))
        avg = Decimal(str(sum(prices_float) / N))
        
        # Median
        sorted_prices = sorted(prices_float)
        if N % 2 == 1:
            median_val = sorted_prices[N // 2]
        else:
            median_val = (sorted_prices[(N // 2) - 1] + sorted_prices[N // 2]) / 2.0
        median = Decimal(str(median_val))
        
        # Standard deviation (sample standard deviation with N-1 denominator)
        if N > 1:
            mean = float(avg)
            variance = sum((x - mean) ** 2 for x in prices_float) / (N - 1)
            std_dev_val = math.sqrt(variance)
        else:
            std_dev_val = 0.0
        std_dev = Decimal(str(round(std_dev_val, 2)))
        
        # Volatility: Standard Deviation / Average Price
        if avg > Decimal('0'):
            volatility_val = std_dev_val / float(avg)
        else:
            volatility_val = 0.0
        volatility = Decimal(str(round(volatility_val, 4)))
        
        # Last seen / First seen
        last_seen = prices[-1]
        first_seen = prices[0]
        
        # Sync with history summary extremes if available
        if history:
            lowest = min(lowest, history.lowest_price)
            highest = max(highest, history.highest_price)
            
        return {
            "lowest_price": lowest,
            "highest_price": highest,
            "average_price": round(avg, 2),
            "median_price": round(median, 2),
            "standard_deviation": std_dev,
            "last_seen_price": last_seen,
            "first_seen_price": first_seen,
            "price_volatility": volatility,
            "number_of_observations": N
        }
