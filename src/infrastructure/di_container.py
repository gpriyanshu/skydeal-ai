from src.adapters.database.connection import DatabaseManager
from src.adapters.database.repository import (
    SQLiteDealRepository,
    SQLiteNotificationRepository,
    SQLitePriceHistoryRepository,
    SQLiteUserRepository,
    SQLiteTravelGoalRepository,
    SQLitePersonalRouteRepository,
)
from src.domain.travel_goal_parser import TravelGoalParser
from src.domain.personal_route_service import PersonalRouteService
from src.adapters.notifications.email import EmailNotificationSender
from src.adapters.notifications.telegram import TelegramNotificationSender
from src.adapters.telegram_command_handler import TelegramCommandHandler
from src.adapters.providers.mock import MockFlightProvider
from src.adapters.providers.skyscanner import SkyscannerFlightProvider
from src.adapters.providers.travelpayouts import TravelPayoutsProvider
from src.adapters.providers.travelpayouts_client import TravelPayoutsClient
from src.adapters.providers.travelpayouts_mapper import TravelPayoutsResponseMapper
from src.adapters.providers.currency_converter import CurrencyConverter
from src.adapters.scheduler.worker import FlightScanScheduler
from src.config import Settings
from src.domain.deal_engine import DealEngine as DomainDealEngine
from src.domain.interfaces import FlightProvider
from src.domain.notification_formatter import NotificationFormatter
from src.domain.scanner_service import ScannerService
from src.use_cases.detect_deals import DealEngine
from src.use_cases.manage_users import ManageUsersUseCase
from src.use_cases.notification_pipeline import NotificationPipeline
from src.use_cases.notify_users import NotifyUsersUseCase
from src.use_cases.pipeline_scheduler_wrapper import PipelineSchedulerWrapper
from src.use_cases.scan_everywhere import ScanEverywhereUseCase
from src.use_cases.scan_flights import ScanFlightsUseCase
from src.use_cases.scan_route import ScanRouteUseCase
from src.use_cases.travel_goal_service import TravelGoalService


