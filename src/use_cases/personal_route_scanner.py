import time
from datetime import datetime, timezone, timedelta
from loguru import logger
from decimal import Decimal

from src.domain.entities import Deal, Notification
from src.domain.interfaces import (
    PersonalRouteRepository,
    DealRepository,
    NotificationRepository
)
from src.domain.scanner_service import ScannerService
from src.domain.notification_formatter import NotificationFormatter
from src.domain.domestic_price_intelligence import DomesticPriceIntelligence
from src.adapters.notifications.telegram import TelegramNotificationSender

class PersonalRouteScanner:
    """
    Independent workflow for scanning Personal Route Watchlists.
    """
    def __init__(
        self,
        personal_route_repo: PersonalRouteRepository,
        scanner_service: ScannerService,
        telegram_sender: TelegramNotificationSender,
        notification_repo: NotificationRepository,
        deal_repo: DealRepository,
        notification_formatter: NotificationFormatter,
        domestic_price_intelligence: DomesticPriceIntelligence
    ):
        self.personal_route_repo = personal_route_repo
        self.scanner_service = scanner_service
        self.telegram_sender = telegram_sender
        self.notification_repo = notification_repo
        self.deal_repo = deal_repo
        self.notification_formatter = notification_formatter
        self.price_intelligence = domestic_price_intelligence

    async def execute(self, departure_dates: list[str] | None = None) -> dict:
        """
        Runs the domestic watchlist scanning workflow.
        """
        start_time = time.perf_counter()
        logger.info("Personal Route Scanner Started")

        # Fallback date if not provided (30 days ahead)
        if not departure_dates:
            departure_dates = [(datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d")]

        # 1. Load all active/enabled routes across all users
        # Group routes by user_id
        routes_by_user = {}
        all_routes = []
        
        # In a real multi-user scenario, we fetch all users, or query the db
        # For simplicity, we query the db manager or list routes for active users
        # Let's get all user_ids that have routes
        conn = self.personal_route_repo.db_manager.get_connection()
        try:
            rows = conn.execute("SELECT DISTINCT user_id FROM personal_routes WHERE enabled = 1;").fetchall()
            user_ids = [r["user_id"] for r in rows]
        finally:
            conn.close()

        for uid in user_ids:
            user_routes = self.personal_route_repo.list_routes(uid)
            enabled_user_routes = [r for r in user_routes if r.enabled]
            if enabled_user_routes:
                routes_by_user[uid] = enabled_user_routes
                all_routes.extend(enabled_user_routes)

        routes_loaded = len(all_routes)
        flights_found = 0
        deals_generated = 0
        notifications_sent = 0

        # Scan for each user
        for user_id, routes in routes_by_user.items():
            user_deals = []
            for route in routes:
                for dep_date in departure_dates:
                    try:
                        flights = await self.scanner_service.search_route(
                            route.origin_airport,
                            route.destination_airport,
                            dep_date,
                            allow_domestic=True
                        )
                        flights_found += len(flights)

                        for flight in flights:
                            band = self.price_intelligence.get_price_band(
                                flight.origin, flight.destination, flight.price
                            )
                            if band in ["excellent", "great", "good"]:
                                score = self.price_intelligence.calculate_score(
                                    flight.origin, flight.destination, flight.price
                                )
                                category = self.price_intelligence.classify_category(
                                    flight.origin, flight.destination, flight.price
                                )
                                recommendation = self.price_intelligence.get_recommendation(
                                    flight.origin, flight.destination, flight.price
                                )
                                avg_price = self.price_intelligence.get_average_price(
                                    flight.origin, flight.destination
                                )

                                # Save deal
                                mapped_cat = f"{category.title()} Deal"
                                deal_entity = Deal(
                                    id=flight.id,
                                    flight=flight,
                                    category=mapped_cat,
                                    discount_percentage=0.0,  # Or compute relative difference
                                    historical_average=Decimal(str(avg_price)),
                                    detected_at=datetime.now(timezone.utc)
                                )
                                self.deal_repo.save(deal_entity)
                                
                                user_deals.append({
                                    "flight": flight,
                                    "category": category,
                                    "score": score
                                })
                                deals_generated += 1

                                # Required logging
                                logger.info(
                                    f"Evaluated Route: {route.origin_airport} -> {route.destination_airport} | "
                                    f"Current Price: {flight.price} | Average Price: {avg_price} | "
                                    f"Route Score: {score} | Category: {category} | Recommendation: {recommendation}"
                                )
                                logger.info(
                                    f"\n{route.origin_airport} → {route.destination_airport}\n"
                                    f"₹{int(flight.price):,}\n"
                                    f"Average ₹{int(avg_price):,}\n"
                                    f"Category: {category}\n"
                                    f"Recommendation:\n"
                                    f"{recommendation}"
                                )

                    except Exception as e:
                        logger.error(f"Error scanning route {route.origin_airport} -> {route.destination_airport}: {e}")

            # Send consolidated watchlist alert
            if user_deals:
                try:
                    message = self.notification_formatter.format_personal_routes_summary(user_deals)
                    notif_id = f"notif_watchlist_{int(time.time())}_{user_id}"
                    notification = Notification(
                        id=notif_id,
                        user_id=user_id,
                        deal_id=user_deals[0]["flight"].id,
                        provider="telegram",
                        status="pending",
                        last_attempt=datetime.now(timezone.utc)
                    )
                    self.notification_repo.save(notification)

                    success = self.telegram_sender.send(
                        notification=notification,
                        message_header=message.subject,
                        message_body=message.body_html
                    )
                    if success:
                        notification.status = "sent"
                        notifications_sent += 1
                    else:
                        notification.status = "failed"
                    self.notification_repo.save(notification)
                except Exception as e:
                    logger.error(f"Failed to send watchlist notification for user {user_id}: {e}")

        duration = time.perf_counter() - start_time
        logger.info(
            f"\nPersonal Route Scanner Started\n"
            f"Routes Loaded: {routes_loaded}\n"
            f"Flights Found: {flights_found}\n"
            f"Deals Generated: {deals_generated}\n"
            f"Notifications Sent: {notifications_sent}\n"
            f"Duration: {duration:.2f} sec"
        )

        return {
            "routes_loaded": routes_loaded,
            "flights_found": flights_found,
            "deals_generated": deals_generated,
            "notifications_sent": notifications_sent,
            "duration_sec": duration
        }
