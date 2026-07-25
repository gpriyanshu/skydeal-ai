import math
from datetime import datetime, timezone
from decimal import Decimal
from src.domain.entities import Flight, PriceHistory
from src.domain.price_statistics_service import PriceStatisticsService
from src.adapters.providers.constants import AIRPORT_TO_COUNTRY

class SeasonalityService:
    @staticmethod
    def calculate_score(destination_iata: str, departure_date: datetime) -> float:
        """
        Calculates seasonal score (40, 70, or 100) based on peak/shoulder/off-peak season rules.
        """
        country = AIRPORT_TO_COUNTRY.get(destination_iata.upper(), "Unknown").lower()
        month = departure_date.month
        day = departure_date.day

        # Japan peak: March 15 to April 30 (Cherry blossom), Oct 15 to Nov 30 (Autumn foliage)
        # Japan shoulder: rest of March (1-14), rest of October (1-14), May, September
        if "japan" in country:
            if (month == 3 and day >= 15) or (month == 4) or (month == 10 and day >= 15) or (month == 11):
                return 100.0
            if (month == 3 and day < 15) or (month == 10 and day < 15) or month in [5, 9]:
                return 70.0
            return 40.0

        # Thailand peak: November to January (covers December)
        # Thailand shoulder: February, March, October
        elif "thailand" in country:
            if month in [11, 12, 1]:
                return 100.0
            if month in [2, 3, 10]:
                return 70.0
            return 40.0

        # Germany, France, Italy peak: June to August (Summer), Dec 15 to Jan 5 (Christmas)
        # Germany, France, Italy shoulder: May, September, rest of December (1-14), rest of January (6-31)
        elif any(c in country for c in ["germany", "france", "italy"]):
            if month in [6, 7, 8] or (month == 12 and day >= 15) or (month == 1 and day <= 5):
                return 100.0
            if month in [5, 9] or (month == 12 and day < 15) or (month == 1 and day > 5):
                return 70.0
            return 40.0

        # United Arab Emirates peak: November to February
        # United Arab Emirates shoulder: October, March, April
        elif "united arab emirates" in country or "uae" in country:
            if month in [11, 12, 1, 2]:
                return 100.0
            if month in [10, 3, 4]:
                return 70.0
            return 40.0

        # South Korea peak: April, May, September, October
        # South Korea shoulder: March, June, November
        elif "south korea" in country or "korea" in country:
            if month in [4, 5, 9, 10]:
                return 100.0
            if month in [3, 6, 11]:
                return 70.0
            return 40.0

        # Singapore, Vietnam, Malaysia, Indonesia (Summer / Winter peak): July, August, December
        # Shoulder: June, September, January, May
        elif any(c in country for c in ["singapore", "vietnam", "malaysia", "indonesia"]):
            if month in [7, 8, 12]:
                return 100.0
            if month in [6, 9, 1, 5]:
                return 70.0
            return 40.0

        # Default for other countries (e.g. December, summer peak)
        else:
            if month in [12, 7, 8]:
                return 100.0
            if month in [6, 9, 1, 11]:
                return 70.0
            return 40.0


class MarketRankingService:
    @staticmethod
    def calculate_scores(flights: list[Flight], country_groups: dict[str, list[Flight]]) -> dict[str, float]:
        """
        Calculates market ranking score (0-100) for each flight.
        flights: all flights in current scan
        country_groups: flights grouped by destination country (lowercase)
        """
        scores = {}
        for country, group in country_groups.items():
            N = len(group)
            if N == 0:
                continue
            if N == 1:
                scores[group[0].id] = 100.0
                continue
            
            # Sort flights by price ascending
            sorted_group = sorted(group, key=lambda f: f.price)
            # Precompute unique prices list to handle ties properly
            sorted_prices = sorted(list({f.price for f in group}))
            P = len(sorted_prices)
            
            for f in group:
                if P == 1:
                    scores[f.id] = 100.0
                else:
                    rank_idx = sorted_prices.index(f.price)
                    # Cheapest unique price (rank_idx == 0) -> 100.0
                    # Most expensive unique price (rank_idx == P-1) -> 0.0
                    scores[f.id] = round(100.0 - (rank_idx / (P - 1)) * 100.0, 2)
        return scores


