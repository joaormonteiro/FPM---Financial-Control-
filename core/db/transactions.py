"""
CRUD operations for the transactions table.

All writes use INSERT OR IGNORE (never INSERT OR REPLACE) to prevent
duplication.  Manual edits also update the learned-patterns table and
auto-generate a keyword rule.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import datetime
from typing import Any, Optional

from ai.description_normalizer import normalize_description
from core.db.connection import connect
from core.db.patterns import ensure_patterns_table, upsert_pattern
from core.db.schema import (
    normalize_category,
    normalize_confidence,
    normalize_payer,
    normalize_source,
)
from core.models import Transaction, capitalize_first
from core.settings import DB_PATH


def insert_transaction(t: Transaction) -> bool:
    """
    Persist *t* to the database.

    Returns ``True`` if the row was inserted, ``False`` if it was skipped
    because a transaction with the same ``import_uid`` already exists.

    Raises ``ValueError`` if ``raw_description`` is empty.
    """
    raw_description = (t.raw_description or "").strip()
    if not raw_description:
        raise ValueError("raw_description cannot be empty")

    conn = connect()
    c = conn.cursor()

    try:
        import_uid = (t.import_uid or "").strip() or None

        if import_uid is not None:
            c.execute(
                "SELECT 1 FROM transactions WHERE import_uid = ? LIMIT 1",
                (import_uid,),
            )
            if c.fetchone() is not None:
                return False

        imported_at = t.imported_at or datetime.now().isoformat()
        description = capitalize_first((t.description or raw_description).strip())
        cleaned = capitalize_first(
            (t.cleaned_description or t.description_ai or description or raw_description).strip()
        )
        description_ai = capitalize_first((t.description_ai or cleaned or description).strip())
        normalized = (
            t.normalized_description or normalize_description(raw_description) or ""
        ).strip()
        note = (t.note or "").strip()
        source_file = (t.source_file or "").strip()

        classification_source = normalize_source(t.classification_source)
        conf_raw = t.confidence if t.confidence is not None else t.ai_confidence
        confidence = normalize_confidence(conf_raw, classification_source)

        category = normalize_category(t.category) or "outros"
        payer = normalize_payer(t.payer)
        category_ai = normalize_category(t.category_ai or t.category) or "outros"

        ai_updated_at = t.ai_updated_at
        if ai_updated_at is None and t.ai_confidence is not None:
            ai_updated_at = datetime.now().isoformat()

        c.execute(
            """
            INSERT OR IGNORE INTO transactions
                (date, description, raw_description, amount, account, type,
                 category, payer, note, source_file, import_uid, imported_at,
                 description_ai, category_ai, ai_confidence, ai_updated_at,
                 confidence, normalized_description, cleaned_description,
                 classification_source, is_recurring, recurrence_group_id,
                 recurrence_confidence)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                t.date.isoformat(),
                description,
                raw_description,
                float(t.amount),
                str(t.account or ""),
                str(t.type or ""),
                category,
                payer,
                note,
                source_file,
                import_uid,
                imported_at,
                description_ai,
                category_ai,
                t.ai_confidence,
                ai_updated_at,
                confidence,
                normalized,
                cleaned,
                classification_source,
                1 if t.is_recurring else 0,
                t.recurrence_group_id,
                None,
            ),
        )
        inserted = c.rowcount > 0
        conn.commit()
        return inserted
    finally:
        conn.close()


def update_transaction_manual(
    tx_id: int,
    description: Optional[str] = None,
    category: Optional[str] = None,
    payer: Optional[str] = None,
    amount: Optional[float] = None,
    note: Optional[str] = None,
) -> None:
    """
    Apply a manual edit to a transaction.

    Also writes to padroes_aprendidos and auto-generates a keyword rule so
    the same transaction is classified correctly on future imports.

    Raises ``ValueError`` if *tx_id* does not exist.
    """
    from ai.custom_rule_engine import upsert_rule_from_manual_edit

    conn = connect()
    c = conn.cursor()
    try:
        c.execute(
            """
            SELECT raw_description, description, amount, note, category, payer
            FROM transactions WHERE id = ?
            """,
            (int(tx_id),),
        )
        row = c.fetchone()
        if row is None:
            raise ValueError(f"Transaction {tx_id} not found")

        raw = str(row[0] or row[1] or "").strip()
        final_desc = capitalize_first(
            (description if description is not None else str(row[1] or raw)).strip() or raw
        )
        final_category = normalize_category(
            category if category is not None else str(row[4] or "")
        ) or "outros"
        final_payer = normalize_payer(payer if payer is not None else str(row[5] or ""))
        final_amount = float(amount if amount is not None else row[2] or 0.0)
        final_note = str(note if note is not None else row[3] or "").strip()
        normalized = normalize_description(raw or final_desc) or ""

        c.execute(
            """
            UPDATE transactions
            SET description = ?, description_ai = ?, cleaned_description = ?,
                category = ?, category_ai = ?, payer = ?, amount = ?, note = ?,
                normalized_description = ?,
                classification_source = 'manual',
                confidence = 1.0, ai_confidence = 1.0,
                ai_updated_at = ?
            WHERE id = ?
            """,
            (
                final_desc, final_desc, final_desc,
                final_category, final_category,
                final_payer, final_amount, final_note,
                normalized,
                datetime.now().isoformat(),
                int(tx_id),
            ),
        )

        ensure_patterns_table(conn)
        upsert_pattern(normalized, final_desc, final_category, final_payer, conn)
        upsert_rule_from_manual_edit(
            original_description=raw or final_desc,
            description_final=final_desc,
            category=final_category,
        )

        conn.commit()
    finally:
        conn.close()


