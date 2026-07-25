from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import MagicMock
from loguru import logger

from src.domain.entities import Flight, PriceHistory
from src.domain.deal_engine import DealEngine
from src.config import Settings

def run_benchmark():
    logger.info("Starting Deal Scoring Engine Benchmark...")
    
    # 1. Setup simulated dataset of 120 flights
    destinations = ["BKK", "SIN", "NRT", "DXB", "KUL"]
    flights = []
    
    # We will generate flights departing in April (peak season for Japan, shoulder for others)
    base_date = datetime(2027, 4, 15, tzinfo=timezone.utc)
    
    for i in range(100):
        dest = destinations[i % len(destinations)]
        # Price ranges from 8,000 to 28,000 INR
        price = Decimal(str(8000 + (i * 200)))
        flights.append(
            Flight(
                id=f"flight_{i}",
                origin="DEL",
                destination=dest,
                departure_date=base_date + timedelta(days=i),
                price=price,
                airline="AI",
                stops=0,
                duration_minutes=240
            )
        )

    # Mock PriceHistoryRepository
    # Pre-seed history with historical average equal to current price (to simulate new or flat routes)
    repo_old = MagicMock()
    repo_new = MagicMock()
    
    history_db = {}
    for f in flights:
        key = (f.origin, f.destination)
        # Seed rolling average close to current price, mimicking flat history
        history_db[key] = PriceHistory(
            origin=f.origin,
            destination=f.destination,
            current_price=f.price,
            lowest_price=f.price - Decimal("50"),
            highest_price=f.price + Decimal("50"),
            rolling_average=f.price,  # 0% savings historically
            first_seen=base_date - timedelta(days=2),
            last_seen=base_date - timedelta(days=2),
            observation_count=3
        )
    
    repo_old.get = lambda o, d: history_db.get((o, d))
    repo_new.get = lambda o, d: history_db.get((o, d))

    # 2. Run Old (Historical) Engine
    old_engine = DealEngine(price_history_repo=repo_old)  # No settings -> is_legacy_mode = True
    old_results = old_engine.process_flights(flights)
    
    old_counts = {"NORMAL": 0, "GOOD": 0, "GREAT": 0, "SUPER": 0}
    for res in old_results:
        old_counts[res.deal_category] += 1
        
    # 3. Run New (Multi-Factor) Engine
    # Setup settings instance
    settings = Settings()
    new_engine = DealEngine(price_history_repo=repo_new, settings=settings)
    new_results = new_engine.process_flights(flights)
    
    new_counts = {"NORMAL": 0, "GOOD": 0, "GREAT": 0, "SUPER": 0}
    for res in new_results:
        new_counts[res.deal_category] += 1

    print("\n" + "="*50)
    print("Sprints 13: Deal Scoring Engine Benchmark Results")
    print("="*50)
    print(f"Total flights evaluated: {len(flights)}")
    print("-"*50)
    print("Old Engine (Historical Discount Only):")
    print(f"  Candidates: {len(flights)}")
    print(f"  NORMAL: {old_counts['NORMAL']}")
    print(f"  GOOD: {old_counts['GOOD']}")
    print(f"  GREAT: {old_counts['GREAT']}")
    print(f"  SUPER: {old_counts['SUPER']}")
    print("-"*50)
    print("New Engine (Intelligent Multi-Factor Scoring):")
    print(f"  Candidates: {len(flights)}")
    print(f"  NORMAL: {new_counts['NORMAL']}")
    print(f"  GOOD: {new_counts['GOOD']}")
    print(f"  GREAT: {new_counts['GREAT']}")
    print(f"  SUPER: {new_counts['SUPER']}")
    print("="*50 + "\n")

    # Output an example breakdown for transparency check
    best_deal = max(new_results, key=lambda r: r.deal_score)
    print("Example Score Breakdown for Best Deal:")
    print(f"  Route: {best_deal.flight.origin} -> {best_deal.flight.destination}")
    print(f"  Price: {best_deal.current_price} INR")
    print(f"  Category: {best_deal.deal_category}")
    print(f"  Final Score: {best_deal.deal_score}")
    print(f"  Breakdown: {best_deal.score_breakdown}")
    print(f"  Explanation: {best_deal.explanation}")
    print("="*50 + "\n")

if __name__ == "__main__":
    run_benchmark()
