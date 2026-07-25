from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal

from src.domain.entities import Deal, Flight, Notification, PriceHistory, User, TravelGoal, ConversationState, PersonalRoute


class UserRepository(ABC):
    @abstractmethod
    def save(self, user: User) -> None:
        """Saves a user or updates their settings in the system."""
        pass

    @abstractmethod
    def get_by_id(self, user_id: str) -> User | None:
        """Retrieves a user by their unique ID."""
        pass

    @abstractmethod
    def get_all_active(self) -> list[User]:
        """Retrieves all users who have enabled notifications."""
        pass

    @abstractmethod
    def delete(self, user_id: str) -> None:
        """Deletes a user from the system."""
        pass


class PriceHistoryRepository(ABC):
    @abstractmethod
    def save(self, history: PriceHistory) -> None:
        """Persists the updated price history for a given origin-destination route."""
        pass

    @abstractmethod
    def get(self, origin: str, destination: str) -> PriceHistory | None:
        """Retrieves the price history statistics for a route."""
        pass

    @abstractmethod
    def save_observation(self, origin: str, destination: str, price: Decimal, scanned_at: datetime) -> None:
        """Saves an individual price observation for the route."""
        pass

    @abstractmethod
    def get_observations(self, origin: str, destination: str) -> list[Decimal]:
        """Retrieves all price observations for the route, ordered chronologically."""
        pass


class DealRepository(ABC):
    @abstractmethod
    def save(self, deal: Deal) -> None:
        """Saves a detected deal."""
        pass

    @abstractmethod
    def get_by_id(self, deal_id: str) -> Deal | None:
        """Retrieves a deal by its unique ID."""
        pass

    @abstractmethod
    def get_recent_deals(self, limit: int = 10) -> list[Deal]:
        """Retrieves the most recently detected deals."""
        pass


class NotificationRepository(ABC):
    @abstractmethod
    def save(self, notification: Notification) -> None:
        """Persists a notification log/status."""
        pass

    @abstractmethod
    def get_pending(self) -> list[Notification]:
        """Retrieves all pending notifications."""
        pass

    @abstractmethod
    def get_sent_for_deal_and_user(self, deal_id: str, user_id: str) -> Notification | None:
        """Gets matching sent/failed notification to prevent duplicate sends."""
        pass

    @abstractmethod
    def has_recent_notification_for_route(
        self, user_id: str, origin: str, destination: str, since: datetime
    ) -> bool:
        """Checks if a notification was already sent to the user for this route since the specified timestamp."""
        pass

    @abstractmethod
    def get_last_sent_deal_for_route(
        self, user_id: str, origin: str, destination: str, goal_id: str | None = None
    ) -> Deal | None:
        """Retrieves the last sent deal for a specific user and route."""
        pass


class FlightProvider(ABC):
    @abstractmethod
    def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: str | None = None
    ) -> list[Flight]:
        """Queries the provider database for flights and returns normalized domain Flight models."""
        pass

    @abstractmethod
    def search_airports(self, query: str) -> list[str]:
        """Finds matching airport codes for a query search (e.g. 'London' -> ['LHR', 'LGW'])."""
        pass


class NotificationSender(ABC):
    @abstractmethod
    def send(self, notification: Notification, message_header: str, message_body: str) -> bool:
        """Sends the notification payload via the channel. Returns True if successful."""
        pass


class TravelGoalRepository(ABC):
    @abstractmethod
    def create_goal(self, goal: TravelGoal) -> TravelGoal:
        """Saves a new travel goal in the system."""
        pass

    @abstractmethod
    def update_goal(self, goal: TravelGoal) -> TravelGoal:
        """Updates an existing travel goal."""
        pass

    @abstractmethod
    def delete_goal(self, goal_id: str) -> bool:
        """Deletes a travel goal from the system."""
        pass

    @abstractmethod
    def list_goals(self, user_id: str) -> list[TravelGoal]:
        """Lists all travel goals (both ACTIVE and PAUSED) for a user."""
        pass

    @abstractmethod
    def get_active_goals(self, user_id: str) -> list[TravelGoal]:
        """Gets all ACTIVE travel goals for a user."""
        pass


class AIProvider(ABC):
    @abstractmethod
    def generate_chat_response(self, messages: list[dict[str, str]], temperature: float = 0.7) -> str:
        """Generates a text completion/response from the LLM given message history."""
        pass

    @abstractmethod
    def generate_structured_response(
        self, messages: list[dict[str, str]], response_format: type, temperature: float = 0.0
    ):
        """Generates structured output (using Pydantic model format) from the LLM."""
        pass


class ConversationStateRepository(ABC):
    @abstractmethod
    def save(self, state: ConversationState) -> None:
        """Saves or updates the conversation state for a user."""
        pass

    @abstractmethod
    def get(self, user_id: str) -> ConversationState | None:
        """Retrieves the conversation state for a user."""
        pass

    @abstractmethod
    def delete(self, user_id: str) -> None:
        """Removes the conversation state for a user."""
        pass


class PersonalRouteRepository(ABC):
    @abstractmethod
    def save(self, route: PersonalRoute) -> None:
        """Saves a personal route or updates its settings."""
        pass

    @abstractmethod
    def get_by_id(self, route_id: str) -> PersonalRoute | None:
        """Retrieves a personal route by its unique ID."""
        pass

    @abstractmethod
    def get_by_route(self, user_id: str, origin: str, destination: str) -> PersonalRoute | None:
        """Retrieves a personal route for a user by origin and destination."""
        pass

    @abstractmethod
    def list_routes(self, user_id: str) -> list[PersonalRoute]:
        """Lists all personal routes for a user."""
        pass

    @abstractmethod
    def delete(self, route_id: str) -> None:
        """Deletes a personal route from the system."""
        pass

