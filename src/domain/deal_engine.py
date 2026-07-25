from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from loguru import logger

from src.domain.entities import DealResult, Flight, PriceHistory
from src.domain.interfaces import PriceHistoryRepository
from src.domain.price_statistics_service import PriceStatisticsService
from src.domain.deal_scoring_services import (
    SeasonalityService,
    MarketRankingService,
    BudgetScoreService,
    DealScoringService,
)
from src.adapters.providers.constants import AIRPORT_TO_COUNTRY
from src.domain.destination_price_intelligence import DestinationPriceIntelligence


class DealEngine:
    """
    Intelligent Deal Engine responsible for price tracking, rolling average calculation,
    and classifying flights into deal tiers (NORMAL, GOOD, GREAT, SUPER) using configuration
    and a multi-factor deal scoring model.
    """
    def __init__(
        self,
        price_history_repo: PriceHistoryRepository,
        good_deal_threshold: float = 0.10,
        great_deal_threshold: float = 0.20,
        super_deal_threshold: float = 0.35,
        ema_alpha: float = 0.20,
        settings = None,
        scoring_weights: dict[str, float] | None = None,
        scoring_thresholds: dict[str, float] | None = None
    ):
        self.price_history_repo = price_history_repo
        self.good_deal_threshold = good_deal_threshold
        self.great_deal_threshold = great_deal_threshold
        self.super_deal_threshold = super_deal_threshold
        self.ema_alpha = Decimal(str(ema_alpha))
        self.settings = settings
        self.is_legacy_mode = (settings is None and not scoring_weights and not scoring_thresholds)

        # Load weights from settings or use defaults
        self.w_absolute = getattr(settings, "SCORING_WEIGHT_ABSOLUTE", 0.0 if self.is_legacy_mode else 0.35)
        self.w_historical = getattr(settings, "SCORING_WEIGHT_HISTORICAL", 0.40)
        self.w_market = getattr(settings, "SCORING_WEIGHT_MARKET", 0.20)
        self.w_percentile = getattr(settings, "SCORING_WEIGHT_PERCENTILE", 0.15)
        self.w_seasonality = getattr(settings, "SCORING_WEIGHT_SEASONALITY", 0.10)
        self.w_budget = getattr(settings, "SCORING_WEIGHT_BUDGET", 0.15)

        if scoring_weights:
            self.w_absolute = scoring_weights.get("absolute", self.w_absolute)
            self.w_historical = scoring_weights.get("historical", self.w_historical)
            self.w_market = scoring_weights.get("market", self.w_market)
            self.w_percentile = scoring_weights.get("percentile", self.w_percentile)
            self.w_seasonality = scoring_weights.get("seasonality", self.w_seasonality)
            self.w_budget = scoring_weights.get("budget", self.w_budget)

        # Load thresholds from settings or use defaults
        self.t_super = getattr(settings, "DEAL_THRESHOLD_SUPER", 90.0)
        self.t_great = getattr(settings, "DEAL_THRESHOLD_GREAT", 75.0)
        self.t_good = getattr(settings, "DEAL_THRESHOLD_GOOD", 60.0)

        if scoring_thresholds:
            self.t_super = scoring_thresholds.get("super", self.t_super)
            self.t_great = scoring_thresholds.get("great", self.t_great)
            self.t_good = scoring_thresholds.get("good", self.t_good)

        # Invalidate DealScoringService
        self.scoring_service = DealScoringService(
            weight_historical=self.w_historical,
            weight_market=self.w_market,
            weight_percentile=self.w_percentile,
            weight_seasonality=self.w_seasonality,
            weight_budget=self.w_budget,
            threshold_super=self.t_super,
            threshold_great=self.t_great,
            threshold_good=self.t_good,
            weight_absolute=self.w_absolute
        )

        self.price_intelligence = DestinationPriceIntelligence(settings)

        # Price Intelligence Services (Sprint 15)
        from src.domain.price_history_service import PriceHistoryService
        from src.domain.price_trend_service import PriceTrendService
        from src.domain.booking_advisor import BookingAdvisor

        self.history_service = PriceHistoryService(self.price_history_repo)
        self.trend_service = PriceTrendService(self.price_history_repo)
        self.booking_advisor = BookingAdvisor(self.settings)

    def calculate_deal_score(self, current_price: Decimal, historical_average: Decimal) -> float:
        """
        Calculates a deal score based on the percentage discount below the historical average.
        Maintained for legacy compatibility.
        """
        if historical_average <= Decimal('0'):
            return 0.0
        discount = ((historical_average - current_price) / historical_average) * Decimal('100.0')
        return max(0.0, round(float(discount), 2))

    def classify_deal_category(
        self, current_price: Decimal, historical_average: Decimal, historical_lowest: Decimal
    ) -> Literal["NORMAL", "GOOD", "GREAT", "SUPER"]:
        """
        Classifies a flight price into a deal category based on configured thresholds.
        Maintained for legacy compatibility.
        """
        if historical_average <= Decimal('0'):
            return "NORMAL"

        discount = float((historical_average - current_price) / historical_average)

        if current_price < historical_lowest or discount >= self.super_deal_threshold:
            return "SUPER"
        if discount >= self.great_deal_threshold:
            return "GREAT"
        if discount >= self.good_deal_threshold:
            return "GOOD"
        return "NORMAL"

    def process_flights(self, flights: list[Flight]) -> list[DealResult]:
        """
        Deduplicates flights, updates their historical metrics, runs the multi-factor deal
        scoring calculations, and returns the DealResults with explanations.
        """
        if not flights:
            return []

        # Deduplicate flights within the same scan to avoid double-counting
        unique_flights: list[Flight] = []
        seen_keys = set()
        for f in flights:
            key = (
                f.origin.upper(),
                f.destination.upper(),
                f.departure_date.isoformat(),
                f.price
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)
            unique_flights.append(f)

        # Precompute Market Rankings and Percentiles by destination country
        country_groups: dict[str, list[Flight]] = {}
        for f in unique_flights:
            country = AIRPORT_TO_COUNTRY.get(f.destination.upper(), "Unknown").lower()
            if country not in country_groups:
                country_groups[country] = []
            country_groups[country].append(f)

        market_scores = MarketRankingService.calculate_scores(unique_flights, country_groups)

        country_sorted_prices: dict[str, list[Decimal]] = {}
        for country, group in country_groups.items():
            country_sorted_prices[country] = sorted([f.price for f in group])

        results: list[DealResult] = []
        now = datetime.now(timezone.utc)

        for flight in unique_flights:
            history = self.price_history_repo.get(flight.origin, flight.destination)

            if not history:
                # Initialize baseline PriceHistory
                history = PriceHistory(
                    origin=flight.origin,
                    destination=flight.destination,
                    current_price=flight.price,
                    lowest_price=flight.price,
                    highest_price=flight.price,
                    rolling_average=flight.price,
                    first_seen=now,
                    last_seen=now,
                    observation_count=1
                )
                self.price_history_repo.save(history)
                old_average = flight.price
                old_lowest = flight.price
            else:
                # Record stats before updating history to compare against historical average
                old_average = history.rolling_average
                old_lowest = history.lowest_price

                # Calculate updated stats
                lowest = min(history.lowest_price, flight.price)
                highest = max(history.highest_price, flight.price)
                new_rolling = PriceStatisticsService.calculate_ema(
                    flight.price, old_average, self.ema_alpha
                )

                # Update and save history
                history.current_price = flight.price
                history.lowest_price = lowest
                history.highest_price = highest
                history.rolling_average = new_rolling
                history.last_seen = now
                history.observation_count += 1
                self.price_history_repo.save(history)

            # Save raw price observation
            try:
                self.price_history_repo.save_observation(flight.origin, flight.destination, flight.price, now)
            except Exception as e:
                pass

            # --- LEGACY COMPATIBILITY MODE ---
            if self.is_legacy_mode:
                savings = max(Decimal('0'), old_average - flight.price)
                pct_diff = PriceStatisticsService.calculate_percentage_difference(flight.price, old_average)
                deal_score = self.calculate_deal_score(flight.price, old_average)
                deal_category = self.classify_deal_category(flight.price, old_average, old_lowest)

                if history.observation_count == 1:
                    deal_score = 0.0
                    deal_category = "NORMAL"
                    savings = Decimal('0')
                    pct_diff = 0.0

                deal_result = DealResult(
                    flight=flight,
                    current_price=flight.price,
                    historical_stats=history,
                    deal_score=deal_score,
                    deal_category=deal_category,
                    savings=savings,
                    percentage_below_average=pct_diff,
                    score_breakdown={
                        "Historical": deal_score,
                        "Market": 0.0,
                        "Percentile": 0.0,
                        "Seasonality": 0.0,
                        "Budget": 0.0
                    },
                    explanation="Legacy mode scoring"
                )
                results.append(deal_result)
                continue

            # Determine destination country and budget limit
            dest_country = AIRPORT_TO_COUNTRY.get(flight.destination.upper(), "Unknown")
            budgets = getattr(self.settings, "COUNTRY_MAX_BUDGETS", {})
            budget = budgets.get(dest_country.lower()) if isinstance(budgets, dict) else None
            if budget is not None:
                budget = Decimal(str(budget))

            # --- MULTI-FACTOR SCORING ---
            # 1. Absolute Fare Score (Sprint 21)
            absolute_score = self.price_intelligence.calculate_absolute_fare_score(dest_country, flight.price)
            absolute_band = self.price_intelligence.get_price_band(dest_country, flight.price).upper()

            # 2. Historical Score
            hist_score = self.scoring_service.calculate_historical_score(
                flight.price, history, old_average, old_lowest
            )

            # 3. Market Score
            market_score = market_scores.get(flight.id, 50.0)

            # 4. Percentile Score
            country_key = dest_country.lower()
            sorted_prices = country_sorted_prices.get(country_key, [flight.price])
            percentile_score = self.scoring_service.calculate_percentile_score(flight.price, sorted_prices)

            # 5. Seasonality Score
            seasonality_score = SeasonalityService.calculate_score(flight.destination, flight.departure_date)

            # 6. Budget Score
            budget_score = BudgetScoreService.calculate_score(flight.price, budget)

            # 7. Combined Final Score
            final_score = self.scoring_service.calculate_final_score(
                historical_score=hist_score,
                market_score=market_score,
                percentile_score=percentile_score,
                seasonality_score=seasonality_score,
                budget_score=budget_score,
                absolute_score=absolute_score
            )

            # Classify deal category using final score
            deal_category = self.scoring_service.classify_category(final_score)

            # Generate dynamic explanation bullets (Sprint 21 absolute price intelligence first)
            bullets = []
            bullets.extend(self.price_intelligence.explain_price_quality(dest_country, flight.price))
            
            if len(sorted_prices) > 1:
                idx = sorted_prices.index(flight.price)
                pct = int((idx / (len(sorted_prices) - 1)) * 100)
                if pct <= 10:
                    bullets.append(f"Cheapest {pct}% today" if pct > 0 else "Cheapest flight today")
            if budget and flight.price < budget:
                savings_pct = int(((budget - flight.price) / budget) * 100)
                if savings_pct >= 30:
                    bullets.append("Excellent budget match")
                elif savings_pct >= 15:
                    bullets.append("Great budget match")
                else:
                    bullets.append("Good budget match")
            if seasonality_score == 100.0:
                bullets.append("Peak season pricing")
            if old_average > Decimal('0') and flight.price < old_average:
                bullets.append("Historical average beaten")

            explanation = "; ".join(bullets) if bullets else "Consistent with market pricing"

            # Sprint 21 - absolute price intelligence log layout
            logger.info(
                f"\n{dest_country}\n"
                f"Price:\n"
                f"₹{int(flight.price):,}\n"
                f"Absolute Fare:\n"
                f"{absolute_band}\n"
                f"Absolute Score:\n"
                f"{int(absolute_score)}\n"
                f"Historical:\n"
                f"{int(hist_score)}\n"
                f"Market:\n"
                f"{int(market_score)}\n"
                f"Budget:\n"
                f"{int(budget_score)}\n"
                f"Seasonality:\n"
                f"{int(seasonality_score)}\n"
                f"Final:\n"
                f"{int(final_score)}\n"
                f"Category:\n"
                f"{deal_category}"
            )

            # Structured logs
            logger.info(
                f"Evaluating {flight.origin} -> {flight.destination} | "
                f"Historical: {hist_score} | "
                f"Market: {market_score} | "
                f"Percentile: {percentile_score} | "
                f"Seasonality: {seasonality_score} | "
                f"Budget: {budget_score} | "
                f"Final Score: {final_score} | "
                f"Category: {deal_category}"
            )

            # Run advisor services
            stats = self.history_service.calculate_stats(flight.origin, flight.destination, flight.price)
            trend = self.trend_service.detect_trend(flight.origin, flight.destination, flight.price)
            try:
                raw_prices = self.price_history_repo.get_observations(flight.origin, flight.destination)
            except Exception:
                raw_prices = []

            if not stats:
                stats = {
                    "lowest_price": flight.price,
                    "highest_price": flight.price,
                    "average_price": flight.price,
                    "median_price": flight.price,
                    "standard_deviation": Decimal('0'),
                    "last_seen_price": flight.price,
                    "first_seen_price": flight.price,
                    "price_volatility": Decimal('0'),
                    "number_of_observations": 1
                }

            advisor_res = self.booking_advisor.advise(
                flight.price, stats, trend, final_score, budget, raw_prices
            )

            # Feature 7 - Runtime Logging
            logger.info(
                f"{flight.origin} -> {flight.destination}\n"
                f"Current {flight.price}\n"
                f"Average {stats['average_price']}\n"
                f"Minimum {stats['lowest_price']}\n"
                f"Trend {trend}\n"
                f"Recommendation {advisor_res['recommendation']}\n"
                f"Confidence {advisor_res['confidence']}"
            )

            # Perform legacy deal calculations
            savings = max(Decimal('0'), old_average - flight.price)
            pct_diff = PriceStatisticsService.calculate_percentage_difference(
                flight.price, old_average
            )

            score_breakdown = {
                "Absolute": absolute_score,
                "Historical": hist_score,
                "Market": market_score,
                "Percentile": percentile_score,
                "Seasonality": seasonality_score,
                "Budget": budget_score
            }

            deal_result = DealResult(
                flight=flight,
                current_price=flight.price,
                historical_stats=history,
                deal_score=final_score,  # Overridden with new final multi-factor score
                deal_category=deal_category,
                savings=savings,
                percentage_below_average=pct_diff,
                score_breakdown=score_breakdown,
                explanation=explanation,
                recommendation=advisor_res["recommendation"],
                confidence=advisor_res["confidence"],
                insights=advisor_res["insights"]
            )
            results.append(deal_result)

        return results
