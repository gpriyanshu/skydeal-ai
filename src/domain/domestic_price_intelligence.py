from decimal import Decimal
from typing import Any
from src.destination_regions import DOMESTIC_PRICE_BANDS

class DomesticPriceIntelligence:
    """
    Authoritative source for domestic route price evaluation and category classification.
    """
    def __init__(self, settings: Any = None):
        self.settings = settings

    def get_price_band(self, origin: str, destination: str, price: float | Decimal) -> str:
        price_val = float(price)
        route_key = f"{origin.upper()}-{destination.upper()}"
        
        bands = DOMESTIC_PRICE_BANDS.get(route_key)
        if not bands:
            # Fallback default bands for unconfigured domestic routes
            bands = {
                "excellent": 4000.0,
                "great": 5000.0,
                "good": 6000.0,
                "average": 7500.0
            }
            
        if price_val <= bands["excellent"]:
            return "excellent"
        elif price_val <= bands["great"]:
            return "great"
        elif price_val <= bands["good"]:
            return "good"
        elif price_val <= bands["average"]:
            return "average"
        else:
            return "expensive"

    def calculate_score(self, origin: str, destination: str, price: float | Decimal) -> float:
        band = self.get_price_band(origin, destination, price)
        mapping = {
            "excellent": 100.0,
            "great": 90.0,
            "good": 75.0,
            "average": 50.0,
            "expensive": 20.0
        }
        return mapping.get(band, 50.0)

    def classify_category(self, origin: str, destination: str, price: float | Decimal) -> str:
        band = self.get_price_band(origin, destination, price)
        mapping = {
            "excellent": "SUPER",
            "great": "GREAT",
            "good": "GOOD",
            "average": "NORMAL",
            "expensive": "NORMAL"
        }
        return mapping.get(band, "NORMAL")

    def get_recommendation(self, origin: str, destination: str, price: float | Decimal) -> str:
        band = self.get_price_band(origin, destination, price)
        if band in ["excellent", "great"]:
            return "Book Now"
        elif band == "good":
            return "Good Time to Book"
        else:
            return "Wait"

    def get_average_price(self, origin: str, destination: str) -> float:
        route_key = f"{origin.upper()}-{destination.upper()}"
        bands = DOMESTIC_PRICE_BANDS.get(route_key)
        if bands:
            return float(bands["average"])
        return 7500.0
