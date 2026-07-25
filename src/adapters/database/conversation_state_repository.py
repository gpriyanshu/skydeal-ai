from datetime import datetime, timezone
from src.domain.entities import ConversationState
from src.domain.interfaces import ConversationStateRepository

class InMemoryConversationStateRepository(ConversationStateRepository):
    def __init__(self, timeout_seconds: int = 900):
        self.timeout_seconds = timeout_seconds
        self.states: dict[str, ConversationState] = {}

    def save(self, state: ConversationState) -> None:
        """
        Saves or updates the conversation state for a user.
        """
        state.last_updated_at = datetime.now(timezone.utc)
        self.states[state.user_id] = state

    def get(self, user_id: str) -> ConversationState | None:
        """
        Retrieves the state, automatically expiring it if the timeout has passed.
        """
        state = self.states.get(user_id)
        if not state:
            return None
        
        now = datetime.now(timezone.utc)
        elapsed = (now - state.last_updated_at).total_seconds()
        if elapsed > self.timeout_seconds:
            # Session expired
            self.delete(user_id)
            return None
            
        return state

    def delete(self, user_id: str) -> None:
        """
        Deletes the conversation state.
        """
        if user_id in self.states:
            del self.states[user_id]
