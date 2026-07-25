import os
import tempfile
from pathlib import Path

import pytest

from src.adapters.database.connection import DatabaseManager
from src.adapters.database.repository import (
    SQLiteDealRepository,
    SQLiteNotificationRepository,
    SQLitePriceHistoryRepository,
    SQLiteUserRepository,
    SQLiteTravelGoalRepository,
)


@pytest.fixture
def temp_db_path():
    """Creates a temporary SQLite file path for the duration of the test."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield Path(path)
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def db_manager(temp_db_path):
    """Provides a DatabaseManager connected to a temporary SQLite database."""
    manager = DatabaseManager(temp_db_path)
    return manager


@pytest.fixture
def user_repo(db_manager):
    return SQLiteUserRepository(db_manager)


@pytest.fixture
def price_history_repo(db_manager):
    return SQLitePriceHistoryRepository(db_manager)


@pytest.fixture
def deal_repo(db_manager):
    return SQLiteDealRepository(db_manager)


@pytest.fixture
def notification_repo(db_manager):
    return SQLiteNotificationRepository(db_manager)


@pytest.fixture
def travel_goal_repo(db_manager):
    return SQLiteTravelGoalRepository(db_manager)

