from src.domain.entities import Flight
from src.domain.scanner_service import ScannerService


class ScanRouteUseCase:
    """
    Use case responsible for performing flight scans for a specific route and departure date.
    Delegates exclusively to ScannerService.
    """
    def __init__(self, scanner_service: ScannerService):
        self.scanner_service = scanner_service

    async def execute(
        self, origin: str, destination: str, departure_date: str
    ) -> list[Flight]:
        """
        Executes Route scan for the given parameters.
        """
        return await self.scanner_service.search_route(origin, destination, departure_date)
