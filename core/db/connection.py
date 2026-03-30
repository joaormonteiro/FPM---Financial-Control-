"""SQLite connection management for FinancialControl."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Generator

from core.settings import DB_PATH


def connect() -> sqlite3.Connection:
    """Return a raw SQLite connection with Row factory enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager that yields a connection, commits on success, and
    rolls back + closes on any exception.
    """
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
