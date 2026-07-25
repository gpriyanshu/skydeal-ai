from decimal import Decimal
from typing import Any
from src.destination_regions import ASIA, MIDDLE_EAST, EUROPE, DESTINATION_PRICE_BANDS

class DestinationPriceIntelligence:
    """
    Authoritative service for absolute destination price intelligence.
    Evaluates whether a fare is objectively attractive for a destination regardless of historical deviations.
    """
    def __init__(self, settings: Any = None):
        self.settings = settings

    def get_price_band(self, country: str, price: float | Decimal) -> str:
        """
        Looks up the price band for a country and price.
        Returns one of: 'excellent', 'great', 'good', 'average', 'expensive', 'very expensive'
        """
        price_val = float(price)
        
        # 1. Look up configured bands
        bands = None
        for k, v in DESTINATION_PRICE_BANDS.items():
            if k.lower() == country.lower():
                bands = v
                break
                
        # 2. Fallback to settings country budget if not in bands
        if not bands and self.settings:
            budgets = getattr(self.settings, "COUNTRY_MAX_BUDGETS", {})
            if isinstance(budgets, dict):
                for k, v in budgets.items():
                    if k.lower() == country.lower():
                        avg_val = float(v)
                        bands = {
                            "excellent": avg_val * 0.70,
                            "great": avg_val * 0.85,
                            "good": avg_val * 0.95,
                            "average": avg_val
                        }
                        break
                    
        # 3. Final default fallback
        if not bands:
            bands = {
                "excellent": 15000.0,
                "great": 20000.0,
                "good": 25000.0,
                "average": 30000.0
            }
            
        if price_val <= bands["excellent"]:
            return "excellent"
        elif price_val <= bands["great"]:
            return "great"
        elif price_val <= bands["good"]:
            return "good"
        elif price_val <= bands["average"]:
            return "average"
        elif price_val <= bands["average"] * 1.25:
            return "expensive"
        else:
            return "very expensive"

    def calculate_absolute_fare_score(self, country: str, price: float | Decimal) -> float:
        """
        Calculates an absolute fare score (0-100) based on the price band.
        """
        band = self.get_price_band(country, price)
        mapping = {
            "excellent": 100.0,
            "great": 90.0,
            "good": 75.0,
            "average": 50.0,
            "expensive": 20.0,
            "very expensive": 0.0
        }
        return mapping.get(band, 50.0)

    def explain_price_quality(self, country: str, price: float | Decimal) -> list[str]:
        """
        Generates destination-aware price quality explanation bullets.
        """
        band = self.get_price_band(country, price)
        
        # Capitalize country name nicely
        country_name = country.title()
        if country.lower() == "uae":
            country_name = "UAE"
        elif country.lower() == "usa" or country.lower() == "united states":
            country_name = "USA"
        elif country.lower() == "uk" or country.lower() == "united kingdom":
            country_name = "UK"
            
        explanations = []
        if band == "excellent":
            explanations.extend([
                f"Excellent fare for {country_name}",
                f"Below typical {country_name} pricing"
            ])
        elif band == "great":
            explanations.extend([
                f"Great {country_name} fare",
                f"Below typical {country_name} pricing"
            ])
        elif band == "good":
            explanations.extend([
                f"Good fare for {country_name}",
                f"Consistent with good {country_name} pricing"
            ])
        elif band == "average":
            explanations.extend([
                f"Average fare for {country_name}",
                f"Consistent with typical {country_name} pricing"
            ])
        elif band == "expensive":
            explanations.append(f"Above average fare for {country_name}")
        else:
            explanations.append(f"High fare for {country_name}")
            
        return explanations
