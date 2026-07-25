from typing import Protocol

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger


class ScanUseCase(Protocol):
    def execute(self) -> None:
        ...


class FlightScanScheduler:
    """
    Background scheduler manager using APScheduler to trigger 
    periodic flight scans at configured intervals.
    """
    def __init__(self, scan_use_case: ScanUseCase, interval_hours: int = 1):
        self.scan_use_case = scan_use_case
        self.interval_hours = interval_hours
        self.scheduler = BackgroundScheduler()

    def start(self) -> None:
        """Starts the scheduler, registering the scanning job."""
        logger.info(f"Registering flight scanning job to run every {self.interval_hours} hour(s).")
        
        # Schedule the scan flights use case execution
        self.scheduler.add_job(
            func=self.scan_use_case.execute,
            trigger=IntervalTrigger(hours=self.interval_hours),
            id="flight_scan_job",
            name="Periodic Flight Scanning Job",
            replace_existing=True
        )
        
        self.scheduler.start()
        logger.info("Scheduler started successfully in the background.")

    def stop(self) -> None:
        """Stops the scheduler, waiting for active jobs to complete."""
        logger.info("Shutting down the background scheduler...")
        self.scheduler.shutdown(wait=True)
        logger.info("Scheduler shut down successfully.")
