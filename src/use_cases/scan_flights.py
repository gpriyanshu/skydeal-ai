from datetime import datetime, timezone, timedelta

from loguru import logger

from src.domain.interfaces import FlightProvider
from src.use_cases.detect_deals import DealEngine
from src.use_cases.notify_users import NotifyUsersUseCase


class ScanFlightsUseCase:
    """
    Coordinates flight scanning iterations across default airports.
    Queries the flight provider, pushes scans to the Deal Engine, and triggers alerts.
    """
    def __init__(
        self,
        flight_provider: FlightProvider,
        deal_engine: DealEngine,
        notify_users_use_case: NotifyUsersUseCase,
        default_origins: list[str] | None = None,
        default_destinations: list[str] | None = None
    ):
        self.flight_provider = flight_provider
        self.deal_engine = deal_engine
        self.notify_users_use_case = notify_users_use_case
        
        # Specified default origins from PROJECT_SPEC.md
        self.default_origins = default_origins or ["DEL", "BOM", "BLR", "HYD", "MAA", "CCU", "COK"]
        
        # Extension point: Fallback destinations when everywhere search is not active
        self.default_destinations = default_destinations or ["LHR", "DXB", "SIN", "BKK", "KUL", "MCT"]

    def execute(self) -> None:
        """Runs the flight scanner for all configured origin-destination pairs."""
        logger.info("Starting flight scanning iteration...")
        
        # Target a fixed departure date for scanning (e.g. 30 days from now)
        scan_departure_date = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d")
        total_flights_scanned = 0
        total_deals_detected = []

        for origin in self.default_origins:
            for destination in self.default_destinations:
                if origin == destination:
                    continue

                try:
                    logger.debug(f"Scanning route {origin} -> {destination} for departure date {scan_departure_date}...")
                    
                    flights = self.flight_provider.search_flights(
                        origin=origin,
                        destination=destination,
                        departure_date=scan_departure_date
                    )
                    
                    if not flights:
                        logger.debug(f"No flights found for route {origin} -> {destination}")
                        continue
                        
                    total_flights_scanned += len(flights)
                    
                    # Analyze flights using the Deal Engine
                    detected_deals = self.deal_engine.analyze_flights(flights)
                    total_deals_detected.extend(detected_deals)
                    
                except Exception as e:
                    logger.error(f"Error occurred while scanning route {origin} -> {destination}: {e}")
                    # Keep scanning other routes even if one fails

        logger.info(
            f"Scanning iteration finished. Scanned {total_flights_scanned} flights, "
            f"detected {len(total_deals_detected)} deals."
        )

        # Trigger user notifications if any deals were detected
        if total_deals_detected:
            try:
                self.notify_users_use_case.execute(total_deals_detected)
            except Exception as e:
                logger.critical(f"Critical failure inside notification pipeline: {e}")
