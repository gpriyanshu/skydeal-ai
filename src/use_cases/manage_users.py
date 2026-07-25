from loguru import logger

from src.domain.entities import User
from src.domain.exceptions import UserNotFoundError
from src.domain.interfaces import UserRepository


class ManageUsersUseCase:
    """
    Handles user onboarding, offboarding, and preference settings updates.
    """
    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo

    def register_user(self, user_id: str, username: str | None = None) -> User:
        """Onboards a user with default settings if they do not exist."""
        user = self.user_repo.get_by_id(user_id)
        if user:
            logger.info(f"User {user_id} already registered. Skipping onboarding.")
            return user
            
        new_user = User(
            id=user_id,
            username=username,
            preferred_countries=[],
            preferred_airports=[],
            preferred_airlines=[],
            budget=None,
            max_stops=None,
            max_duration_minutes=None,
            cabin_class="economy",
            notification_enabled=True
        )
        self.user_repo.save(new_user)
        logger.info(f"Successfully registered new user: {user_id} (@{username or 'N/A'})")
        return new_user

    def update_budget(self, user_id: str, budget: float | None) -> User:
        """Updates the maximum price threshold for a user's deal matching."""
        user = self._get_user_or_raise(user_id)
        user.budget = budget
        self.user_repo.save(user)
        logger.info(f"Updated user {user_id} budget to ${budget}")
        return user

    def update_airports(self, user_id: str, airports: list[str]) -> User:
        """Updates the list of preferred airports (e.g. ['DEL', 'BOM'])."""
        user = self._get_user_or_raise(user_id)
        # Normalize to upper case IATA codes
        user.preferred_airports = [apt.strip().upper() for apt in airports if apt.strip()]
        self.user_repo.save(user)
        logger.info(f"Updated user {user_id} preferred airports to {user.preferred_airports}")
        return user

    def update_countries(self, user_id: str, countries: list[str]) -> User:
        """Updates preferred destination countries."""
        user = self._get_user_or_raise(user_id)
        user.preferred_countries = [c.strip() for c in countries if c.strip()]
        self.user_repo.save(user)
        logger.info(f"Updated user {user_id} preferred countries to {user.preferred_countries}")
        return user

    def update_airlines(self, user_id: str, airlines: list[str]) -> User:
        """Updates preferred airlines list."""
        user = self._get_user_or_raise(user_id)
        user.preferred_airlines = [a.strip() for a in airlines if a.strip()]
        self.user_repo.save(user)
        logger.info(f"Updated user {user_id} preferred airlines to {user.preferred_airlines}")
        return user

    def update_email(self, user_id: str, email: str | None) -> User:
        """Configures or clears secondary email address alerts."""
        user = self._get_user_or_raise(user_id)
        user.email = email.strip() if email else None
        self.user_repo.save(user)
        logger.info(f"Updated user {user_id} email to {user.email}")
        return user

    def set_notifications_enabled(self, user_id: str, enabled: bool) -> User:
        """Toggles subscription alerts for the user."""
        user = self._get_user_or_raise(user_id)
        user.notification_enabled = enabled
        self.user_repo.save(user)
        logger.info(f"Toggled notifications for user {user_id} to {enabled}")
        return user

    def deregister_user(self, user_id: str) -> None:
        """Completely removes a user from the system."""
        self.user_repo.delete(user_id)
        logger.info(f"Deregistered and deleted user {user_id} from database.")

    def get_user_settings(self, user_id: str) -> User | None:
        return self.user_repo.get_by_id(user_id)

    def _get_user_or_raise(self, user_id: str) -> User:
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError(user_id)
        return user
