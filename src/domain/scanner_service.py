import asyncio
import time

from loguru import logger

from src.domain.entities import Flight
from src.domain.exceptions import ProviderError
from src.domain.interfaces import FlightProvider


class ScannerService:
    """
    ScannerService is responsible ONLY for retrieving flights from the configured FlightProvider.
    Decoupled from deal detection, notifications, database operations, or currency conversion.
    """
    def __init__(self, provider: FlightProvider):
        self.provider = provider

    async def search_everywhere(
        self,
        origin: str | list[str],
        max_budget: float | None = None,
        depart_months: str | None = None,
        destination_codes: list[str] | None = None,
        destination_query: str | None = None
    ) -> list[Flight]:
        """
        Retrieves cheap flights from the configured provider from a single or multiple origins to everywhere.
        Supports concurrent scanning for multiple origins.
        """
        from datetime import datetime, timezone, timedelta

        # 6. Runtime Logging
        logger.info(f"Detected destination: {destination_query}")
        logger.info(f"Resolved airport codes: {destination_codes}")

        if isinstance(origin, str):
            if not origin or len(origin) != 3:
                logger.warning(
                    f"Invalid origin airport IATA code '{origin}' provided for everywhere search."
                )
                raise ValueError(f"Invalid origin airport code: {origin}")
            origins = [origin]
        else:
            origins = list(origin)

        if not origins:
            logger.warning("No origin airports provided for everywhere search.")
            return []

        start_time_all = time.perf_counter()

        if destination_codes:
            # Route-specific search to avoid global search
            logger.info("Destination resolved. Performing route-specific search.")
            
            # Resolve departure date
            dep_date = None
            if depart_months:
                if len(depart_months) == 7:  # YYYY-MM
                    dep_date = f"{depart_months}-01"
                else:
                    dep_date = depart_months
            else:
                dep_date = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d")

            # Collect flights concurrently
            tasks = []
            allowed_set = {code.upper() for code in destination_codes}
            
            for org in origins:
                org_upper = org.strip().upper()
                for dest in destination_codes:
                    dest_upper = dest.strip().upper()
                    
                    async def scan_single_route(o: str, d: str) -> list[Flight]:
                        try:
                            if hasattr(self.provider, "search_flights_async"):
                                flights = await self.provider.search_flights_async(o, d, dep_date)
                            else:
                                flights = await asyncio.to_thread(
                                    self.provider.search_flights, o, d, dep_date
                                )
                            # Ensure we only return flights matching the destination
                            return [f for f in flights if f.destination.upper() == d]
                        except Exception as e:
                            logger.error(f"FlightProvider route search failed for {o} -> {d}: {e}")
                            return []
                    
                    tasks.append(scan_single_route(org_upper, dest_upper))
            
            results = await asyncio.gather(*tasks)
            
            # Merge flights
            all_flights = []
            for res in results:
                all_flights.extend(res)
                
            flights_before_merge_count = len(all_flights)
            
            # Filter flights to ensure we ONLY return resolved airports / never return unrelated countries
            filtered_flights = [f for f in all_flights if f.destination.upper() in allowed_set]
            
            # Deduplicate
            seen = set()
            deduplicated_flights = []
            for f in filtered_flights:
                key = (
                    f.origin.upper(),
                    f.destination.upper(),
                    f.departure_date,
                    f.airline.upper() if f.airline else "",
                    f.price
                )
                if key not in seen:
                    seen.add(key)
                    deduplicated_flights.append(f)
                    
            logger.info(f"Flights before filtering: {flights_before_merge_count}")
            logger.info(f"Flights after destination filtering: {len(deduplicated_flights)}")
            
            return deduplicated_flights

        else:
            # Standard global search
            async def scan_single_origin(org: str) -> list[Flight]:
                org_upper = org.strip().upper()
                if not org_upper or len(org_upper) != 3:
                    logger.warning(f"Invalid origin airport IATA code '{org_upper}' provided.")
                    return []
                
                logger.info(f"Starting scan: {org_upper}")
                start_time = time.perf_counter()
                try:
                    if hasattr(self.provider, "search_everywhere"):
                        kwargs = {}
                        if max_budget is not None:
                            kwargs["max_budget"] = max_budget
                        if depart_months is not None:
                            kwargs["depart_months"] = depart_months
                        try:
                            flights = await self.provider.search_everywhere(org_upper, **kwargs)
                        except TypeError:
                            flights = await self.provider.search_everywhere(org_upper)
                    else:
                        raise NotImplementedError(
                            "Everywhere search is not supported by the configured provider: "
                            f"{type(self.provider).__name__}"
                        )
                except Exception as e:
                    logger.error(f"FlightProvider failed during Everywhere search from '{org_upper}': {e}")
                    if len(origins) == 1:
                        raise
                    # Provider failure for one airport while others continue
                    return []
                
                duration = time.perf_counter() - start_time
                logger.info(
                    f"Flights returned: {len(flights)}\n"
                    f"Duration: {duration:.1f} sec"
                )
                return flights

            # Execute concurrently
            tasks = [scan_single_origin(org) for org in origins]
            results = await asyncio.gather(*tasks)

            # Merge flights
            all_flights = []
            for res in results:
                all_flights.extend(res)

            flights_before_merge_count = len(all_flights)

            # Deduplicate flights:
            seen = set()
            deduplicated_flights = []
            for f in all_flights:
                key = (
                    f.origin.upper(),
                    f.destination.upper(),
                    f.departure_date,
                    f.airline.upper() if f.airline else "",
                    f.price
                )
                if key not in seen:
                    seen.add(key)
                    deduplicated_flights.append(f)

            total_duration = time.perf_counter() - start_time_all

            # Log summary
            logger.info(
                f"Origins scanned: {len(origins)}\n"
                f"Flights before merge: {flights_before_merge_count}\n"
                f"Flights after deduplication: {len(deduplicated_flights)}\n"
                f"Flights sent to Deal Engine: {len(deduplicated_flights)}\n"
                f"Total execution time: {total_duration:.1f} sec"
            )
            
            logger.info(f"Flights before filtering: {flights_before_merge_count}")
            logger.info(f"Flights after destination filtering: {len(deduplicated_flights)}")

            return deduplicated_flights

    async def search_route(
        self, origin: str, destination: str, departure_date: str, allow_domestic: bool = False
    ) -> list[Flight]:
        """
        Retrieves flights from the configured provider for a specific route and departure date.
        """
        if not origin or len(origin) != 3:
            raise ValueError(f"Invalid origin airport code: {origin}")
        if not destination or len(destination) != 3:
            raise ValueError(f"Invalid destination airport code: {destination}")
        if not departure_date:
            raise ValueError("Departure date must be provided.")

        start_time = time.perf_counter()
        logger.info(
            f"Starting route scan from '{origin}' to '{destination}' on {departure_date}..."
        )

        try:
            if hasattr(self.provider, "search_flights_async"):
                if allow_domestic:
                    flights = await self.provider.search_flights_async(
                        origin, destination, departure_date, allow_domestic=allow_domestic
                    )
                else:
                    flights = await self.provider.search_flights_async(
                        origin, destination, departure_date
                    )
            else:
                # Fallback to running synchronous search_flights in executor thread
                if allow_domestic:
                    flights = await asyncio.to_thread(
                        self.provider.search_flights, origin, destination, departure_date, allow_domestic
                    )
                else:
                    flights = await asyncio.to_thread(
                        self.provider.search_flights, origin, destination, departure_date
                    )
        except ProviderError as e:
            logger.error(
                f"FlightProvider failed during route search '{origin}' -> '{destination}': {e}"
            )
            raise
        except Exception as e:
            logger.error(
                f"Unexpected error during route search '{origin}' -> '{destination}': {e}"
            )
            raise

        duration = time.perf_counter() - start_time
        logger.info(
            f"Route scan '{origin}' -> '{destination}' finished in {duration:.2f}s. "
            f"Received {len(flights)} flights."
        )
        return flights
