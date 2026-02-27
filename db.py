import sqlite3
from datetime import datetime

from models import (
    ALLOWED_CATEGORIES,
    ALLOWED_CLASSIFICATION_SOURCES,
    ALLOWED_PAYERS,
    Transaction,
)

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


def _normalize_source(source: str | None) -> str:
    allowed_sources = set(ALLOWED_CLASSIFICATION_SOURCES) | {"history"}
    normalized = (source or "heuristic").strip().lower()
    if normalized not in allowed_sources:
        return "heuristic"
    return normalized


def _normalize_confidence(value: float | None, source: str) -> float:
    if source == "manual":
        return 1.0

    if value is None:
        return 0.0 if source == "heuristic" else 0.0

    conf = float(value)
    if conf < 0.0:
        return 0.0
    if conf > 1.0:
        return 1.0
    return conf


def _normalize_category(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized in ALLOWED_CATEGORIES:
        return normalized
    return normalized


def _normalize_payer(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized in ALLOWED_PAYERS:
        return normalized
    return normalized


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
            confidence REAL,
            raw_description TEXT NOT NULL DEFAULT '',
            cleaned_description TEXT,
            classification_source TEXT NOT NULL DEFAULT 'heuristic',
            is_recurring INTEGER NOT NULL DEFAULT 0,
            recurrence_group_id TEXT,
            recurrence_confidence REAL
        )
        """
    )

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
        "raw_description": "TEXT NOT NULL DEFAULT ''",
        "cleaned_description": "TEXT",
        "classification_source": "TEXT NOT NULL DEFAULT 'heuristic'",
        "is_recurring": "INTEGER NOT NULL DEFAULT 0",
        "recurrence_group_id": "TEXT",
        "recurrence_confidence": "REAL",
    }

    for column, column_type in required_columns.items():
        _add_column_if_missing(conn, "transactions", column, column_type)

    # Backfill minimo para manter consistencia dos novos campos em bases antigas.
    conn.execute(
        """
        UPDATE transactions
        SET raw_description = COALESCE(NULLIF(raw_description, ''), description, ''),
            cleaned_description = COALESCE(cleaned_description, description_ai, description),
            classification_source = COALESCE(NULLIF(classification_source, ''), 'heuristic'),
            is_recurring = COALESCE(is_recurring, 0),
            recurrence_group_id = COALESCE(recurrence_group_id, NULL),
            recurrence_confidence = COALESCE(recurrence_confidence, NULL),
            confidence = COALESCE(confidence, ai_confidence, 0.0)
        """
    )

    conn.commit()
    conn.close()


def insert_transaction(t: Transaction):
    conn = connect()
    c = conn.cursor()

    raw_description = (t.raw_description or "").strip()
    if not raw_description:
        conn.close()
        raise ValueError("raw_description nao pode ser vazio")

    imported_at = t.imported_at or datetime.now().isoformat()
    cleaned_description = t.cleaned_description or t.description_ai or t.description or raw_description

    classification_source = _normalize_source(t.classification_source)
    confidence_value = t.confidence if t.confidence is not None else t.ai_confidence
    confidence = _normalize_confidence(confidence_value, classification_source)

    category = _normalize_category(t.category)
    payer = _normalize_payer(t.payer)
    if category is None and payer is None:
        classification_source = "heuristic"
        confidence = 0.0

    ai_updated_at = t.ai_updated_at
    if ai_updated_at is None and t.ai_confidence is not None:
        ai_updated_at = datetime.now().isoformat()

    c.execute(
        """
        INSERT INTO transactions
        (date, description, amount, account, type, category, payer, source_file,
         imported_at, description_ai, category_ai, ai_confidence, ai_updated_at,
         confidence, raw_description, cleaned_description, classification_source, is_recurring,
         recurrence_group_id, recurrence_confidence)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            t.date.isoformat(),
            t.description,
            t.amount,
            t.account,
            t.type,
            category,
            payer,
            t.source_file,
            imported_at,
            t.description_ai,
            t.category_ai,
            t.ai_confidence,
            ai_updated_at,
            confidence,
            raw_description,
            cleaned_description,
            classification_source,
            1 if t.is_recurring else 0,
            None,
            None,
        ),
    )

    conn.commit()
    conn.close()


