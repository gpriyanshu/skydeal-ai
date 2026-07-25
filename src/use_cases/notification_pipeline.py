from datetime import datetime, timezone, timedelta
from typing import Literal

from loguru import logger

from src.adapters.notifications.telegram import TelegramNotificationSender
from src.domain.deal_engine import DealEngine as DomainDealEngine
from src.domain.entities import Deal, Notification, User, TravelGoal
from src.domain.interfaces import DealRepository, NotificationRepository, UserRepository, TravelGoalRepository, PersonalRouteRepository
from src.domain.notification_formatter import NotificationFormatter
from src.domain.scanner_service import ScannerService


class NotificationPipeline:
    """
    Orchestrates the scheduled end-to-end flight scanning and deal alerting pipeline:
    ScannerService -> DealEngine -> NotificationFormatter -> TelegramNotificationSender.
    """
    def __init__(
        self,
        scanner_service: ScannerService,
        deal_engine: DomainDealEngine,
        notification_formatter: NotificationFormatter,
        telegram_sender: TelegramNotificationSender,
        user_repo: UserRepository,
        notification_repo: NotificationRepository,
        deal_repo: DealRepository,
        min_notification_category: Literal["NORMAL", "GOOD", "GREAT", "SUPER"] = "GOOD",
        cooldown_seconds: int = 3600,
        scan_origin: str = "DEL",
        scan_origins: list[str] | None = None,
        settings = None,
        travel_goal_repo: TravelGoalRepository | None = None,
        personal_route_repo: PersonalRouteRepository | None = None
    ):
        self.scanner_service = scanner_service
        self.deal_engine = deal_engine
        self.notification_formatter = notification_formatter
        self.telegram_sender = telegram_sender
        self.user_repo = user_repo
        self.notification_repo = notification_repo
        self.deal_repo = deal_repo
        self.min_notification_category = min_notification_category
        self.cooldown_seconds = cooldown_seconds
        self.scan_origin = scan_origin
        self.scan_origins = scan_origins or [scan_origin]
        self.settings = settings
        self.travel_goal_repo = travel_goal_repo
        self.personal_route_repo = personal_route_repo

    async def execute(self) -> None:
        """
        Executes the Hybrid Travel Intelligence Engine:
        Workflow 1: Daily Scanner (Configuration-Driven Everywhere Scan)
        Workflow 2: Travel Goal Scanner (User-Driven Goal Scan)
        Workflow 3: Personal Route Scanner (Domestic Route Watchlist Scan)
        """
        start_time = datetime.now(timezone.utc)
        logger.info("Daily Scanner Started")

        try:
            # 1. Fetch active users
            try:
                active_users = self.user_repo.get_all_active()
            except Exception as e:
                logger.error(f"Database failure loading active users: {e}")
                active_users = []

            # If no users are registered, but a default chat ID is set, create a default user
            if not active_users:
                default_chat_id = self.telegram_sender.default_chat_id
                if default_chat_id:
                    default_user = self.user_repo.get_by_id(default_chat_id)
                    if not default_user:
                        default_user = User(
                            id=default_chat_id,
                            username="Default User",
                            notification_enabled=True,
                            baseline_sent=False
                        )
                        try:
                            self.user_repo.save(default_user)
                        except Exception as e:
                            logger.error(f"Database failure saving default user: {e}")
                    active_users = [default_user]

            if not active_users:
                logger.error(
                    "No registered users found in database and TELEGRAM_DEFAULT_CHAT_ID is missing or empty. "
                    "Telegram notifications cannot be delivered."
                )
                return

            # Fetch raw flights from configured origins bypassing provider filters
            old_allowed = None
            old_budgets = None
            old_max_days = None
            if self.settings:
                old_allowed = getattr(self.settings, "ALLOWED_DESTINATION_COUNTRIES", None)
                old_budgets = getattr(self.settings, "COUNTRY_MAX_BUDGETS", None)
                old_max_days = getattr(self.settings, "MAX_DAYS_AHEAD", None)
                try:
                    self.settings.ALLOWED_DESTINATION_COUNTRIES = []
                    self.settings.COUNTRY_MAX_BUDGETS = {}
                    self.settings.MAX_DAYS_AHEAD = 99999
                except Exception:
                    pass

            raw_flights = []
            try:
                origins = self.scan_origins if self.scan_origins else [self.scan_origin]
                if len(origins) == 1:
                    raw_flights = await self.scanner_service.search_everywhere(origins[0])
                else:
                    raw_flights = await self.scanner_service.search_everywhere(origins)
            except Exception as e:
                logger.error(f"Provider failure (ScannerService failed): {e}")
                return
            finally:
                if self.settings:
                    try:
                        if old_allowed is not None:
                            self.settings.ALLOWED_DESTINATION_COUNTRIES = old_allowed
                        if old_budgets is not None:
                            self.settings.COUNTRY_MAX_BUDGETS = old_budgets
                        if old_max_days is not None:
                            self.settings.MAX_DAYS_AHEAD = old_max_days
                    except Exception:
                        pass

            logger.info(f"Daily Scanner retrieved raw flights: {len(raw_flights)}")

            # ====================================================
            # WORKFLOW 1: DAILY SCANNER (Configuration-Driven)
            # ====================================================
            from src.adapters.providers.constants import AIRPORT_TO_COUNTRY

            # Apply legacy filters manually (Sprint 20: default to DEFAULT_ALERT_REGION)
            legacy_flights = []
            region_countries = getattr(self.settings, "DEFAULT_ALERT_REGION", None)
            if region_countries is None:
                region_countries = getattr(self.settings, "ALLOWED_DESTINATION_COUNTRIES", [])
            if isinstance(region_countries, str):
                region_countries = [c.strip() for c in region_countries.split(",") if c.strip()]
            allowed_countries = [c.lower() for c in region_countries if c]
            country_budgets = {k.lower(): v for k, v in getattr(self.settings, "COUNTRY_MAX_BUDGETS", {}).items()}
            max_days = getattr(self.settings, "MAX_DAYS_AHEAD", None)

            for f in raw_flights:
                dest_country = AIRPORT_TO_COUNTRY.get(f.destination.upper(), "Unknown")
                if allowed_countries and dest_country.lower() not in allowed_countries:
                    continue

                budget = country_budgets.get(dest_country.lower())
                if budget is not None and f.price > budget:
                    continue

                if max_days is not None:
                    dep_date = f.departure_date
                    if dep_date.tzinfo is None:
                        dep_date = dep_date.replace(tzinfo=timezone.utc)
                    days_diff = (dep_date - start_time).days
                    if days_diff > max_days:
                        continue

                legacy_flights.append(f)

            logger.info(f"Daily Scanner filtered flights: {len(legacy_flights)}")

            # Calculate scan duplicates for logging
            unique_keys = set()
            scan_duplicates = 0
            for f in legacy_flights:
                key = (f.origin.upper(), f.destination.upper(), f.departure_date.isoformat(), f.price)
                if key in unique_keys:
                    scan_duplicates += 1
                else:
                    unique_keys.add(key)

            # Initialize metrics for Deal Summary log
            normal_count = 0
            good_count = 0
            great_count = 0
            super_count = 0
            selected_count = 0
            cooldown_skipped_count = 0
            duplicate_skipped_count = scan_duplicates

            # Process legacy flights through DealEngine
            try:
                legacy_deal_results = self.deal_engine.process_flights(legacy_flights)
            except Exception as e:
                logger.error(f"DealEngine failure in Workflow 1: {e}")
                legacy_deal_results = []

            # Filter legacy deals by category
            categories = ["NORMAL", "GOOD", "GREAT", "SUPER"]
            try:
                min_idx = categories.index(self.min_notification_category.upper())
            except ValueError:
                min_idx = categories.index("GOOD")

            qualifying_legacy_deals = [
                d for d in legacy_deal_results
                if categories.index(d.deal_category.upper()) >= min_idx
            ]

            # Sprint 20 scheduled scan logs
            from src.destination_regions import ASIA, MIDDLE_EAST, EUROPE
            countries = getattr(self.settings, "DEFAULT_ALERT_REGION", [])
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

            logger.info("Automatic Deal Scan")
            logger.info(f"Region: {region_name}")
            logger.info(f"Countries scanned: {len(countries)}")
            logger.info(f"Flights collected: {len(legacy_flights)}")
            logger.info(f"Deals generated: {len(qualifying_legacy_deals)}")

            daily_messages_sent = 0
            daily_messages_skipped = 0

            for user in active_users:
                recipient_id = user.id

                # Baseline check for legacy scanner
                if not user.baseline_sent:
                    cheapest_deals = sorted(legacy_deal_results, key=lambda x: x.current_price)[:10]
                    if not cheapest_deals:
                        logger.info(f"No legacy flights to initialize baseline for user {recipient_id}.")
                        continue

                    logger.info(f"Generating Initial Baseline Notification for user {recipient_id}.")
                    selected_count += len(cheapest_deals)
                    try:
                        message = self.notification_formatter.format_baseline(cheapest_deals)
                    except Exception as e:
                        logger.error(f"Baseline formatter failure: {e}")
                        continue

                    # Save deal records
                    for deal in cheapest_deals:
                        category_mapping = {
                            "NORMAL": "Normal", "GOOD": "Good Deal", "GREAT": "Great Deal", "SUPER": "Super Deal"
                        }
                        mapped_category = category_mapping.get(deal.deal_category.upper(), "Normal")
                        deal_entity = Deal(
                            id=deal.flight.id, flight=deal.flight, category=mapped_category,
                            discount_percentage=deal.percentage_below_average,
                            historical_average=deal.historical_stats.rolling_average, detected_at=start_time
                        )
                        try:
                            self.deal_repo.save(deal_entity)
                        except Exception as e:
                            logger.error(f"Database failure saving deal: {e}")

                    summary_notif_id = f"notif_baseline_{int(start_time.timestamp())}_{recipient_id}"
                    summary_notif = Notification(
                        id=summary_notif_id, user_id=recipient_id, deal_id=cheapest_deals[0].flight.id,
                        provider="telegram", status="pending", last_attempt=start_time
                    )
                    try:
                        self.notification_repo.save(summary_notif)
                    except Exception as e:
                        logger.error(f"Database failure saving notification: {e}")

                    try:
                        success = self.telegram_sender.send(
                            notification=summary_notif, message_header=message.subject, message_body=message.body_html
                        )
                        status_str = "sent" if success else "failed"
                        if success:
                            daily_messages_sent += 1
                            summary_notif.status = "sent"
                            user.baseline_sent = True
                            try:
                                self.user_repo.save(user)
                            except Exception as e:
                                logger.error(f"Database failure updating user: {e}")
                        else:
                            summary_notif.status = "failed"
                        try:
                            self.notification_repo.save(summary_notif)
                        except Exception as e:
                            logger.error(f"Database failure updating notification: {e}")

                        # Save details per sent deal
                        for deal in cheapest_deals:
                            notif_log_id = f"notif_{deal.flight.id}_{int(start_time.timestamp())}_{recipient_id}"
                            notif_log = Notification(
                                id=notif_log_id, user_id=recipient_id, deal_id=deal.flight.id,
                                provider="telegram", status=status_str, last_attempt=start_time
                            )
                            try:
                                self.notification_repo.save(notif_log)
                            except Exception as e:
                                logger.error(f"Database failure saving notification log: {e}")
                    except Exception as e:
                        logger.error(f"Telegram failure sending baseline: {e}")
                        summary_notif.status = "failed"
                        summary_notif.error_message = str(e)
                        try:
                            self.notification_repo.save(summary_notif)
                        except Exception as re:
                            logger.error(f"Database failure saving failed baseline summary: {re}")
                            
                        for deal in cheapest_deals:
                            notif_log_id = f"notif_{deal.flight.id}_{int(start_time.timestamp())}_{recipient_id}"
                            notif_log = Notification(
                                id=notif_log_id, user_id=recipient_id, deal_id=deal.flight.id,
                                provider="telegram", status="failed", last_attempt=start_time,
                                error_message=str(e)
                            )
                            try:
                                self.notification_repo.save(notif_log)
                            except Exception as re:
                                logger.error(f"Database failure saving failed notification log: {re}")
                    continue

                # Normal legacy daily scanning cooldown & duplicate logic (goal_id=None)
                cooldown_since = start_time - timedelta(seconds=self.cooldown_seconds)
                eligible_deals = []
                for deal in qualifying_legacy_deals:
                    try:
                        last_sent = self.notification_repo.get_last_sent_deal_for_route(
                            recipient_id, deal.flight.origin, deal.flight.destination
                        )
                    except Exception as e:
                        logger.error(f"Database failure checking notification history: {e}")
                        last_sent = None

                    if last_sent is None:
                        eligible_deals.append(deal)
                    else:
                        last_sent_detected = last_sent.detected_at
                        if last_sent_detected.tzinfo is None:
                            last_sent_detected = last_sent_detected.replace(tzinfo=timezone.utc)
                        cooldown_expired = last_sent_detected < cooldown_since
                        price_changed = deal.flight.price != last_sent.flight.price
                        last_sent_score = max(0.0, round(float(last_sent.discount_percentage), 2))
                        score_improved = deal.deal_score > last_sent_score

                        if cooldown_expired or price_changed or score_improved:
                            eligible_deals.append(deal)
                        else:
                            daily_messages_skipped += 1
                            cooldown_skipped_count += 1
                            if not price_changed:
                                duplicate_skipped_count += 1

                if not eligible_deals:
                    continue

                # Sort and select best legacy deals (max 2 per country, up to MAX_DEALS_PER_SCAN)
                eligible_deals.sort(
                    key=lambda x: (-float(x.deal_score), -float(x.percentage_below_average), float(x.current_price))
                )

                selected = []
                country_counts = {}
                remaining_pool = []
                for deal in eligible_deals:
                    dest_iata = deal.flight.destination.upper()
                    country = AIRPORT_TO_COUNTRY.get(dest_iata, "Unknown")
                    count = country_counts.get(country, 0)
                    if count < 2:
                        selected.append(deal)
                        country_counts[country] = count + 1
                    else:
                        remaining_pool.append(deal)

                max_deals = getattr(self.settings, "MAX_DEALS_PER_SCAN", 10)
                if len(selected) < max_deals and remaining_pool:
                    needed = max_deals - len(selected)
                    selected.extend(remaining_pool[:needed])
                selected = selected[:max_deals]
                selected_count += len(selected)

                selected.sort(
                    key=lambda x: (-float(x.deal_score), -float(x.percentage_below_average), float(x.current_price))
                )

                if not selected:
                    continue

                try:
                    message = self.notification_formatter.format_summary(selected)
                except Exception as e:
                    logger.error(f"Summary formatter failure: {e}")
                    continue

                # Save Deal entities
                for deal in selected:
                    category_mapping = {
                        "NORMAL": "Normal", "GOOD": "Good Deal", "GREAT": "Great Deal", "SUPER": "Super Deal"
                    }
                    mapped_category = category_mapping.get(deal.deal_category.upper(), "Normal")
                    deal_entity = Deal(
                        id=deal.flight.id, flight=deal.flight, category=mapped_category,
                        discount_percentage=deal.percentage_below_average,
                        historical_average=deal.historical_stats.rolling_average, detected_at=start_time
                    )
                    try:
                        self.deal_repo.save(deal_entity)
                    except Exception as e:
                        logger.error(f"Database failure saving deal: {e}")

                summary_notif_id = f"notif_summary_{int(start_time.timestamp())}_{recipient_id}"
                summary_notif = Notification(
                    id=summary_notif_id, user_id=recipient_id, deal_id=selected[0].flight.id,
                    provider="telegram", status="pending", last_attempt=start_time
                )
                try:
                    self.notification_repo.save(summary_notif)
                except Exception as e:
                    logger.error(f"Database failure saving notification: {e}")

                try:
                    success = self.telegram_sender.send(
                        notification=summary_notif, message_header=message.subject, message_body=message.body_html
                    )
                    status_str = "sent" if success else "failed"
                    if success:
                        daily_messages_sent += 1
                        summary_notif.status = "sent"
                    else:
                        summary_notif.status = "failed"
                    try:
                        self.notification_repo.save(summary_notif)
                    except Exception as e:
                        logger.error(f"Database failure updating notification: {e}")

                    for deal in selected:
                        notif_log_id = f"notif_{deal.flight.id}_{int(start_time.timestamp())}_{recipient_id}"
                        notif_log = Notification(
                            id=notif_log_id, user_id=recipient_id, deal_id=deal.flight.id,
                            provider="telegram", status=status_str, last_attempt=start_time
                        )
                        try:
                            self.notification_repo.save(notif_log)
                        except Exception as e:
                            logger.error(f"Database failure saving notification log: {e}")
                except Exception as e:
                    logger.error(f"Telegram failure sending summary: {e}")
                    summary_notif.status = "failed"
                    summary_notif.error_message = str(e)
                    try:
                        self.notification_repo.save(summary_notif)
                    except Exception as re:
                        logger.error(f"Database failure saving failed summary: {re}")
                        
                    for deal in selected:
                        notif_log_id = f"notif_{deal.flight.id}_{int(start_time.timestamp())}_{recipient_id}"
                        notif_log = Notification(
                            id=notif_log_id, user_id=recipient_id, deal_id=deal.flight.id,
                            provider="telegram", status="failed", last_attempt=start_time,
                            error_message=str(e)
                        )
                        try:
                            self.notification_repo.save(notif_log)
                        except Exception as re:
                            logger.error(f"Database failure saving failed notification log: {re}")

            # Populate category counts
            for d in legacy_deal_results:
                cat = d.deal_category.upper()
                if cat == "SUPER":
                    super_count += 1
                elif cat == "GREAT":
                    great_count += 1
                elif cat == "GOOD":
                    good_count += 1
                else:
                    normal_count += 1

            # Log summary
            logger.info(
                f"Deal Summary\n"
                f"NORMAL : {normal_count}\n"
                f"GOOD : {good_count}\n"
                f"GREAT : {great_count}\n"
                f"SUPER : {super_count}\n"
                f"Selected : {selected_count}\n"
                f"Cooldown Skipped : {cooldown_skipped_count}\n"
                f"Duplicate Skipped : {duplicate_skipped_count}"
            )

            logger.info("Daily Scanner Finished")

            # ====================================================
            # WORKFLOW 2: TRAVEL GOALS SCANNER (User-Driven)
            # ====================================================
            # Load active travel goals for all users
            all_active_goals = []
            goals_by_user = {}
            if self.travel_goal_repo:
                for user in active_users:
                    try:
                        user_goals = self.travel_goal_repo.get_active_goals(user.id)
                        all_active_goals.extend(user_goals)
                        goals_by_user[user.id] = user_goals
                    except Exception as e:
                        logger.error(f"Error loading goals for user {user.id}: {e}")

            logger.info(f"Active Goals Loaded: {len(all_active_goals)}")

            # Process goals
            deal_results_cache = {}
            goal_messages_sent = 0

            for user in active_users:
                recipient_id = user.id
                user_goals = goals_by_user.get(recipient_id, [])

                for goal in user_goals:
                    logger.info(f"Processing Goal:\n{goal.country}")
                    try:
                        cache_key = (goal.country.lower(), goal.start_date.date(), goal.end_date.date(), goal.budget_inr)

                        if cache_key in deal_results_cache:
                            goal_deal_results = deal_results_cache[cache_key]
                        else:
                            # Filter raw_flights by destination country, travel window, and budget
                            matching_flights = []
                            for f in raw_flights:
                                dest_country = AIRPORT_TO_COUNTRY.get(f.destination.upper(), "Unknown")
                                if dest_country.lower() != goal.country.lower():
                                    continue

                                dep_date = f.departure_date
                                if dep_date.tzinfo is None:
                                    dep_date = dep_date.replace(tzinfo=timezone.utc)
                                if not (goal.start_date <= dep_date <= goal.end_date):
                                    continue

                                if goal.budget_inr > 0 and f.price > goal.budget_inr:
                                    continue

                                matching_flights.append(f)

                            logger.info(f"Flights Matched: {len(matching_flights)}")

                            if matching_flights:
                                goal_deal_results = self.deal_engine.process_flights(matching_flights)
                            else:
                                goal_deal_results = []
                            deal_results_cache[cache_key] = goal_deal_results

                        if not goal_deal_results:
                            continue

                        # Filter by Min Notification Category
                        qualifying_goal_deals = [
                            d for d in goal_deal_results
                            if categories.index(d.deal_category.upper()) >= min_idx
                        ]

                        if not qualifying_goal_deals:
                            continue

                        # Cooldown & Duplicate detection for this goal (isolated by goal_id!)
                        cooldown_since = start_time - timedelta(seconds=self.cooldown_seconds)
                        eligible_goal_deals = []
                        for deal in qualifying_goal_deals:
                            try:
                                last_sent = self.notification_repo.get_last_sent_deal_for_route(
                                    recipient_id, deal.flight.origin, deal.flight.destination, goal.id
                                )
                            except Exception as e:
                                logger.error(f"Database failure checking goal notification history: {e}")
                                last_sent = None

                            if last_sent is None:
                                eligible_goal_deals.append(deal)
                            else:
                                last_sent_detected = last_sent.detected_at
                                if last_sent_detected.tzinfo is None:
                                    last_sent_detected = last_sent_detected.replace(tzinfo=timezone.utc)
                                cooldown_expired = last_sent_detected < cooldown_since
                                price_changed = deal.flight.price != last_sent.flight.price
                                last_sent_score = max(0.0, round(float(last_sent.discount_percentage), 2))
                                score_improved = deal.deal_score > last_sent_score

                                if cooldown_expired or price_changed or score_improved:
                                    eligible_goal_deals.append(deal)

                        if not eligible_goal_deals:
                            continue

                        # Sort and limit to MAX_DEALS_PER_SCAN
                        eligible_goal_deals.sort(
                            key=lambda x: (-float(x.deal_score), -float(x.percentage_below_average), float(x.current_price))
                        )
                        max_deals = getattr(self.settings, "MAX_DEALS_PER_SCAN", 10)
                        eligible_goal_deals = eligible_goal_deals[:max_deals]

                        # Fetch old prices from last sent route notification (Sprint 19)
                        old_prices = {}
                        for d in eligible_goal_deals:
                            try:
                                last_sent = self.notification_repo.get_last_sent_deal_for_route(
                                    recipient_id, d.flight.origin, d.flight.destination, goal.id
                                )
                                if last_sent:
                                    old_prices[d.flight.id] = last_sent.flight.price
                            except Exception:
                                pass

                        # Format goal notification
                        try:
                            message = self.notification_formatter.format_goal_summary(goal, eligible_goal_deals, old_prices)
                        except Exception as e:
                            logger.error(f"Goal formatter failure: {e}")
                            continue

                        # Save Deal entities
                        for deal in eligible_goal_deals:
                            category_mapping = {
                                "NORMAL": "Normal", "GOOD": "Good Deal", "GREAT": "Great Deal", "SUPER": "Super Deal"
                            }
                            mapped_category = category_mapping.get(deal.deal_category.upper(), "Normal")
                            deal_entity = Deal(
                                id=deal.flight.id, flight=deal.flight, category=mapped_category,
                                discount_percentage=deal.percentage_below_average,
                                historical_average=deal.historical_stats.rolling_average, detected_at=start_time
                            )
                            try:
                                self.deal_repo.save(deal_entity)
                            except Exception as e:
                                logger.error(f"Database failure saving goal deal: {e}")

                        # Save Goal Notification Log
                        summary_notif_id = f"notif_goal_{goal.id}_{int(start_time.timestamp())}_{recipient_id}"
                        summary_notif = Notification(
                            id=summary_notif_id, user_id=recipient_id, deal_id=eligible_goal_deals[0].flight.id,
                            provider="telegram", status="pending", last_attempt=start_time
                        )
                        try:
                            self.notification_repo.save(summary_notif)
                        except Exception as e:
                            logger.error(f"Database failure saving goal notification: {e}")

                        # Send Telegram Notification
                        try:
                            success = self.telegram_sender.send(
                                notification=summary_notif, message_header=message.subject, message_body=message.body_html
                            )
                            status_str = "sent" if success else "failed"
                            if success:
                                goal_messages_sent += 1
                                summary_notif.status = "sent"
                                logger.info("Goal Notification Sent")
                            else:
                                summary_notif.status = "failed"

                            try:
                                self.notification_repo.save(summary_notif)
                            except Exception as e:
                                logger.error(f"Database failure updating goal notification: {e}")

                            # Replicate logs for sent deals
                            for deal in eligible_goal_deals:
                                notif_log_id = f"notif_{deal.flight.id}_{int(start_time.timestamp())}_{recipient_id}"
                                notif_log = Notification(
                                    id=notif_log_id, user_id=recipient_id, deal_id=deal.flight.id,
                                    provider="telegram", status=status_str, last_attempt=start_time
                                )
                                try:
                                    self.notification_repo.save(notif_log)
                                except Exception as e:
                                    logger.error(f"Database failure saving goal notification log: {e}")
                        except Exception as e:
                            logger.error(f"Telegram failure sending goal notification: {e}")

                    except Exception as e:
                        logger.error(f"Error processing goal {goal.id} for user {recipient_id}: {e}")
                        continue

            # ====================================================
            # WORKFLOW 3: PERSONAL ROUTE WATCHLIST (Domestic Watchlist)
            # ====================================================
            if self.personal_route_repo:
                from src.domain.domestic_price_intelligence import DomesticPriceIntelligence
                from src.use_cases.personal_route_scanner import PersonalRouteScanner
                
                dom_intel = DomesticPriceIntelligence(self.settings)
                route_scanner = PersonalRouteScanner(
                    personal_route_repo=self.personal_route_repo,
                    scanner_service=self.scanner_service,
                    telegram_sender=self.telegram_sender,
                    notification_repo=self.notification_repo,
                    deal_repo=self.deal_repo,
                    notification_formatter=self.notification_formatter,
                    domestic_price_intelligence=dom_intel
                )
                try:
                    await route_scanner.execute()
                except Exception as e:
                    logger.error(f"Error executing Personal Route Watchlist scanner: {e}")

            logger.info("Hybrid Pipeline Finished")

        except Exception as e:
            logger.error(f"Unhandled error in Hybrid Pipeline: {e}")
