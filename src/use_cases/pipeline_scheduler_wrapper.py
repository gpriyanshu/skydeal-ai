import asyncio

from src.use_cases.notification_pipeline import NotificationPipeline


class PipelineSchedulerWrapper:
    """
    A synchronous wrapper around NotificationPipeline.execute() so it can be
    executed by the synchronous background FlightScanScheduler.
    """
    def __init__(self, pipeline: NotificationPipeline):
        self.pipeline = pipeline

    def execute(self) -> None:
        """
        Runs the async pipeline execute method synchronously.
        """
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            # If the current thread has a running loop, execute in a thread pool
            future = asyncio.run_coroutine_threadsafe(self.pipeline.execute(), loop)
            future.result()
        else:
            loop.run_until_complete(self.pipeline.execute())