def update_transaction_manual(tx_id: int, category: str, payer: str | None):
    conn = connect()
    c = conn.cursor()

    normalized_category = _normalize_category(category)
    normalized_payer = _normalize_payer(payer)

    c.execute(
        """
        UPDATE transactions
        SET category = ?,
            category_ai = ?,
            payer = ?,
            classification_source = 'manual',
            confidence = 1.0,
            ai_confidence = 1.0
        WHERE id = ?
        """,
        (normalized_category, normalized_category, normalized_payer, tx_id),
    )

    conn.commit()
    conn.close()


def reprocess_all_with_history():
    from ai.history_classifier import HistoryBasedClassifier
    from ai.rule_engine import apply_rules

    conn = connect()
    c = conn.cursor()

    c.execute(
        """
        SELECT id, raw_description, cleaned_description, description, amount
        FROM transactions
        WHERE classification_source != 'manual'
          AND (
                classification_source = 'heuristic'
                OR COALESCE(confidence, 0.0) < 0.6
              )
        """
    )
    rows = c.fetchall()

    classifier = HistoryBasedClassifier(DB_PATH)
    classifier.build_index()

    updated = 0
    for tx_id, raw_description, cleaned_description, description, amount in rows:
        raw_desc = (raw_description or description or "").strip()
        if not raw_desc:
            continue

        clean_desc = (cleaned_description or raw_desc).strip()

        rule_result = apply_rules(raw_desc, float(amount or 0.0))
        if rule_result is not None:
            rule_desc, rule_category, rule_payer, rule_conf = rule_result
            c.execute(
                """
                UPDATE transactions
                SET category = ?,
                    payer = ?,
                    confidence = ?,
                    classification_source = 'rule',
                    cleaned_description = COALESCE(?, cleaned_description)
                WHERE id = ?
                """,
                (
                    _normalize_category(rule_category),
                    _normalize_payer(rule_payer),
                    _normalize_confidence(float(rule_conf), "rule"),
                    rule_desc,
                    tx_id,
                ),
            )
            updated += 1
            continue

        pred = classifier.predict(clean_desc)
        if pred is None:
            continue

        pred_category, pred_payer, pred_confidence = pred
        c.execute(
            """
            UPDATE transactions
            SET category = ?,
                payer = ?,
                confidence = ?,
                classification_source = 'history'
            WHERE id = ?
            """,
            (
                _normalize_category(pred_category),
                _normalize_payer(pred_payer),
                _normalize_confidence(float(pred_confidence), "history"),
                tx_id,
            ),
        )
        updated += 1

    conn.commit()
    conn.close()
    return updated


def set_transaction_recurring(transaction_id: int, group_name: str) -> None:
    from ai.custom_rule_engine import apply_custom_rule

    conn = connect()
    c = conn.cursor()

    c.execute(
        """
        UPDATE transactions
        SET is_recurring = 1,
            recurrence_group_id = ?,
            recurrence_confidence = 1.0
        WHERE id = ?
        """,
        (group_name, transaction_id),
    )

    c.execute(
        """
        SELECT cleaned_description, raw_description, amount
        FROM transactions
        WHERE id = ?
        """,
        (transaction_id,),
    )
    row = c.fetchone()
    if row:
        cleaned_description, raw_description, amount = row
        custom_result = apply_custom_rule(
            description=(cleaned_description or raw_description or ""),
            amount=float(amount or 0.0),
            is_recurring=True,
        )
        if custom_result is not None:
            custom_category, custom_confidence = custom_result
            c.execute(
                """
                UPDATE transactions
                SET category = ?,
                    category_ai = ?,
                    confidence = ?,
                    ai_confidence = ?,
                    classification_source = 'rule'
                WHERE id = ?
                """,
                (
                    _normalize_category(custom_category),
                    _normalize_category(custom_category),
                    _normalize_confidence(float(custom_confidence), "rule"),
                    _normalize_confidence(float(custom_confidence), "rule"),
                    transaction_id,
                ),
            )

    conn.commit()
    conn.close()
