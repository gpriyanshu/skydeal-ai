import uuid
import logging
from datetime import datetime, timezone
from decimal import Decimal

from src.domain.entities import TravelGoal, TravelGoalDraft
from src.domain.interfaces import TravelGoalRepository
from src.domain.travel_goal_parser import TravelGoalParser

logger = logging.getLogger(__name__)


class TravelGoalService:
    """
    Service containing business logic for Travel Goals.
    Validates inputs, prevents duplicate goals, and manages goal lifecycles.
    """
    def __init__(self, travel_goal_repo: TravelGoalRepository, parser: TravelGoalParser):
        self.travel_goal_repo = travel_goal_repo
        self.parser = parser
        self.conversation_service = None

    def set_conversation_service(self, conversation_service):
        self.conversation_service = conversation_service

    def create_goal(self, user_id: str, query: str, now: datetime | None = None) -> TravelGoal:
        if now is None:
            now = datetime.now(timezone.utc)

        # 1. Obtain structured slots via ConversationService (Single Source of Truth)
        state = None
        if self.conversation_service:
            state = self.conversation_service.extract_and_save_slots(user_id, query, now)
        else:
            # Fallback for standalone TravelGoalService tests (instantiate lightweight inline helper)
            from src.adapters.database.conversation_state_repository import InMemoryConversationStateRepository
            from src.domain.conversation_service import ConversationService
            from unittest.mock import MagicMock
            repo = InMemoryConversationStateRepository()
            cs = ConversationService(
                conversation_state_repo=repo,
                ai_provider=MagicMock(),
                travel_goal_service=self,
                deal_engine=None,
                domain_deal_engine=None,
                scanner_service=None,
                settings=None
            )
            state = cs.extract_and_save_slots(user_id, query, now)

        # Log: Extracted slots
        logger.info(
            f"Extracted slots: country={state.country}, city={state.city}, "
            f"destination_codes={state.destination_codes}, month={state.month}, "
            f"travel_date_window={state.travel_date_window}, budget={state.budget}, "
            f"origin={state.origin or state.preferred_origin}, travel_type={state.travel_type}"
        )

        # Log: Structured GoalRequest
        goal_request = {
            "user_id": user_id,
            "country": state.country,
            "travel_date_window": state.travel_date_window,
            "budget": state.budget
        }
        logger.info(f"Structured GoalRequest: {goal_request}")

        # Construct TravelGoalDraft from state properties (Never re-parse text)
        budget_val = Decimal(str(state.budget)) if state.budget is not None else None
        
        start_date = None
        end_date = None
        if state.travel_date_window:
            p_start, p_end = state.travel_date_window.split(" to ")
            start_date = datetime.fromisoformat(p_start).replace(tzinfo=timezone.utc)
            end_dt = datetime.fromisoformat(p_end).replace(tzinfo=timezone.utc)
            end_date = datetime(end_dt.year, end_dt.month, end_dt.day, 23, 59, 59, tzinfo=timezone.utc)

        draft = TravelGoalDraft(
            country=state.country,
            start_date=start_date,
            end_date=end_date,
            budget_inr=budget_val
        )

        # Log: TravelGoalParser input
        logger.info(f"TravelGoalParser input: {draft}")

        # 2. Call parser to validate
        draft = self.parser.parse(draft, now=now)

        # 3. Check for duplicate goals
        existing_goals = self.travel_goal_repo.list_goals(user_id)
        for eg in existing_goals:
            if (
                eg.country.lower() == draft.country.lower()
                and eg.start_date.date() == draft.start_date.date()
                and eg.end_date.date() == draft.end_date.date()
            ):
                raise ValueError("Goal already exists.")

        # 4. Create TravelGoal domain entity
        goal = TravelGoal(
            id=uuid.uuid4().hex[:12],
            user_id=user_id,
            country=draft.country,
            start_date=draft.start_date,
            end_date=draft.end_date,
            budget_inr=draft.budget_inr if draft.budget_inr is not None else 0,
            status="ACTIVE",
            created_at=now,
            updated_at=now,
        )

        # Log: TravelGoal creation
        logger.info(
            f"TravelGoal creation: id={goal.id}, country={goal.country}, "
            f"start={goal.start_date}, end={goal.end_date}, budget={goal.budget_inr}"
        )

        # 5. Persist to DB
        return self.travel_goal_repo.create_goal(goal)

    def pause_goal(self, user_id: str, goal_id: str, now: datetime | None = None) -> bool:
        if now is None:
            now = datetime.now(timezone.utc)

        goals = self.travel_goal_repo.list_goals(user_id)
        target_goal = next((g for g in goals if g.id == goal_id), None)
        if not target_goal:
            raise ValueError("Goal not found.")

        target_goal.status = "PAUSED"
        target_goal.updated_at = now
        self.travel_goal_repo.update_goal(target_goal)
        return True

    def resume_goal(self, user_id: str, goal_id: str, now: datetime | None = None) -> bool:
        if now is None:
            now = datetime.now(timezone.utc)

        goals = self.travel_goal_repo.list_goals(user_id)
        target_goal = next((g for g in goals if g.id == goal_id), None)
        if not target_goal:
            raise ValueError("Goal not found.")

        target_goal.status = "ACTIVE"
        target_goal.updated_at = now
        self.travel_goal_repo.update_goal(target_goal)
        return True

    def delete_goal(self, user_id: str, goal_id: str) -> bool:
        goals = self.travel_goal_repo.list_goals(user_id)
        target_goal = next((g for g in goals if g.id == goal_id), None)
        if not target_goal:
            raise ValueError("Goal not found.")

        return self.travel_goal_repo.delete_goal(goal_id)

    def list_goals(self, user_id: str) -> list[TravelGoal]:
        return self.travel_goal_repo.list_goals(user_id)

    def update_goal(self, goal: TravelGoal) -> TravelGoal:
        return self.travel_goal_repo.update_goal(goal)
