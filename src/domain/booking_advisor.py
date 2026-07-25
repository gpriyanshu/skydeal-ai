import math
from decimal import Decimal
from typing import Literal, TypedDict
from src.domain.price_history_service import RouteStats

class AdvisorResult(TypedDict):
    recommendation: Literal["BOOK NOW", "GOOD TIME TO BOOK", "WAIT", "NOT ENOUGH DATA"]
    confidence: int
    insights: list[str]

class BookingAdvisor:
    def __init__(self, settings = None):
        self.settings = settings
        
        # Expose thresholds in config.py
        self.book_now_threshold = getattr(settings, "BOOK_NOW_THRESHOLD", 80.0)
        self.wait_threshold = getattr(settings, "WAIT_THRESHOLD", 45.0)
        self.high_volatility_limit = getattr(settings, "HIGH_VOLATILITY_LIMIT", 0.15)
        self.w_history = getattr(settings, "CONFIDENCE_WEIGHT_HISTORY", 0.50)
        self.w_trend = getattr(settings, "CONFIDENCE_WEIGHT_TREND", 0.25)
        self.w_volatility = getattr(settings, "CONFIDENCE_WEIGHT_VOLATILITY", 0.25)

    def advise(
        self,
        current_price: Decimal,
        stats: RouteStats,
        trend: Literal["FALLING", "RISING", "STABLE", "UNKNOWN"],
        deal_score: float,
        budget: Decimal | None,
        raw_prices: list[Decimal]
    ) -> AdvisorResult:
        """
        Generates booking recommendations, confidence scores, and price insights.
        """
        N = stats["number_of_observations"]

        # Feature 3 — Book Now Recommendation
        if N < 3:
            recommendation = "NOT ENOUGH DATA"
        else:
            if deal_score >= self.book_now_threshold:
                recommendation = "BOOK NOW"
            elif deal_score >= self.wait_threshold:
                if trend == "FALLING":
                    recommendation = "WAIT"
                elif trend == "RISING":
                    recommendation = "GOOD TIME TO BOOK"
                else:
                    recommendation = "GOOD TIME TO BOOK"
            else:
                recommendation = "WAIT"

        # Feature 4 — Confidence Score
        if N < 3:
            confidence = 0
        else:
            # 1. History Factor (maxes at 30 observations)
            c_history = min(100.0, (N / 30.0) * 100.0)
            
            # 2. Volatility Factor (maxes at 0 volatility, drops to 0 at 50% volatility)
            vol = float(stats["price_volatility"])
            c_volatility = max(0.0, 100.0 - vol * 200.0)
            
            # 3. Trend Factor
            if trend == "UNKNOWN":
                c_trend = 50.0
            else:
                c_trend = 100.0

            total_confidence = (
                c_history * self.w_history +
                c_volatility * self.w_volatility +
                c_trend * self.w_trend
            )
            confidence = int(round(total_confidence))

        # Feature 5 — Price Insights (max 4 bullets)
        insights = []
        
        # Bullet 1: Average Comparison
        avg = stats["average_price"]
        if avg > Decimal('0'):
            if current_price < avg:
                pct = int(round(float((avg - current_price) / avg) * 100))
                insights.append(f"Current fare is {pct}% below historical average")
            else:
                pct = int(round(float((current_price - avg) / avg) * 100))
                insights.append(f"Current fare is {pct}% above historical average")

        # Bullet 2: Extremes
        lowest = stats["lowest_price"]
        if current_price <= lowest:
            insights.append(f"Lowest price seen in the last {N} scans")
        elif current_price <= lowest * Decimal('1.05'):
            insights.append("Current fare is near historical minimum")

        # Bullet 3: Consecutive observations
        consecutive_up = 0
        consecutive_down = 0
        if len(raw_prices) >= 2:
            diffs = []
            for idx in range(len(raw_prices) - 1):
                diffs.append(raw_prices[idx+1] - raw_prices[idx])
            
            # Count consecutive changes from the end
            for d in reversed(diffs):
                if d > 0:
                    if consecutive_down > 0:
                        break
                    consecutive_up += 1
                elif d < 0:
                    if consecutive_up > 0:
                        break
                    consecutive_down += 1
                else:
                    break

        if consecutive_up >= 3:
            insights.append(f"Prices have increased for {consecutive_up} consecutive observations")
        elif consecutive_down >= 3:
            insights.append(f"Prices have decreased for {consecutive_down} consecutive observations")

        # Bullet 4: Volatility
        vol = stats["price_volatility"]
        if vol > self.high_volatility_limit:
            insights.append("High volatility detected")
        else:
            insights.append("Stable pricing")

        # Bullet 5: Budget match (fallback/extra)
        if budget and current_price <= budget:
            insights.append("Excellent budget match")

        # Select first 4 bullets
        insights = insights[:4]

        return {
            "recommendation": recommendation,
            "confidence": confidence,
            "insights": insights
        }
