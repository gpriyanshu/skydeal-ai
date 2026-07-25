import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from src.adapters.database.connection import DatabaseManager
from src.domain.entities import Deal, Flight, Notification, PriceHistory, User, TravelGoal, PersonalRoute
from src.domain.interfaces import (
    DealRepository,
    NotificationRepository,
    PriceHistoryRepository,
    UserRepository,
    TravelGoalRepository,
    PersonalRouteRepository,
)


class SQLiteUserRepository(UserRepository):
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def save(self, user: User) -> None:
        query = """
        INSERT OR REPLACE INTO users (
            id, username, email, preferred_countries, preferred_airports,
            preferred_airlines, budget, max_stops, max_duration_minutes,
            cabin_class, notification_enabled, baseline_sent
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        with self.db_manager.transaction() as cursor:
            cursor.execute(
                query,
                (
                    user.id,
                    user.username,
                    user.email,
                    json.dumps(user.preferred_countries),
                    json.dumps(user.preferred_airports),
                    json.dumps(user.preferred_airlines),
                    user.budget,
                    user.max_stops,
                    user.max_duration_minutes,
                    user.cabin_class,
                    1 if user.notification_enabled else 0,
                    1 if user.baseline_sent else 0,
                ),
            )

    def get_by_id(self, user_id: str) -> User | None:
        query = "SELECT * FROM users WHERE id = ?;"
        conn = self.db_manager.get_connection()
        try:
            row = conn.execute(query, (user_id,)).fetchone()
            if not row:
                return None
            return self._row_to_user(row)
        finally:
            conn.close()

    def get_all_active(self) -> list[User]:
        query = "SELECT * FROM users WHERE notification_enabled = 1;"
        conn = self.db_manager.get_connection()
        try:
            rows = conn.execute(query).fetchall()
            return [self._row_to_user(row) for row in rows]
        finally:
            conn.close()

    def delete(self, user_id: str) -> None:
        query = "DELETE FROM users WHERE id = ?;"
        with self.db_manager.transaction() as cursor:
            cursor.execute(query, (user_id,))

    def _row_to_user(self, row: Any) -> User:
        return User(
            id=row["id"],
            username=row["username"],
            email=row["email"],
            preferred_countries=json.loads(row["preferred_countries"]),
            preferred_airports=json.loads(row["preferred_airports"]),
            preferred_airlines=json.loads(row["preferred_airlines"]),
            budget=row["budget"],
            max_stops=row["max_stops"],
            max_duration_minutes=row["max_duration_minutes"],
            cabin_class=row["cabin_class"],
            notification_enabled=bool(row["notification_enabled"]),
            baseline_sent=bool(row["baseline_sent"]) if "baseline_sent" in row.keys() else False,
        )


class SQLitePriceHistoryRepository(PriceHistoryRepository):
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def save(self, history: PriceHistory) -> None:
        query = """
        INSERT OR REPLACE INTO price_history (
            origin, destination, current_price, lowest_price, highest_price,
            rolling_average, first_seen, last_seen, observation_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        with self.db_manager.transaction() as cursor:
            cursor.execute(
                query,
                (
                    history.origin,
                    history.destination,
                    history.current_price,
                    history.lowest_price,
                    history.highest_price,
                    history.rolling_average,
                    history.first_seen.isoformat(),
                    history.last_seen.isoformat(),
                    history.observation_count,
                ),
            )

    def get(self, origin: str, destination: str) -> PriceHistory | None:
        query = "SELECT * FROM price_history WHERE origin = ? AND destination = ?;"
        conn = self.db_manager.get_connection()
        try:
            row = conn.execute(query, (origin, destination)).fetchone()
            if not row:
                return None
            return PriceHistory(
                origin=row["origin"],
                destination=row["destination"],
                current_price=row["current_price"],
                lowest_price=row["lowest_price"],
                highest_price=row["highest_price"],
                rolling_average=row["rolling_average"],
                first_seen=datetime.fromisoformat(row["first_seen"]),
                last_seen=datetime.fromisoformat(row["last_seen"]),
                observation_count=row["observation_count"] if "observation_count" in row.keys() else 1,
            )
        finally:
            conn.close()

    def save_observation(self, origin: str, destination: str, price: Decimal, scanned_at: datetime) -> None:
        query = """
        INSERT INTO price_observations (origin, destination, price, scanned_at)
        VALUES (?, ?, ?, ?);
        """
        with self.db_manager.transaction() as cursor:
            cursor.execute(query, (origin.upper(), destination.upper(), float(price), scanned_at.isoformat()))

    def get_observations(self, origin: str, destination: str) -> list[Decimal]:
        query = """
        SELECT price FROM price_observations
        WHERE origin = ? AND destination = ?
        ORDER BY id ASC;
        """
        conn = self.db_manager.get_connection()
        try:
            rows = conn.execute(query, (origin.upper(), destination.upper())).fetchall()
            return [Decimal(str(r["price"])) for r in rows]
        finally:
            conn.close()


class SQLiteDealRepository(DealRepository):
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def save(self, deal: Deal) -> None:
        query = """
        INSERT INTO deals (
            id, flight_id, origin, destination, price, airline, stops,
            duration_minutes, departure_date, return_date, cabin_class,
            deep_link, category, discount_percentage, historical_average, detected_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            price = excluded.price,
            category = excluded.category,
            discount_percentage = excluded.discount_percentage,
            historical_average = excluded.historical_average,
            detected_at = excluded.detected_at;
        """
        with self.db_manager.transaction() as cursor:
            cursor.execute(
                query,
                (
                    deal.id,
                    deal.flight.id,
                    deal.flight.origin,
                    deal.flight.destination,
                    deal.flight.price,
                    deal.flight.airline,
                    deal.flight.stops,
                    deal.flight.duration_minutes,
                    deal.flight.departure_date.isoformat(),
                    deal.flight.return_date.isoformat() if deal.flight.return_date else None,
                    deal.flight.cabin_class,
                    deal.flight.deep_link,
                    deal.category,
                    deal.discount_percentage,
                    deal.historical_average,
                    deal.detected_at.isoformat(),
                ),
            )

    def get_by_id(self, deal_id: str) -> Deal | None:
        query = "SELECT * FROM deals WHERE id = ?;"
        conn = self.db_manager.get_connection()
        try:
            row = conn.execute(query, (deal_id,)).fetchone()
            if not row:
                return None
            return self._row_to_deal(row)
        finally:
            conn.close()

    def get_recent_deals(self, limit: int = 10) -> list[Deal]:
        query = "SELECT * FROM deals ORDER BY detected_at DESC LIMIT ?;"
        conn = self.db_manager.get_connection()
        try:
            rows = conn.execute(query, (limit,)).fetchall()
            return [self._row_to_deal(row) for row in rows]
        finally:
            conn.close()

    def _row_to_deal(self, row: Any) -> Deal:
        flight = Flight(
            id=row["flight_id"],
            origin=row["origin"],
            destination=row["destination"],
            departure_date=datetime.fromisoformat(row["departure_date"]),
            return_date=datetime.fromisoformat(row["return_date"]) if row["return_date"] else None,
            price=row["price"],
            airline=row["airline"],
            stops=row["stops"],
            duration_minutes=row["duration_minutes"],
            cabin_class=row["cabin_class"],
            deep_link=row["deep_link"],
        )
        return Deal(
            id=row["id"],
            flight=flight,
            category=row["category"],
            discount_percentage=row["discount_percentage"],
            historical_average=row["historical_average"],
            detected_at=datetime.fromisoformat(row["detected_at"]),
        )


class SQLiteNotificationRepository(NotificationRepository):
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def save(self, notification: Notification) -> None:
        query = """
        INSERT OR REPLACE INTO notifications (
            id, user_id, deal_id, provider, status, retry_count, last_attempt, error_message
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """
        with self.db_manager.transaction() as cursor:
            cursor.execute(
                query,
                (
                    notification.id,
                    notification.user_id,
                    notification.deal_id,
                    notification.provider,
                    notification.status,
                    notification.retry_count,
                    notification.last_attempt.isoformat() if notification.last_attempt else None,
                    notification.error_message,
                ),
            )

    def get_pending(self) -> list[Notification]:
        query = "SELECT * FROM notifications WHERE status = 'pending';"
        conn = self.db_manager.get_connection()
        try:
            rows = conn.execute(query).fetchall()
            return [self._row_to_notification(row) for row in rows]
        finally:
            conn.close()

    def get_sent_for_deal_and_user(self, deal_id: str, user_id: str) -> Notification | None:
        query = "SELECT * FROM notifications WHERE deal_id = ? AND user_id = ? LIMIT 1;"
        conn = self.db_manager.get_connection()
        try:
            row = conn.execute(query, (deal_id, user_id)).fetchone()
            if not row:
                return None
            return self._row_to_notification(row)
        finally:
            conn.close()

    def has_recent_notification_for_route(
        self, user_id: str, origin: str, destination: str, since: datetime
    ) -> bool:
        query = """
        SELECT 1 FROM notifications n
        JOIN deals d ON n.deal_id = d.id
        WHERE n.user_id = ? 
          AND d.origin = ? 
          AND d.destination = ? 
          AND n.status = 'sent'
          AND n.last_attempt >= ?
        LIMIT 1;
        """
        conn = self.db_manager.get_connection()
        try:
            row = conn.execute(
                query, (user_id, origin, destination, since.isoformat())
            ).fetchone()
            return bool(row)
        finally:
            conn.close()

    def get_last_sent_deal_for_route(
        self, user_id: str, origin: str, destination: str, goal_id: str | None = None
    ) -> Deal | None:
        if goal_id is not None:
            query = """
            SELECT d.* FROM notifications n
            JOIN deals d ON n.deal_id = d.id
            WHERE n.user_id = ? 
              AND d.origin = ? 
              AND d.destination = ? 
              AND n.status = 'sent'
              AND n.id LIKE 'notif_goal_' || ? || '_%'
            ORDER BY n.last_attempt DESC
            LIMIT 1;
            """
            params = (user_id, origin, destination, goal_id)
        else:
            query = """
            SELECT d.* FROM notifications n
            JOIN deals d ON n.deal_id = d.id
            WHERE n.user_id = ? 
              AND d.origin = ? 
              AND d.destination = ? 
              AND n.status = 'sent'
              AND n.id NOT LIKE 'notif_goal_%'
            ORDER BY n.last_attempt DESC
            LIMIT 1;
            """
            params = (user_id, origin, destination)

        conn = self.db_manager.get_connection()
        try:
            row = conn.execute(query, params).fetchone()
            if not row:
                return None
            return SQLiteDealRepository(self.db_manager)._row_to_deal(row)
        finally:
            conn.close()

    def _row_to_notification(self, row: Any) -> Notification:
        return Notification(
            id=row["id"],
            user_id=row["user_id"],
            deal_id=row["deal_id"],
            provider=row["provider"],
            status=row["status"],
            retry_count=row["retry_count"],
            last_attempt=datetime.fromisoformat(row["last_attempt"]) if row["last_attempt"] else None,
            error_message=row["error_message"],
        )


class SQLiteTravelGoalRepository(TravelGoalRepository):
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def create_goal(self, goal: TravelGoal) -> TravelGoal:
        query = """
        INSERT INTO travel_goals (
            id, user_id, country, start_date, end_date, budget_inr, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        with self.db_manager.transaction() as cursor:
            cursor.execute(
                query,
                (
                    goal.id,
                    goal.user_id,
                    goal.country,
                    goal.start_date.isoformat(),
                    goal.end_date.isoformat(),
                    float(goal.budget_inr),
                    goal.status,
                    goal.created_at.isoformat(),
                    goal.updated_at.isoformat(),
                ),
            )
        return goal

    def update_goal(self, goal: TravelGoal) -> TravelGoal:
        query = """
        UPDATE travel_goals
        SET user_id = ?,
            country = ?,
            start_date = ?,
            end_date = ?,
            budget_inr = ?,
            status = ?,
            created_at = ?,
            updated_at = ?
        WHERE id = ?;
        """
        with self.db_manager.transaction() as cursor:
            cursor.execute(
                query,
                (
                    goal.user_id,
                    goal.country,
                    goal.start_date.isoformat(),
                    goal.end_date.isoformat(),
                    float(goal.budget_inr),
                    goal.status,
                    goal.created_at.isoformat(),
                    goal.updated_at.isoformat(),
                    goal.id,
                ),
            )
        return goal

    def delete_goal(self, goal_id: str) -> bool:
        # Check if the goal exists first
        conn = self.db_manager.get_connection()
        try:
            row = conn.execute("SELECT 1 FROM travel_goals WHERE id = ?;", (goal_id,)).fetchone()
            if not row:
                return False
        finally:
            conn.close()

        query = "DELETE FROM travel_goals WHERE id = ?;"
        with self.db_manager.transaction() as cursor:
            cursor.execute(query, (goal_id,))
        return True

    def list_goals(self, user_id: str) -> list[TravelGoal]:
        query = "SELECT * FROM travel_goals WHERE user_id = ? ORDER BY created_at DESC;"
        conn = self.db_manager.get_connection()
        try:
            rows = conn.execute(query, (user_id,)).fetchall()
            return [self._row_to_travel_goal(row) for row in rows]
        finally:
            conn.close()

    def get_active_goals(self, user_id: str) -> list[TravelGoal]:
        query = "SELECT * FROM travel_goals WHERE user_id = ? AND status = 'ACTIVE' ORDER BY created_at DESC;"
        conn = self.db_manager.get_connection()
        try:
            rows = conn.execute(query, (user_id,)).fetchall()
            return [self._row_to_travel_goal(row) for row in rows]
        finally:
            conn.close()

    def _row_to_travel_goal(self, row: Any) -> TravelGoal:
        from decimal import Decimal
        return TravelGoal(
            id=row["id"],
            user_id=row["user_id"],
            country=row["country"],
            start_date=datetime.fromisoformat(row["start_date"]),
            end_date=datetime.fromisoformat(row["end_date"]),
            budget_inr=Decimal(str(row["budget_inr"])),
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )


class SQLitePersonalRouteRepository(PersonalRouteRepository):
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def save(self, route: PersonalRoute) -> None:
        query = """
        INSERT OR REPLACE INTO personal_routes (
            id, user_id, origin_airport, destination_airport, enabled, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?);
        """
        with self.db_manager.transaction() as cursor:
            cursor.execute(
                query,
                (
                    route.id,
                    route.user_id,
                    route.origin_airport,
                    route.destination_airport,
                    1 if route.enabled else 0,
                    route.created_at.isoformat(),
                    route.updated_at.isoformat(),
                ),
            )

    def get_by_id(self, route_id: str) -> PersonalRoute | None:
        query = "SELECT * FROM personal_routes WHERE id = ?;"
        conn = self.db_manager.get_connection()
        try:
            row = conn.execute(query, (route_id,)).fetchone()
            if not row:
                return None
            return self._row_to_personal_route(row)
        finally:
            conn.close()

    def get_by_route(self, user_id: str, origin: str, destination: str) -> PersonalRoute | None:
        query = "SELECT * FROM personal_routes WHERE user_id = ? AND origin_airport = ? AND destination_airport = ?;"
        conn = self.db_manager.get_connection()
        try:
            row = conn.execute(query, (user_id, origin.upper(), destination.upper())).fetchone()
            if not row:
                return None
            return self._row_to_personal_route(row)
        finally:
            conn.close()

    def list_routes(self, user_id: str) -> list[PersonalRoute]:
        query = "SELECT * FROM personal_routes WHERE user_id = ? ORDER BY created_at DESC;"
        conn = self.db_manager.get_connection()
        try:
            rows = conn.execute(query, (user_id,)).fetchall()
            return [self._row_to_personal_route(row) for row in rows]
        finally:
            conn.close()

    def delete(self, route_id: str) -> None:
        query = "DELETE FROM personal_routes WHERE id = ?;"
        with self.db_manager.transaction() as cursor:
            cursor.execute(query, (route_id,))

    def _row_to_personal_route(self, row: Any) -> PersonalRoute:
        return PersonalRoute(
            id=row["id"],
            user_id=row["user_id"],
            origin_airport=row["origin_airport"],
            destination_airport=row["destination_airport"],
            enabled=bool(row["enabled"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

