"""
Database schema creation and migrations.

All CREATE TABLE statements and ALTER TABLE migrations live here.
"""

from __future__ import annotations

import sqlite3
import unicodedata

from ai.description_normalizer import normalize_description
from core.models import ALLOWED_CATEGORIES, ALLOWED_CLASSIFICATION_SOURCES, ALLOWED_PAYERS

_LEGACY_CATEGORY_MAP: dict[str, str] = {
    "alimentacao": "alimentacao",
    "lazer": "lazer",
    "transporte": "transporte",
    "educacao": "educacao",
    "moradia": "moradia",
    "assinatura": "assinaturas",
    "assinaturas": "assinaturas",
    "saude": "saude",
    "investimento": "investimentos",
    "investimentos": "investimentos",
    "entrada": "entrada",
    "receita": "entrada",
    "outro": "outros",
    "outros": "outros",
}

_LEGACY_PAYER_MAP: dict[str, str] = {
    "joao": "eu",
    "eu": "eu",
    "pais": "pais",
}


def _to_ascii_key(value: str) -> str:
    return (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
        .strip()
        .lower()
    )


def normalize_category(value: str | None) -> str | None:
    """Normalise a raw category string to a canonical ALLOWED_CATEGORIES value."""
    if value is None:
        return None
    key = _to_ascii_key(value)
    if not key:
        return None
    mapped = _LEGACY_CATEGORY_MAP.get(key, key)
    return mapped if mapped in ALLOWED_CATEGORIES else "outros"


def normalize_payer(value: str | None) -> str | None:
    """Normalise a raw payer string to a canonical ALLOWED_PAYERS value."""
    if value is None:
        return None
    key = _to_ascii_key(value)
    if not key:
        return None
    mapped = _LEGACY_PAYER_MAP.get(key, key)
    return mapped if mapped in ALLOWED_PAYERS else None


def normalize_source(source: str | None) -> str:
    """Return a valid classification source, defaulting to 'fallback'."""
    normalized = (source or "fallback").strip().lower()
    return normalized if normalized in ALLOWED_CLASSIFICATION_SOURCES else "fallback"


def normalize_confidence(value: float | None, source: str) -> float:
    """Clamp confidence to [0, 1]; manual edits are always 1.0."""
    if source == "manual":
        return 1.0
    if value is None:
        return 0.4
    return max(0.0, min(1.0, float(value)))


def _get_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    c = conn.cursor()
    c.execute(f"PRAGMA table_info({table})")
    return {r[1] for r in c.fetchall()}


def _add_column_if_missing(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    col_type: str,
) -> None:
    if column not in _get_columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")


def create_tables(conn: sqlite3.Connection) -> None:
    """Create all application tables if they do not already exist."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            date                  TEXT    NOT NULL,
            description           TEXT    NOT NULL DEFAULT '',
            raw_description       TEXT    NOT NULL DEFAULT '',
            amount                REAL    NOT NULL,
            account               TEXT    NOT NULL DEFAULT '',
            type                  TEXT    NOT NULL DEFAULT '',
            category              TEXT    DEFAULT 'outros',
            payer                 TEXT,
            note                  TEXT    DEFAULT '',
            source_file           TEXT    DEFAULT '',
            import_uid            TEXT,
            imported_at           TEXT,
            description_ai        TEXT,
            category_ai           TEXT,
            ai_confidence         REAL,
            ai_updated_at         TEXT,
            confidence            REAL    DEFAULT 0.4,
            normalized_description TEXT,
            cleaned_description   TEXT,
            classification_source TEXT    NOT NULL DEFAULT 'fallback',
            is_recurring          INTEGER NOT NULL DEFAULT 0,
            recurrence_group_id   TEXT,
            recurrence_confidence REAL
        )
        """
    )

    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_transactions_import_uid
        ON transactions (import_uid)
        WHERE import_uid IS NOT NULL
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS padroes_aprendidos (
            id                       INTEGER PRIMARY KEY AUTOINCREMENT,
            descricao_normalizada    TEXT    NOT NULL UNIQUE,
            descricao_editada_usuario TEXT,
            categoria                TEXT,
            pagador                  TEXT,
            ultima_atualizacao       TEXT    NOT NULL,
            contador_uso             INTEGER NOT NULL DEFAULT 1
        )
        """
    )


def run_migrations(conn: sqlite3.Connection) -> None:
    """Add any columns that were introduced after the initial schema."""
    migration_columns = {
        "raw_description": "TEXT NOT NULL DEFAULT ''",
        "normalized_description": "TEXT",
        "cleaned_description": "TEXT",
        "classification_source": "TEXT NOT NULL DEFAULT 'fallback'",
        "confidence": "REAL DEFAULT 0.4",
        "is_recurring": "INTEGER NOT NULL DEFAULT 0",
        "recurrence_group_id": "TEXT",
        "recurrence_confidence": "REAL",
        "description_ai": "TEXT",
        "category_ai": "TEXT",
        "ai_confidence": "REAL",
        "ai_updated_at": "TEXT",
        "imported_at": "TEXT",
        "note": "TEXT DEFAULT ''",
    }
    for col, col_type in migration_columns.items():
        _add_column_if_missing(conn, "transactions", col, col_type)


def backfill_legacy_data(conn: sqlite3.Connection) -> None:
    """
    Fill in any NULL / invalid values that pre-date the current schema.
    Safe to run repeatedly.
    """
    conn.execute(
        """
        UPDATE transactions
        SET raw_description       = COALESCE(NULLIF(raw_description, ''), description, ''),
            cleaned_description   = COALESCE(cleaned_description, description_ai, description),
            classification_source = COALESCE(NULLIF(classification_source, ''), 'fallback'),
            is_recurring          = COALESCE(is_recurring, 0),
            confidence            = COALESCE(confidence, ai_confidence, 0.4),
            note                  = COALESCE(note, ''),
            normalized_description = COALESCE(
                normalized_description,
                cleaned_description,
                raw_description,
                description
            )
        """
    )

    # Normalise categories and payers stored before validation was enforced.
    c = conn.cursor()
    c.execute(
        """
        SELECT id, category, category_ai, payer, raw_description, description
        FROM transactions
        """
    )
    rows = c.fetchall()
    for row in rows:
        tx_id = int(row[0])
        cat = normalize_category(row[1])
        cat_ai = normalize_category(row[2])
        pyr = normalize_payer(row[3])
        nd = normalize_description(str(row[4] or row[5] or ""))
        c.execute(
            """
            UPDATE transactions
            SET category = ?, category_ai = ?, payer = ?, normalized_description = ?
            WHERE id = ?
            """,
            (cat, cat_ai, pyr, nd, tx_id),
        )


def init_db() -> None:
    """
    Initialise the database: create tables, run migrations, backfill legacy data.
    Safe to call on every application start.
    """
    from core.db.connection import connect

    conn = connect()
    try:
        create_tables(conn)
        run_migrations(conn)
        backfill_legacy_data(conn)
        conn.commit()
    finally:
        conn.close()
