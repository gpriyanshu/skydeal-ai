from src.domain.entities import Flight
from src.domain.interfaces import FlightProvider


class SkyscannerFlightProvider(FlightProvider):
    """
    Plugin adapter for the Skyscanner API provider.
    Reuses code/logic from shadyvb/mcp-skyscanner.
    
    NOTE: As per project constraints, flight searching is NOT implemented in this foundation.
    This serves as an integration extension point.
    """
    def __init__(self, settings_env: dict | None = None):
        self.settings_env = settings_env or {}

    def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: str | None = None
    ) -> list[Flight]:
        raise NotImplementedError(
            "Skyscanner search is not implemented in this phase. "
            "Please use the pluggable MockFlightProvider for testing and local runs."
        )

    def search_airports(self, query: str) -> list[str]:
        raise NotImplementedError(
            "Skyscanner airport search is not implemented in this phase."
        )
