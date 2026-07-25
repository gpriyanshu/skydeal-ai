import asyncio
from loguru import logger

from src.adapters.providers.travelpayouts_client import (
    TravelPayoutsClient,
    TravelPayoutsUnexpectedResponse,
)
from src.adapters.providers.travelpayouts_mapper import TravelPayoutsResponseMapper
from src.domain.entities import Flight
from src.domain.interfaces import FlightProvider
from src.adapters.providers.constants import INDIAN_AIRPORTS, AIRPORT_TO_COUNTRY


class TravelPayoutsProvider(FlightProvider):
    """
    Flight provider adapter for TravelPayouts (Aviasales GraphQL API).
    Orchestrates HTTP requests using TravelPayoutsClient and maps results
    using TravelPayoutsResponseMapper.
    """
    def __init__(
        self,
        client: TravelPayoutsClient,
        mapper: TravelPayoutsResponseMapper | None = None,
        settings = None
    ):
        self.client = client
        self.mapper = mapper or TravelPayoutsResponseMapper()
        self.settings = settings
        if not self.settings and client is not None:
            try:
                self.settings = client.settings
            except AttributeError:
                self.settings = None

    def _filter_and_sort_flights(self, flights: list[Flight], max_budget: float | None = None, allow_domestic: bool = False) -> list[Flight]:
        from datetime import datetime, timezone, timedelta
        from decimal import Decimal

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
            if not allow_domestic and f.destination.upper() in INDIAN_AIRPORTS:
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
                if max_budget is not None:
                    budget = max_budget
                if f.price > Decimal(str(budget)):
                    budget_removed += 1
                    continue
            elif max_budget is not None:
                if f.price > Decimal(str(max_budget)):
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

    async def search_everywhere(self, origin: str, max_budget: float | None = None, depart_months: str | None = None) -> list[Flight]:
        """
        Performs an Everywhere search from the specified origin using the TravelPayouts GraphQL API.
        Returns a list of normalized Flight domain models.
        """
        query = """
        query ($origin: String!, $depart_months: [Date!], $limit: Int!) {
          prices_one_way(
            params: {
              origin: $origin
              depart_months: $depart_months
            }
            grouping: DIRECTIONS
            paging: {
              limit: $limit
              offset: 0
            }
          ) {
            origin_airport_iata
            destination_airport_iata
            departure_at
            value
            currency
            trip_duration
            number_of_changes
            main_airline
            ticket_link
          }
        }
        """
        limit_val = int(getattr(self.settings, "TRAVELPAYOUTS_PAGE_SIZE", 300))
        variables = {
            "origin": origin.upper(),
            "limit": limit_val
        }
        if depart_months:
            if len(depart_months) == 7:
                depart_months = f"{depart_months}-01"
            variables["depart_months"] = [depart_months]
        raw_json = await self.client.execute(query, variables)
        try:
            mapped_flights = self.mapper.map(raw_json)
            return self._filter_and_sort_flights(mapped_flights, max_budget=max_budget)
        except Exception as e:
            raise TravelPayoutsUnexpectedResponse(f"Mapping failed: {e}") from e

    async def search_flights_async(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: str | None = None,  # noqa: ARG002
        allow_domestic: bool = False
    ) -> list[Flight]:
        """
        Asynchronously queries the provider for a specific route and departure date.
        """
        query = """
        query ($origin: String!, $destination: String!, $depart_months: [Date!], $limit: Int!) {
          prices_one_way(
            params: {
              origin: $origin
              destination: $destination
              depart_months: $depart_months
            }
            paging: {
              limit: $limit
              offset: 0
            }
          ) {
            origin_airport_iata
            destination_airport_iata
            departure_at
            value
            currency
            trip_duration
            number_of_changes
            main_airline
            ticket_link
          }
        }
        """
        # Extract YYYY-MM-01 for depart_months query filtering
        depart_months = [f"{departure_date[:7]}-01"] if departure_date else None
        limit_val = int(getattr(self.settings, "TRAVELPAYOUTS_PAGE_SIZE", 300))

        variables = {
            "origin": origin.upper(),
            "destination": destination.upper(),
            "depart_months": depart_months,
            "limit": limit_val
        }

        raw_json = await self.client.execute(query, variables)
        try:
            flights = self.mapper.map(raw_json)
        except Exception as e:
            raise TravelPayoutsUnexpectedResponse(f"Mapping failed: {e}") from e

        # Filter locally for flights matching the exact departure date (YYYY-MM-DD)
        date_flights = [
            f for f in flights
            if f.departure_date.strftime("%Y-%m-%d") == departure_date
        ]
        return self._filter_and_sort_flights(date_flights, allow_domestic=allow_domestic)

    def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: str | None = None,
        allow_domestic: bool = False
    ) -> list[Flight]:
        """
        Queries the provider database for flights and returns normalized domain Flight models.
        Adapts the asynchronous underlying execute calls for synchronous consumption.
        """
        try:
            return asyncio.run(
                self.search_flights_async(origin, destination, departure_date, return_date, allow_domestic)
            )
        except RuntimeError:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(
                self.search_flights_async(origin, destination, departure_date, return_date, allow_domestic)
            )

    def search_airports(self, query: str) -> list[str]:
        """
        Finds matching airport codes based on a case-insensitive query substring match.
        """
        airports = [
            "DEL", "BOM", "BLR", "HYD", "MAA", "CCU", "COK", "LHR", "DXB", "SIN",
            "BKK", "KUL", "MCT"
        ]
        query_upper = query.upper()
        return [apt for apt in airports if query_upper in apt]
