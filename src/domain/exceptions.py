class DomainError(Exception):
    """Base exception for all domain-specific errors."""
    pass


class UserNotFoundError(DomainError):
    """Raised when a user is not found in the repository."""
    def __init__(self, user_id: str):
        super().__init__(f"User with ID {user_id} was not found.")
        self.user_id = user_id


class ProviderError(DomainError):
    """Raised when an external flight provider fails."""
    pass


class NotificationError(DomainError):
    """Raised when notification delivery fails."""
    pass


class DatabaseError(DomainError):
    """Raised when database operations fail."""
    pass


class DealDetectionError(DomainError):
    """Raised when deal engine calculations encounter invalid inputs."""
    pass