class BudgetScoreService:
    @staticmethod
    def calculate_score(price: Decimal, budget: Decimal | None) -> float:
        """
        Calculates budget attractiveness score (0-100) relative to a reference budget.
        """
        if not budget or budget <= Decimal('0'):
            return 50.0  # Neutral score if budget is missing or 0
        if price >= budget:
            return 0.0
        
        # Calculate percentage below budget
        saving_pct = float(((budget - price) / budget) * 100)
        # Scale: 50% or more savings below budget -> 100.0
        score = (saving_pct / 50.0) * 100.0
        return min(100.0, max(0.0, round(score, 2)))


class DealScoringService:
    def __init__(
        self,
        weight_historical: float = 0.40,
        weight_market: float = 0.20,
        weight_percentile: float = 0.15,
        weight_seasonality: float = 0.10,
        weight_budget: float = 0.15,
        threshold_super: float = 90.0,
        threshold_great: float = 75.0,
        threshold_good: float = 60.0,
        weight_absolute: float = 0.0
    ):
        self.weight_historical = weight_historical
        self.weight_market = weight_market
        self.weight_percentile = weight_percentile
        self.weight_seasonality = weight_seasonality
        self.weight_budget = weight_budget
        self.threshold_super = threshold_super
        self.threshold_great = threshold_great
        self.threshold_good = threshold_good
        self.weight_absolute = weight_absolute

    def calculate_percentile_score(self, price: Decimal, sorted_prices: list[Decimal]) -> float:
        """
        Calculates the percentile score based on price bins:
          - Cheapest 10% -> 100
          - Top 20% -> 90
          - Top 30% -> 80
          - Middle (30% to 50%) -> 50
          - Expensive (>50%) -> 10
        """
        N = len(sorted_prices)
        if N <= 1:
            return 100.0
        
        idx = sorted_prices.index(price)
        percentile = idx / (N - 1)
        
        if percentile <= 0.10:
            return 100.0
        elif percentile <= 0.20:
            return 90.0
        elif percentile <= 0.30:
            return 80.0
        elif percentile <= 0.50:
            return 50.0
        else:
            return 10.0

    def calculate_historical_score(
        self, price: Decimal, history: PriceHistory | None, old_average: Decimal, old_lowest: Decimal
    ) -> float:
        """
        Calculates historical score (0-100). Beating absolute lowest gives 100.0.
        Otherwise, 35% or more discount below rolling average gives 100.0.
        """
        if not history or old_average <= Decimal('0'):
            return 0.0
        
        if price < old_lowest:
            return 100.0
            
        discount_pct = PriceStatisticsService.calculate_percentage_difference(price, old_average)
        if discount_pct <= 0.0:
            return 0.0
            
        score = (discount_pct / 35.0) * 100.0
        return min(100.0, max(0.0, round(score, 2)))

    def calculate_final_score(
        self,
        historical_score: float,
        market_score: float,
        percentile_score: float,
        seasonality_score: float,
        budget_score: float,
        absolute_score: float | None = None
    ) -> float:
        """
        Combines scores using configured weights. Supports backwards compatibility if absolute_score is not passed.
        """
        if absolute_score is None:
            total = (
                historical_score * self.weight_historical +
                market_score * self.weight_market +
                percentile_score * self.weight_percentile +
                seasonality_score * self.weight_seasonality +
                budget_score * self.weight_budget
            )
        else:
            total = (
                absolute_score * self.weight_absolute +
                historical_score * self.weight_historical +
                market_score * self.weight_market +
                percentile_score * self.weight_percentile +
                seasonality_score * self.weight_seasonality +
                budget_score * self.weight_budget
            )
        return round(total, 2)

    def classify_category(self, final_score: float) -> str:
        """
        Classifies deal category (NORMAL, GOOD, GREAT, SUPER) based on final score.
        """
        if final_score >= self.threshold_super:
            return "SUPER"
        elif final_score >= self.threshold_great:
            return "GREAT"
        elif final_score >= self.threshold_good:
            return "GOOD"
        else:
            return "NORMAL"
