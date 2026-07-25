import asyncio
import sys
import time

from fastmcp import FastMCP
from loguru import logger

from src.config import get_settings
from src.infrastructure.di_container import DIContainer

# 1. Initialize Loguru logger
logger.remove()  # Remove default handler
logger.add(
    sys.stdout,
    format=(
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level:7}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    ),
    level=get_settings().LOG_LEVEL,
)

# 2. Boot DI Container
settings = get_settings()
container = DIContainer(settings)

# 3. Create the FastMCP server instance
mcp = FastMCP("SkyDeal AI")

# Persistent container for running tasks to prevent garbage collection
background_tasks = set()


# 4. Register FastMCP Tools (Extension Point for AI agents / MCP client integrations)
@mcp.tool()
async def run_manual_scan() -> str:
    """
    Manually triggers a flight price scan across all default routes
    and checks for new deals.
    """
    logger.info("Manual scan triggered via MCP tool.")
    try:
        await container.notification_pipeline.execute()
        return "Flight scan completed successfully. Check logs for detected deals."
    except Exception as e:
        logger.error(f"Manual scan failed: {e}")
        return f"Scan failed: {e!s}"


@mcp.tool()
def get_recent_deals(limit: int = 5) -> str:
    """
    Retrieves the most recently detected flight deals.
    """
    try:
        deals = container.deal_repo.get_recent_deals(limit)
        if not deals:
            return "No deals have been detected yet."

        result = []
        for deal in deals:
            flight = deal.flight
            route_str = f"{flight.origin} -> {flight.destination}"
            dep_date = flight.departure_date.strftime('%Y-%m-%d')
            result.append(
                f"- [{deal.category}] {route_str} on {dep_date} "
                f"for ${flight.price} (Avg: ${deal.historical_average}, "
                f"Save {deal.discount_percentage}%)"
            )
        return "\n".join(result)
    except Exception as e:
        return f"Error retrieving deals: {e!s}"


@mcp.tool()
def register_alert_subscriber(chat_id: str, budget: float, origin: str) -> str:
    """
    Registers a new user/chat_id to monitor flight deals for a specific origin
    airport with a budget.
    """
    try:
        # Onboard user
        container.manage_users_use_case.register_user(chat_id)
        # Update preferences
        container.manage_users_use_case.update_budget(chat_id, budget)
        container.manage_users_use_case.update_airports(chat_id, [origin])
        return (
            f"Subscriber {chat_id} registered successfully for origin "
            f"{origin.upper()} with budget ${budget}."
        )
    except Exception as e:
        return f"Failed to register subscriber: {e!s}"


def start_app() -> None:
    """Bootstraps database, runs initial scan, and starts scheduler."""
    logger.info("Starting SkyDeal AI Foundation...")
    
    # Sprint 20 - Startup logs for Regional Alert Strategy
    from src.destination_regions import ASIA, MIDDLE_EAST, EUROPE
    countries = settings.DEFAULT_ALERT_REGION
    if isinstance(countries, str):
        countries = [c.strip() for c in countries.split(",") if c.strip()]
    
    c_set = {c.lower() for c in countries}
    if c_set == {c.lower() for c in ASIA}:
        region_name = "Asia"
    elif c_set == {c.lower() for c in MIDDLE_EAST}:
        region_name = "Middle East"
    elif c_set == {c.lower() for c in EUROPE}:
        region_name = "Europe"
    else:
        region_name = "Custom"
        
    logger.info(f"Default Alert Region: {region_name}")
    logger.info("Countries monitored:")
    for country in sorted(countries):
        logger.info(country)
    logger.info(f"Total monitored countries: {len(countries)}")

    print("Configured scan origins:")
    print(", ".join(settings.SCAN_ORIGINS))

    # Validate at startup
    if not settings.TELEGRAM_BOT_TOKEN:
        raise ValueError("Configuration Error: TELEGRAM_BOT_TOKEN is missing. Application cannot start.")

    if not settings.TELEGRAM_DEFAULT_CHAT_ID:
        logger.warning(
            "TELEGRAM_DEFAULT_CHAT_ID is missing. Automatic notifications are disabled until a chat ID is configured."
        )

    # Pre-populate database with a mock user for testing if users table is empty
    try:
        mock_chat_id = settings.TELEGRAM_DEFAULT_CHAT_ID
        if mock_chat_id:
            if not container.user_repo.get_by_id(mock_chat_id):
                logger.info(f"Pre-populating database with mock user: {mock_chat_id}")
                container.manage_users_use_case.register_user(mock_chat_id, "mock_admin")
                container.manage_users_use_case.update_budget(mock_chat_id, 50000.0)
                container.manage_users_use_case.update_airports(mock_chat_id, ["DEL", "BOM", "BLR"])
                container.manage_users_use_case.update_countries(
                    mock_chat_id, ["United Kingdom", "Singapore", "United Arab Emirates"]
                )
            
            if not container.personal_route_service.list_routes(mock_chat_id):
                default_routes = getattr(settings, "DEFAULT_PERSONAL_ROUTES", [])
                for o, d in default_routes:
                    try:
                        container.personal_route_service.add_route(mock_chat_id, o, d)
                        logger.info(f"Seeded personal route {o} -> {d} for user {mock_chat_id}")
                    except Exception as se:
                        logger.warning(f"Failed to seed personal route {o} -> {d}: {se}")
    except Exception as e:
        logger.error(f"Failed to pre-populate database: {e}")

    # Run initial baseline scan
    logger.info("Executing initial startup flight scan...")
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            task = loop.create_task(container.notification_pipeline.execute())
            background_tasks.add(task)
            task.add_done_callback(background_tasks.discard)
        else:
            asyncio.run(container.notification_pipeline.execute())
    except Exception as e:
        logger.error(f"Initial startup scan failed: {e}")

    # Start periodic background scheduler
    container.scheduler.start()

    # Start Telegram bot long-polling in a background thread
    import threading
    def run_bot_listener():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(container.telegram_bot_listener.start_polling())
        except Exception as e:
            logger.error(f"Telegram Bot listener thread crashed: {e}")
        finally:
            loop.close()

    listener_thread = threading.Thread(target=run_bot_listener, daemon=True)
    listener_thread.start()


if __name__ == "__main__":
    start_app()
    try:
        # Keep main thread alive while scheduler runs
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        container.scheduler.stop()
        container.telegram_bot_listener.stop()
        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                task = loop.create_task(container.close())
                background_tasks.add(task)
                task.add_done_callback(background_tasks.discard)
            else:
                asyncio.run(container.close())
        except Exception as e:
            logger.error(f"Error during DI container resource cleanup: {e}")
        logger.info("SkyDeal AI gracefully shut down.")
