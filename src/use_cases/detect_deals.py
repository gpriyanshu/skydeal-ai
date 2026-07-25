from datetime import datetime, timezone
from decimal import Decimal

from loguru import logger

from src.domain.entities import Deal, Flight, PriceHistory
from src.domain.interfaces import DealRepository, PriceHistoryRepository


class DealEngine:
    """
    Independent deal analysis engine.
    Processes flight scans against historical price records to identify discount tiers.
    """
    def __init__(
        self,
        price_history_repo: PriceHistoryRepository,
        deal_repo: DealRepository,
        ema_alpha: float = 0.20  # Exponential Moving Average weight for new prices
    ):
        self.price_history_repo = price_history_repo
        self.deal_repo = deal_repo
        self.ema_alpha = ema_alpha

    def analyze_flights(self, flights: list[Flight]) -> list[Deal]:
        """
        Analyzes a list of flights for a route, updating price history statistics 
        and returning any detected deals (Good, Great, or Super).
        """
        detected_deals = []
        
        for flight in flights:
            history = self.price_history_repo.get(flight.origin, flight.destination)
            now = datetime.now(timezone.utc)

            if not history:
                # First time seeing flights for this route. Initialize baseline.
                history = PriceHistory(
                    origin=flight.origin,
                    destination=flight.destination,
                    current_price=flight.price,
                    lowest_price=flight.price,
                    highest_price=flight.price,
                    rolling_average=flight.price,
                    first_seen=now,
                    last_seen=now
                )
                self.price_history_repo.save(history)
                logger.info(f"Initialized historical baseline for route {flight.origin}->{flight.destination} at ${flight.price}.")
                continue

            # Calculate price properties
            old_average = history.rolling_average
            old_lowest = history.lowest_price
            
            # Update extremes
            lowest = min(history.lowest_price, flight.price)
            highest = max(history.highest_price, flight.price)
            
            # Exponential Moving Average calculation for rolling average
            alpha = Decimal(str(self.ema_alpha))
            new_rolling = (flight.price * alpha) + (old_average * (Decimal('1.0') - alpha))
            
            # Save updated stats
            history.current_price = flight.price
            history.lowest_price = lowest
            history.highest_price = highest
            history.rolling_average = round(new_rolling, 2)
            history.last_seen = now
            self.price_history_repo.save(history)

            # Analyze deal category against baseline average
            if flight.price >= old_average:
                # Price is higher than or equal to historical average; no deal.
                continue
                
            discount_pct = float(((old_average - flight.price) / old_average) * 100)

            # Deal classification thresholds
            # Good Deal: 10% - 20% discount
            # Great Deal: 20% - 35% discount
            # Super Deal: >= 35% discount OR drops below absolute historical lowest price
            category = "Normal"
            if flight.price < old_lowest or discount_pct >= 35.0:
                category = "Super Deal"
            elif discount_pct >= 20.0:
                category = "Great Deal"
            elif discount_pct >= 10.0:
                category = "Good Deal"

            if category in ["Good Deal", "Great Deal", "Super Deal"]:
                deal_id = f"deal_{flight.origin.lower()}_{flight.destination.lower()}_{int(flight.price)}_{now.strftime('%m%d%H%M')}"
                deal = Deal(
                    id=deal_id,
                    flight=flight,
                    category=category,
                    discount_percentage=round(discount_pct, 2),
                    historical_average=round(old_average, 2),
                    detected_at=now
                )
                self.deal_repo.save(deal)
                detected_deals.append(deal)
                logger.info(f"[{category}] Detected on route {flight.origin}->{flight.destination}: ${flight.price} (Avg: ${round(old_average, 2)})")

        return detected_deals

    def get_recent_deals(self, limit: int = 50) -> list[Deal]:
        """
        Retrieves the most recently stored flight deals.
        """
        return self.deal_repo.get_recent_deals(limit)
