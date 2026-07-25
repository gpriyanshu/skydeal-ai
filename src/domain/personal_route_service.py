import uuid
from datetime import datetime, timezone
from src.domain.entities import PersonalRoute
from src.domain.interfaces import PersonalRouteRepository
from src.adapters.providers.constants import INDIAN_AIRPORTS, AIRPORT_TO_COUNTRY

class PersonalRouteService:
    """
    Service responsible for managing Personal Route Watchlists.
    Supports CRUD operations, duplicate prevention, and airport code validation.
    """
    def __init__(self, repository: PersonalRouteRepository):
        self.repository = repository

    def add_route(self, user_id: str, origin: str, destination: str) -> PersonalRoute:
        """
        Validates codes, checks for duplicates, and adds a new personal route.
        """
        origin_code = origin.strip().upper()
        destination_code = destination.strip().upper()

        # Validate airport codes
        if not self._is_valid_airport(origin_code):
            raise ValueError(f"Invalid origin airport code: {origin_code}")
        if not self._is_valid_airport(destination_code):
            raise ValueError(f"Invalid destination airport code: {destination_code}")

        if origin_code == destination_code:
            raise ValueError("Origin and destination airports cannot be the same.")

        # Check for existing route
        existing = self.repository.get_by_route(user_id, origin_code, destination_code)
        if existing:
            # If exists but disabled, enable it
            if not existing.enabled:
                existing.enabled = True
                existing.updated_at = datetime.now(timezone.utc)
                self.repository.save(existing)
            return existing

        # Create new route
        new_route = PersonalRoute(
            id=str(uuid.uuid4()),
            user_id=user_id,
            origin_airport=origin_code,
            destination_airport=destination_code,
            enabled=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        self.repository.save(new_route)
        return new_route

    def remove_route(self, user_id: str, origin: str, destination: str) -> bool:
        """
        Removes a personal route. Returns True if successfully deleted.
        """
        origin_code = origin.strip().upper()
        destination_code = destination.strip().upper()
        
        existing = self.repository.get_by_route(user_id, origin_code, destination_code)
        if not existing:
            return False
            
        self.repository.delete(existing.id)
        return True

    def enable_route(self, user_id: str, origin: str, destination: str) -> bool:
        """
        Enables an existing route. Returns True if state changed.
        """
        origin_code = origin.strip().upper()
        destination_code = destination.strip().upper()
        
        existing = self.repository.get_by_route(user_id, origin_code, destination_code)
        if not existing:
            return False
            
        if not existing.enabled:
            existing.enabled = True
            existing.updated_at = datetime.now(timezone.utc)
            self.repository.save(existing)
            return True
        return False

    def disable_route(self, user_id: str, origin: str, destination: str) -> bool:
        """
        Disables an existing route. Returns True if state changed.
        """
        origin_code = origin.strip().upper()
        destination_code = destination.strip().upper()
        
        existing = self.repository.get_by_route(user_id, origin_code, destination_code)
        if not existing:
            return False
            
        if existing.enabled:
            existing.enabled = False
            existing.updated_at = datetime.now(timezone.utc)
            self.repository.save(existing)
            return True
        return False

    def list_routes(self, user_id: str) -> list[PersonalRoute]:
        """
        Lists all routes (enabled and disabled) for a user.
        """
        return self.repository.list_routes(user_id)

    def _is_valid_airport(self, code: str) -> bool:
        return code in INDIAN_AIRPORTS or code in AIRPORT_TO_COUNTRY
