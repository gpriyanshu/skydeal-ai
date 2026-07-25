from src.domain.entities import Flight
from src.domain.scanner_service import ScannerService


class ScanEverywhereUseCase:
    """
    Use case responsible for performing Everywhere flight scans.
    Delegates exclusively to ScannerService.
    """
    def __init__(self, scanner_service: ScannerService):
        self.scanner_service = scanner_service

    async def execute(self, origin: str) -> list[Flight]:
        """
        Executes Everywhere scan for the given origin.
        """
        return await self.scanner_service.search_everywhere(origin)
