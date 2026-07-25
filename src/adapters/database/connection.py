import sqlite3
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path

from loguru import logger

# Register Decimal adapter for SQLite parameter binding
sqlite3.register_adapter(Decimal, float)


class DatabaseManager:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        # Ensure parent directories exist
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize_db()

    def get_connection(self) -> sqlite3.Connection:
        """Creates and configures a SQLite connection with WAL mode and foreign keys enabled."""
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=30.0,  # Prevent locked exceptions under heavy loads
            isolation_level=None  # Enable autocommit mode by default
        )
        conn.row_factory = sqlite3.Row
        
        # Performance and security configurations
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        
        return conn

    @contextmanager
    def transaction(self):
        """Context manager to ensure transactions are safely committed or rolled back."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("BEGIN IMMEDIATE TRANSACTION;")
            yield cursor
            conn.commit()
        except Exception as e:
            logger.error(f"Transaction failed, rolling back: {e}")
            try:
                conn.rollback()
            except sqlite3.OperationalError:
                pass  # Transaction was not active
            raise
        finally:
            cursor.close()
            conn.close()

    def initialize_db(self) -> None:
        """Runs creation scripts for SQLite tables."""
        logger.info(f"Initializing SQLite database at: {self.db_path}")
        
        create_users_table = """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT,
            email TEXT,
            preferred_countries TEXT NOT NULL, -- JSON list
            preferred_airports TEXT NOT NULL,  -- JSON list
            preferred_airlines TEXT NOT NULL,  -- JSON list
            budget REAL,
            max_stops INTEGER,
            max_duration_minutes INTEGER,
            cabin_class TEXT NOT NULL,
            notification_enabled INTEGER NOT NULL DEFAULT 1,
            baseline_sent INTEGER NOT NULL DEFAULT 0
        );
        """

        create_price_history_table = """
        CREATE TABLE IF NOT EXISTS price_history (
            origin TEXT,
            destination TEXT,
            current_price REAL NOT NULL,
            lowest_price REAL NOT NULL,
            highest_price REAL NOT NULL,
            rolling_average REAL NOT NULL,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            observation_count INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (origin, destination)
        );
        """

        create_price_observations_table = """
        CREATE TABLE IF NOT EXISTS price_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            origin TEXT NOT NULL,
            destination TEXT NOT NULL,
            price REAL NOT NULL,
            scanned_at TEXT NOT NULL
        );
        """

        create_deals_table = """
        CREATE TABLE IF NOT EXISTS deals (
            id TEXT PRIMARY KEY,
            flight_id TEXT NOT NULL,
            origin TEXT NOT NULL,
            destination TEXT NOT NULL,
            price REAL NOT NULL,
            airline TEXT NOT NULL,
            stops INTEGER NOT NULL,
            duration_minutes INTEGER NOT NULL,
            departure_date TEXT NOT NULL,
            return_date TEXT,
            cabin_class TEXT NOT NULL,
            deep_link TEXT,
            category TEXT NOT NULL,
            discount_percentage REAL NOT NULL,
            historical_average REAL NOT NULL,
            detected_at TEXT NOT NULL
        );
        """

        create_notifications_table = """
        CREATE TABLE IF NOT EXISTS notifications (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            deal_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            status TEXT NOT NULL,
            retry_count INTEGER NOT NULL DEFAULT 0,
            last_attempt TEXT,
            error_message TEXT,
            FOREIGN KEY (deal_id) REFERENCES deals(id) ON DELETE CASCADE
        );
        """

        create_travel_goals_table = """
        CREATE TABLE IF NOT EXISTS travel_goals (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            country TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            budget_inr REAL NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('ACTIVE', 'PAUSED')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """

        create_personal_routes_table = """
        CREATE TABLE IF NOT EXISTS personal_routes (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            origin_airport TEXT NOT NULL,
            destination_airport TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(user_id, origin_airport, destination_airport)
        );
        """

        # Index creations for queries optimization
        create_price_idx = "CREATE INDEX IF NOT EXISTS idx_history_route ON price_history(origin, destination);"
        create_price_obs_idx = "CREATE INDEX IF NOT EXISTS idx_price_obs_route ON price_observations(origin, destination);"
        create_notif_idx = "CREATE INDEX IF NOT EXISTS idx_notif_dedup ON notifications(deal_id, user_id);"
        create_travel_goals_idx = "CREATE INDEX IF NOT EXISTS idx_travel_goals_user ON travel_goals(user_id);"
        create_personal_routes_idx = "CREATE INDEX IF NOT EXISTS idx_personal_routes_user ON personal_routes(user_id);"

        conn = self.get_connection()
        try:
            with conn:
                conn.execute(create_users_table)
                conn.execute(create_price_history_table)
                conn.execute(create_price_observations_table)
                conn.execute(create_deals_table)
                conn.execute(create_notifications_table)
                conn.execute(create_travel_goals_table)
                conn.execute(create_personal_routes_table)
                conn.execute(create_price_idx)
                conn.execute(create_price_obs_idx)
                conn.execute(create_notif_idx)
                conn.execute(create_travel_goals_idx)
                conn.execute(create_personal_routes_idx)
            # Run column migration to ensure baseline_sent exists
            try:
                conn.execute("ALTER TABLE users ADD COLUMN baseline_sent INTEGER NOT NULL DEFAULT 0;")
            except sqlite3.OperationalError:
                pass  # already exists
            logger.info("Database schemas and indexes initialized successfully.")
        except Exception as e:
            logger.critical(f"Failed to initialize database: {e}")
            raise
        finally:
            conn.close()
