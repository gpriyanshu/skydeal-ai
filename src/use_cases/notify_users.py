from datetime import datetime, timezone, timedelta

from loguru import logger

from src.domain.entities import Deal, Notification, User
from src.domain.interfaces import NotificationRepository, NotificationSender, UserRepository


class NotifyUsersUseCase:
    """
    Orchestrates the matching of deals to users and dispatches alerts via
    configured notification senders. Enforces deduplication, cooldown, and preference rules.
    """
    def __init__(
        self,
        user_repo: UserRepository,
        notification_repo: NotificationRepository,
        telegram_sender: NotificationSender,
        email_sender: NotificationSender,
        cooldown_seconds: int = 3600
    ):
        self.user_repo = user_repo
        self.notification_repo = notification_repo
        self.telegram_sender = telegram_sender
        self.email_sender = email_sender
        self.cooldown_seconds = cooldown_seconds

        # Simplified airport to country mapping for mock preference verification
        self.airport_countries = {
            "LHR": "United Kingdom",
            "LGW": "United Kingdom",
            "DXB": "United Arab Emirates",
            "SIN": "Singapore",
            "BKK": "Thailand",
            "KUL": "Malaysia",
            "MCT": "Oman",
            "DEL": "India",
            "BOM": "India",
            "BLR": "India",
            "HYD": "India",
            "MAA": "India",
            "CCU": "India",
            "COK": "India",
        }

    def execute(self, deals: list[Deal]) -> None:
        """Evaluates detected deals against active user criteria and dispatches alerts."""
        active_users = self.user_repo.get_all_active()
        
        now = datetime.now(timezone.utc)
        cooldown_since = now - timedelta(seconds=self.cooldown_seconds)

        if active_users:
            for deal in deals:
                # We only notify Great Deal and Super Deal categories as per PROJECT_SPEC.md
                if deal.category not in ["Great Deal", "Super Deal"]:
                    continue

                for user in active_users:
                    if self._matches_preferences(user, deal):
                        self._dispatch_notifications_for_user(user, deal, cooldown_since)
        else:
            default_chat_id = self.telegram_sender.default_chat_id
            if not default_chat_id:
                logger.error(
                    "No registered users found in database and TELEGRAM_DEFAULT_CHAT_ID is missing or empty. "
                    "Telegram notifications cannot be delivered."
                )
                return
            
            for deal in deals:
                # We only notify Great Deal and Super Deal categories as per PROJECT_SPEC.md
                if deal.category not in ["Great Deal", "Super Deal"]:
                    continue
                self._dispatch_default_telegram_notification(default_chat_id, deal, cooldown_since)

    def _matches_preferences(self, user: User, deal: Deal) -> bool:
        flight = deal.flight

        # 1. Budget check
        if user.budget is not None and flight.price > user.budget:
            return False

        # 2. Preferred airports (origin check)
        if user.preferred_airports and flight.origin not in user.preferred_airports:
            return False

        # 3. Preferred countries check
        if user.preferred_countries:
            dest_country = self.airport_countries.get(flight.destination, "Unknown")
            if dest_country not in user.preferred_countries:
                return False

        # 4. Preferred airlines check
        if user.preferred_airlines and flight.airline not in user.preferred_airlines:
            return False

        # 5. Max stops check
        if user.max_stops is not None and flight.stops > user.max_stops:
            return False

        # 6. Max duration check
        if user.max_duration_minutes is not None and flight.duration_minutes > user.max_duration_minutes:
            return False

        # 7. Cabin class check
        if user.cabin_class != flight.cabin_class:
            return False

        return True

    def _dispatch_notifications_for_user(self, user: User, deal: Deal, cooldown_since: datetime) -> None:
        flight = deal.flight
        now = datetime.now(timezone.utc)

        # Check Route Cooldown to prevent spamming
        if self.notification_repo.has_recent_notification_for_route(
            user.id, flight.origin, flight.destination, cooldown_since
        ):
            logger.debug(f"Skipping notification for user {user.id} on route {flight.origin}->{flight.destination} due to cooldown.")
            return

        # 1. Telegram Dispatch
        telegram_notif_id = f"notif_tg_{deal.id}_{user.id}"
        
        # Check Exact Duplicate Notification
        existing_tg = self.notification_repo.get_sent_for_deal_and_user(deal.id, user.id)
        if existing_tg:
            logger.debug(f"Telegram notification already recorded for user {user.id} and deal {deal.id}. Skipping.")
        else:
            tg_notification = Notification(
                id=telegram_notif_id,
                user_id=user.id,
                deal_id=deal.id,
                provider="telegram",
                status="pending",
                last_attempt=now
            )
            self.notification_repo.save(tg_notification)

            tg_header = f"✈️ {deal.category.upper()} DETECTED! ✈️"
            tg_body = (
                f"Route: <b>{flight.origin} ➡️ {flight.destination}</b>\n"
                f"Price: <b>${flight.price}</b> (Saved {deal.discount_percentage}%, Avg: ${deal.historical_average})\n"
                f"Airline: {flight.airline}\n"
                f"Stops: {'Direct' if flight.stops == 0 else f'{flight.stops} layovers'}\n"
                f"Duration: {flight.duration_minutes // 60}h {flight.duration_minutes % 60}m\n"
                f"Departure: {flight.departure_date.strftime('%Y-%m-%d')}\n"
                f"Cabin Class: {flight.cabin_class.title()}\n\n"
                f"👉 <a href='{flight.deep_link}'>Book Flight Now</a>"
            )

            success = self.telegram_sender.send(tg_notification, tg_header, tg_body)
            tg_notification.status = "sent" if success else "failed"
            tg_notification.last_attempt = datetime.now(timezone.utc)
            if not success:
                tg_notification.retry_count = 1
                tg_notification.error_message = "Delivery returned HTTP failure or timed out."
            
            self.notification_repo.save(tg_notification)

        # 2. Email Dispatch (Secondary)
        if user.email:
            email_notif_id = f"notif_em_{deal.id}_{user.id}"
            existing_em = self.notification_repo.get_sent_for_deal_and_user(deal.id, user.email)
            
            if existing_em:
                logger.debug(f"Email notification already sent to {user.email} for deal {deal.id}.")
                return

            em_notification = Notification(
                id=email_notif_id,
                user_id=user.email,
                deal_id=deal.id,
                provider="email",
                status="pending",
                last_attempt=now
            )
            self.notification_repo.save(em_notification)

            em_subject = f"SkyDeal AI Alert: {deal.category} Found - {flight.origin} to {flight.destination} for ${flight.price}"
            em_body = (
                f"Hello,\n\n"
                f"We found an exceptional flight deal on SkyDeal AI:\n\n"
                f"Route: {flight.origin} to {flight.destination}\n"
                f"Price: ${flight.price} (Historical average: ${deal.historical_average})\n"
                f"Airline: {flight.airline}\n"
                f"Stops: {flight.stops}\n"
                f"Departure Date: {flight.departure_date.strftime('%Y-%m-%d')}\n"
                f"Booking Link: {flight.deep_link}\n\n"
                f"Best regards,\nSkyDeal AI System"
            )

            success = self.email_sender.send(em_notification, em_subject, em_body)
            em_notification.status = "sent" if success else "failed"
            em_notification.last_attempt = datetime.now(timezone.utc)
            if not success:
                em_notification.retry_count = 1
                em_notification.error_message = "SMTP delivery error."
            
            self.notification_repo.save(em_notification)

    def _dispatch_default_telegram_notification(self, chat_id: str, deal: Deal, cooldown_since: datetime) -> None:
        flight = deal.flight
        now = datetime.now(timezone.utc)

        # Check Route Cooldown to prevent spamming
        if self.notification_repo.has_recent_notification_for_route(
            chat_id, flight.origin, flight.destination, cooldown_since
        ):
            logger.debug(f"Skipping notification for chat {chat_id} on route {flight.origin}->{flight.destination} due to cooldown.")
            return

        # Telegram Dispatch
        telegram_notif_id = f"notif_tg_{deal.id}_{chat_id}"
        
        # Check Exact Duplicate Notification
        existing_tg = self.notification_repo.get_sent_for_deal_and_user(deal.id, chat_id)
        if existing_tg:
            logger.debug(f"Telegram notification already recorded for chat {chat_id} and deal {deal.id}. Skipping.")
        else:
            tg_notification = Notification(
                id=telegram_notif_id,
                user_id=chat_id,
                deal_id=deal.id,
                provider="telegram",
                status="pending",
                last_attempt=now
            )
            self.notification_repo.save(tg_notification)

            tg_header = f"✈️ {deal.category.upper()} DETECTED! ✈️"
            tg_body = (
                f"Route: <b>{flight.origin} ➡️ {flight.destination}</b>\n"
                f"Price: <b>${flight.price}</b> (Saved {deal.discount_percentage}%, Avg: ${deal.historical_average})\n"
                f"Airline: {flight.airline}\n"
                f"Stops: {'Direct' if flight.stops == 0 else f'{flight.stops} layovers'}\n"
                f"Duration: {flight.duration_minutes // 60}h {flight.duration_minutes % 60}m\n"
                f"Departure: {flight.departure_date.strftime('%Y-%m-%d')}\n"
                f"Cabin Class: {flight.cabin_class.title()}\n\n"
                f"👉 <a href='{flight.deep_link}'>Book Flight Now</a>"
            )

            success = self.telegram_sender.send(tg_notification, tg_header, tg_body)
            tg_notification.status = "sent" if success else "failed"
            tg_notification.last_attempt = datetime.now(timezone.utc)
            if not success:
                tg_notification.retry_count = 1
                tg_notification.error_message = "Delivery returned HTTP failure or timed out."
            
            self.notification_repo.save(tg_notification)