class DIContainer:
    """
    Dependency Injection Container resolving services and binding adapters
    to domain interfaces based on application settings.
    """
    def __init__(self, settings: Settings):
        self.settings = settings

        # Database infrastructure setup
        self.db_manager = DatabaseManager(settings.DB_PATH)

        # Repositories instantiation
        self.user_repo = SQLiteUserRepository(self.db_manager)
        self.price_history_repo = SQLitePriceHistoryRepository(self.db_manager)
        self.deal_repo = SQLiteDealRepository(self.db_manager)
        self.notification_repo = SQLiteNotificationRepository(self.db_manager)
        self.travel_goal_repo = SQLiteTravelGoalRepository(self.db_manager)
        self.travel_goal_parser = TravelGoalParser()
        self.personal_route_repo = SQLitePersonalRouteRepository(self.db_manager)
        self.personal_route_service = PersonalRouteService(self.personal_route_repo)

        # Provider plugin resolution (Skyscanner, TravelPayouts, or Mock)
        # Currency Converter (Sprint 7)
        self.currency_converter = CurrencyConverter(
            fallback_rates=settings.FALLBACK_EXCHANGE_RATES
        )

        # Flight Provider Setup (Sprint 3)
        if settings.FLIGHT_PROVIDER == "skyscanner":
            self.flight_provider = SkyscannerFlightProvider()
        elif settings.FLIGHT_PROVIDER == "travelpayouts":
            self.tp_client = TravelPayoutsClient(self.settings)
            self.tp_mapper = TravelPayoutsResponseMapper(currency_converter=self.currency_converter)
            self.flight_provider = TravelPayoutsProvider(self.tp_client, self.tp_mapper, settings=self.settings)
        else:
            self.flight_provider = MockFlightProvider(settings=self.settings)

        # Notification Senders
        self.telegram_sender = TelegramNotificationSender(
            bot_token=settings.TELEGRAM_BOT_TOKEN,
            default_chat_id=settings.TELEGRAM_DEFAULT_CHAT_ID
        )
        self.email_sender = EmailNotificationSender(
            smtp_host=settings.SMTP_HOST,
            smtp_port=settings.SMTP_PORT,
            smtp_username=settings.SMTP_USERNAME,
            smtp_password=settings.SMTP_PASSWORD,
            smtp_from_email=settings.SMTP_FROM_EMAIL
        )

        # Business Logic Use Cases
        self.manage_users_use_case = ManageUsersUseCase(self.user_repo)
        self.deal_engine = DealEngine(
            price_history_repo=self.price_history_repo,
            deal_repo=self.deal_repo
        )
        self.notify_users_use_case = NotifyUsersUseCase(
            user_repo=self.user_repo,
            notification_repo=self.notification_repo,
            telegram_sender=self.telegram_sender,
            email_sender=self.email_sender,
            cooldown_seconds=settings.TELEGRAM_COOLDOWN_SECONDS
        )
        self.scan_flights_use_case = ScanFlightsUseCase(
            flight_provider=self.flight_provider,
            deal_engine=self.deal_engine,
            notify_users_use_case=self.notify_users_use_case
        )
        self.travel_goal_service = TravelGoalService(self.travel_goal_repo, self.travel_goal_parser)
        
        # Scanner Service and Use Cases (Sprint 3A)
        self.scanner_service = ScannerService(self.flight_provider)
        self.scan_everywhere_use_case = ScanEverywhereUseCase(self.scanner_service)
        self.scan_route_use_case = ScanRouteUseCase(self.scanner_service)

        # Domain Deal Engine (Sprint 4)
        self.domain_deal_engine = DomainDealEngine(
            price_history_repo=self.price_history_repo,
            good_deal_threshold=settings.GOOD_DEAL_THRESHOLD,
            great_deal_threshold=settings.GREAT_DEAL_THRESHOLD,
            super_deal_threshold=settings.SUPER_DEAL_THRESHOLD,
            settings=settings
        )

        # Notification Formatter (Sprint 5A)
        self.notification_formatter = NotificationFormatter()

        # Notification Pipeline (Sprint 6)
        self.notification_pipeline = NotificationPipeline(
            scanner_service=self.scanner_service,
            deal_engine=self.domain_deal_engine,
            notification_formatter=self.notification_formatter,
            telegram_sender=self.telegram_sender,
            user_repo=self.user_repo,
            notification_repo=self.notification_repo,
            deal_repo=self.deal_repo,
            min_notification_category=settings.MIN_NOTIFICATION_CATEGORY,
            cooldown_seconds=settings.TELEGRAM_COOLDOWN_SECONDS,
            scan_origin=settings.SCAN_ORIGIN,
            scan_origins=settings.SCAN_ORIGINS,
            settings=settings,
            travel_goal_repo=self.travel_goal_repo,
            personal_route_repo=self.personal_route_repo
        )

        # Scheduler service
        self.scheduler = FlightScanScheduler(
            scan_use_case=PipelineSchedulerWrapper(self.notification_pipeline),
            interval_hours=settings.SCAN_INTERVAL_HOURS
        )

        # AI Conversational Services (Sprint 16)
        from src.adapters.ai.openai_provider import OpenAIProvider
        from src.adapters.database.conversation_state_repository import InMemoryConversationStateRepository
        from src.domain.conversation_service import ConversationService

        self.ai_provider = OpenAIProvider(
            api_key=settings.OPENAI_API_KEY,
            model_name=settings.MODEL_NAME
        )
        self.conversation_state_repo = InMemoryConversationStateRepository(
            timeout_seconds=settings.CONVERSATION_TIMEOUT
        )
        self.conversation_service = ConversationService(
            conversation_state_repo=self.conversation_state_repo,
            ai_provider=self.ai_provider,
            travel_goal_service=self.travel_goal_service,
            deal_engine=self.deal_engine,
            domain_deal_engine=self.domain_deal_engine,
            scanner_service=self.scanner_service,
            settings=settings,
            personal_route_service=self.personal_route_service
        )
        self.travel_goal_service.set_conversation_service(self.conversation_service)

        self.telegram_command_handler = TelegramCommandHandler(self.travel_goal_service, self.conversation_service)

        # Telegram Bot Updates Listener (Sprint 16 Polling)
        from src.adapters.notifications.telegram_bot_listener import TelegramBotListener
        self.telegram_bot_listener = TelegramBotListener(
            bot_token=settings.TELEGRAM_BOT_TOKEN,
            command_handler=self.telegram_command_handler,
            telegram_sender=self.telegram_sender
        )

    async def close(self) -> None:
        """Closes all underlying resources (e.g. HTTP client connection pools)."""
        if hasattr(self, "tp_client"):
            await self.tp_client.close()
