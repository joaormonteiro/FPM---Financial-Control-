import sqlite3
from datetime import datetime

from models import Transaction

DB_PATH = "data/finance.db"


def connect():
    return sqlite3.connect(DB_PATH)


def _get_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    c = conn.cursor()
    c.execute(f"PRAGMA table_info({table})")
    return {r[1] for r in c.fetchall()}


def _add_column_if_missing(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    column_type: str,
) -> None:
    cols = _get_columns(conn, table)
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


def init_db():
    conn = connect()
    c = conn.cursor()

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            description TEXT,
            amount REAL,
            account TEXT,
            type TEXT,
            category TEXT,
            payer TEXT,
            source_file TEXT,
            imported_at TEXT,
            description_ai TEXT,
            category_ai TEXT,
            ai_confidence REAL,
            ai_updated_at TEXT,
            confidence REAL
        )
        """
    )

    # Consolidacao idempotente do schema atual sem renomear/remover colunas existentes.
    required_columns = {
        "date": "TEXT",
        "description": "TEXT",
        "amount": "REAL",
        "account": "TEXT",
        "type": "TEXT",
        "category": "TEXT",
        "payer": "TEXT",
        "source_file": "TEXT",
        "imported_at": "TEXT",
        "description_ai": "TEXT",
        "category_ai": "TEXT",
        "ai_confidence": "REAL",
        "ai_updated_at": "TEXT",
        "confidence": "REAL",
    }
    for column, column_type in required_columns.items():
        _add_column_if_missing(conn, "transactions", column, column_type)

    conn.commit()
    conn.close()


def insert_transaction(t: Transaction):
    conn = connect()
    c = conn.cursor()

    imported_at = t.imported_at or datetime.now().isoformat()
    ai_updated_at = t.ai_updated_at
    if ai_updated_at is None and t.ai_confidence is not None:
        ai_updated_at = datetime.now().isoformat()

    c.execute(
        """
        INSERT INTO transactions
        (date, description, amount, account, type, category, payer, source_file,
         imported_at, description_ai, category_ai, ai_confidence, ai_updated_at, confidence)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            t.date.isoformat(),
            t.description,
            t.amount,
            t.account,
            t.type,
            t.category,
            t.payer,
            t.source_file,
            imported_at,
            t.description_ai,
            t.category_ai,
            t.ai_confidence,
            ai_updated_at,
            t.ai_confidence,
        ),
    )

    conn.commit()
    conn.close()