def set_transaction_recurring(transaction_id: int, group_name: str) -> None:
    """Mark a transaction as recurring and optionally re-classify it via custom rules."""
    from ai.custom_rule_engine import apply_custom_rule

    conn = connect()
    c = conn.cursor()
    try:
        c.execute(
            """
            UPDATE transactions
            SET is_recurring = 1, recurrence_group_id = ?, recurrence_confidence = 1.0
            WHERE id = ?
            """,
            (group_name, transaction_id),
        )

        c.execute(
            "SELECT cleaned_description, raw_description, amount FROM transactions WHERE id = ?",
            (transaction_id,),
        )
        row = c.fetchone()
        if row:
            desc = str(row[0] or row[1] or "")
            amt = float(row[2] or 0.0)
            result = apply_custom_rule(description=desc, amount=amt, is_recurring=True)
            if result is not None:
                custom_cat, custom_conf = result
                norm_cat = normalize_category(custom_cat) or "outros"
                norm_conf = normalize_confidence(float(custom_conf), "rule")
                c.execute(
                    """
                    UPDATE transactions
                    SET category = ?, category_ai = ?,
                        confidence = ?, ai_confidence = ?,
                        classification_source = 'rule'
                    WHERE id = ?
                    """,
                    (norm_cat, norm_cat, norm_conf, norm_conf, transaction_id),
                )

        conn.commit()
    finally:
        conn.close()


def reprocess_all_with_history() -> int:
    """
    Re-classify low-confidence transactions using the rule engine and
    TF-IDF history classifier.

    Returns the number of rows updated.
    """
    from ai.history_classifier import HistoryBasedClassifier
    from ai.rule_engine import apply_rules

    conn = connect()
    c = conn.cursor()
    try:
        c.execute(
            """
            SELECT id, raw_description, cleaned_description, description, amount
            FROM transactions
            WHERE classification_source != 'manual'
              AND (
                    classification_source = 'fallback'
                    OR COALESCE(confidence, 0.0) < 0.6
                  )
            """
        )
        rows = c.fetchall()

        classifier = HistoryBasedClassifier(DB_PATH)
        classifier.build_index()
        updated = 0

        for row in rows:
            tx_id = int(row[0])
            raw = str(row[1] or row[3] or "").strip()
            clean = str(row[2] or raw).strip()
            if not raw:
                continue

            rule_result = apply_rules(raw, float(row[4] or 0.0))
            if rule_result is not None:
                r_desc, r_cat, r_payer, r_conf = rule_result
                c.execute(
                    """
                    UPDATE transactions
                    SET category = ?, payer = ?, confidence = ?,
                        classification_source = 'rule',
                        cleaned_description = COALESCE(?, cleaned_description)
                    WHERE id = ?
                    """,
                    (
                        normalize_category(r_cat),
                        normalize_payer(r_payer),
                        normalize_confidence(float(r_conf), "rule"),
                        r_desc,
                        tx_id,
                    ),
                )
                updated += 1
                continue

            pred = classifier.predict(clean)
            if pred is None:
                continue
            pred_cat, pred_payer, pred_conf = pred
            c.execute(
                """
                UPDATE transactions
                SET category = ?, payer = ?, confidence = ?,
                    classification_source = 'history'
                WHERE id = ?
                """,
                (
                    normalize_category(pred_cat),
                    normalize_payer(pred_payer),
                    normalize_confidence(float(pred_conf), "history"),
                    tx_id,
                ),
            )
            updated += 1

        conn.commit()
        return updated
    finally:
        conn.close()


def get_transactions(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 10_000,
) -> list[dict[str, Any]]:
    """
    Fetch transactions ordered by date descending.

    Optional *start_date* / *end_date* filter as ISO date strings.
    """
    conn = connect()
    c = conn.cursor()
    try:
        params: list[Any] = []
        where_clauses: list[str] = []

        if start_date:
            where_clauses.append("date >= ?")
            params.append(start_date)
        if end_date:
            where_clauses.append("date <= ?")
            params.append(end_date)

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        params.append(limit)

        c.execute(
            f"""
            SELECT id, date,
                   COALESCE(cleaned_description, description) AS description,
                   raw_description,
                   COALESCE(category_ai, category) AS category,
                   payer, amount, note, is_recurring, recurrence_group_id,
                   classification_source, confidence
            FROM transactions
            {where_sql}
            ORDER BY date DESC, id DESC
            LIMIT ?
            """,
            params,
        )
        rows = c.fetchall()
        return [
            {
                "id": int(row[0]),
                "date": str(row[1] or ""),
                "description": str(row[2] or ""),
                "raw_description": str(row[3] or ""),
                "category": str(row[4] or "outros"),
                "payer": str(row[5] or ""),
                "amount": float(row[6] or 0.0),
                "note": str(row[7] or ""),
                "is_recurring": bool(row[8]),
                "recurrence_group_id": str(row[9] or ""),
                "classification_source": str(row[10] or ""),
                "confidence": float(row[11] or 0.0),
            }
            for row in rows
        ]
    finally:
        conn.close()
