import random
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any
from loguru import logger

from src.domain.entities import Flight
from src.domain.interfaces import FlightProvider
from src.adapters.providers.currency_converter import CurrencyConverter
from src.adapters.providers.constants import INDIAN_AIRPORTS, AIRPORT_TO_COUNTRY


class MockFlightProvider(FlightProvider):
    """
    Mock flight provider simulating price updates for routes.
    Used for local testing and running the application worker end-to-end.
    """
    def __init__(self, settings: Any = None, seed: int | None = None):
        if seed is not None:
            random.seed(seed)
        
        self.settings = settings
        fallback_rates = getattr(settings, "FALLBACK_EXCHANGE_RATES", {"USD": 1.0, "INR": 83.5})
        self.currency_converter = CurrencyConverter(fallback_rates=fallback_rates)

        # Base prices for mock routes (in USD)
        self.routes = {
            ("DEL", "LHR"): {"price": 600.0, "airline": "Air India", "duration": 540},
            ("BOM", "DXB"): {"price": 300.0, "airline": "Emirates", "duration": 180},
            ("BLR", "SIN"): {"price": 250.0, "airline": "Singapore Airlines", "duration": 280},
            ("HYD", "BKK"): {"price": 220.0, "airline": "Thai Airways", "duration": 240},
            ("MAA", "KUL"): {"price": 180.0, "airline": "AirAsia", "duration": 220},
            ("CCU", "BKK"): {"price": 190.0, "airline": "IndiGo", "duration": 180},
            ("COK", "MCT"): {"price": 240.0, "airline": "Oman Air", "duration": 260},
            # Additional mock routes for testing filters
            ("DEL", "BOM"): {"price": 50.0, "airline": "IndiGo", "duration": 120},
            ("DEL", "LKO"): {"price": 30.0, "airline": "Air India", "duration": 60},
        }

    def _filter_and_sort_flights(self, flights: list[Flight]) -> list[Flight]:
        raw_count = len(flights)
        filtered = []
        allowed_countries = getattr(self.settings, "ALLOWED_DESTINATION_COUNTRIES", [])
        if not isinstance(allowed_countries, list):
            allowed_countries = []
        allowed_countries_lower = {c.lower() for c in allowed_countries}

        max_days = getattr(self.settings, "MAX_DAYS_AHEAD", 120)
        max_dep_date = datetime.now(timezone.utc) + timedelta(days=max_days)

        budgets = getattr(self.settings, "COUNTRY_MAX_BUDGETS", {})
        budgets_lower = {k.lower(): v for k, v in budgets.items()}

        domestic_removed = 0
        country_removed = 0
        budget_removed = 0
        departure_removed = 0

        for f in flights:
            # 1. Ignore domestic Indian flights (destination is an Indian airport)
            if f.destination.upper() in INDIAN_AIRPORTS:
                domestic_removed += 1
                continue

            # 2. Allowed destination countries filter
            dest_country = AIRPORT_TO_COUNTRY.get(f.destination.upper(), "Unknown")
            if allowed_countries_lower:
                if not dest_country or dest_country.lower() not in allowed_countries_lower:
                    country_removed += 1
                    continue

            # 3. Country-specific budget filter
            if dest_country and dest_country.lower() in budgets_lower:
                budget = budgets_lower[dest_country.lower()]
                if f.price > Decimal(str(budget)):
                    budget_removed += 1
                    continue

            # 4. Departure window filter
            dep_date = f.departure_date
            if dep_date.tzinfo is None:
                dep_date = dep_date.replace(tzinfo=timezone.utc)
            if dep_date > max_dep_date:
                departure_removed += 1
                continue

            filtered.append(f)

        # 5. Sort by INR price (cheapest first)
        filtered.sort(key=lambda x: x.price)

        # Log required metrics during every scan
        logger.info(f"Flights returned by API: {raw_count}")
        logger.info(f"Domestic removed: {domestic_removed}")
        logger.info(f"Country filter removed: {country_removed}")
        logger.info(f"Budget filter removed: {budget_removed}")
        logger.info(f"Departure window filter removed: {departure_removed}")
        logger.info(f"International retained: {len(filtered)}")
        logger.info(f"Flights sent to Deal Engine: {len(filtered)}")

        return filtered

    async def search_everywhere(self, origin: str) -> list[Flight]:
        """
        Simulates an Everywhere search by returning mock flights for all routes originating from origin.
        """
        flights = []
        departure_date = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d")
        for (org, dest) in self.routes.keys():
            if org.upper() == origin.upper():
                flights.extend(self.search_flights(origin, dest, departure_date))
        return flights

    def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: str | None = None
    ) -> list[Flight]:
        route_key = (origin.upper(), destination.upper())
        if route_key not in self.routes:
            base_price = 400.0
            airline = "Mock Airlines"
            duration = 300
        else:
            route_info = self.routes[route_key]
            base_price = route_info["price"]
            airline = route_info["airline"]
            duration = route_info["duration"]

        flights = []
        dep_dt = datetime.fromisoformat(departure_date)
        if dep_dt.tzinfo is None:
            dep_dt = dep_dt.replace(tzinfo=timezone.utc)
        ret_dt = datetime.fromisoformat(return_date) if return_date else None
        if ret_dt and ret_dt.tzinfo is None:
            ret_dt = ret_dt.replace(tzinfo=timezone.utc)
        
        price_multipliers = [0.95, 0.70, 1.10]
        
        for i, multiplier in enumerate(price_multipliers):
            price_usd = round(base_price * multiplier * random.uniform(0.95, 1.05), 2)
            stops = 0 if i == 0 else 1
            
            flight_id = f"mock_{origin.lower()}_{destination.lower()}_{dep_dt.strftime('%Y%m%d')}_{i}"
            
            # Convert price to INR
            price_inr = self.currency_converter.convert_to_inr(Decimal(str(price_usd)), "USD")

            flights.append(
                Flight(
                    id=flight_id,
                    origin=origin.upper(),
                    destination=destination.upper(),
                    departure_date=dep_dt,
                    return_date=ret_dt,
                    price=price_inr,
                    airline=airline,
                    stops=stops,
                    duration_minutes=duration + (stops * 120),
                    cabin_class="economy",
                    deep_link=f"https://skydeal.ai/book/{flight_id}"
                )
            )
            
        return self._filter_and_sort_flights(flights)

    def search_airports(self, query: str) -> list[str]:
        airports = ["DEL", "BOM", "BLR", "HYD", "MAA", "CCU", "COK", "LHR", "DXB", "SIN", "BKK", "KUL", "MCT", "LKO"]
        query_upper = query.upper()
        return [apt for apt in airports if query_upper in apt]
