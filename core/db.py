from collections import defaultdict
import sqlite3
import unicodedata
from datetime import datetime

from core.import_uid import build_import_uid, canonical_source_name
from ai.custom_rule_engine import upsert_rule_from_manual_edit
from ai.description_normalizer import normalize_description
from ai.learned_patterns import ensure_learned_patterns_table, upsert_learned_pattern
from core.models import (
    ALLOWED_CATEGORIES,
    ALLOWED_CLASSIFICATION_SOURCES,
    ALLOWED_PAYERS,
    Transaction,
    capitalize_first,
)
from core.settings import DB_PATH


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


def _to_key(value: str) -> str:
    return (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
        .strip()
        .lower()
    )


_LEGACY_CATEGORY_MAP = {
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
    "outro": "outros",
    "outros": "outros",
}

_LEGACY_PAYER_MAP = {
    "joao": "eu",
    "eu": "eu",
    "pais": "pais",
}


def _normalize_source(source: str | None) -> str:
    allowed_sources = set(ALLOWED_CLASSIFICATION_SOURCES)
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
    key = _to_key(value)
    if not key:
        return None
    normalized = _LEGACY_CATEGORY_MAP.get(key, key)
    if normalized in ALLOWED_CATEGORIES:
        return normalized
    return "outros"


def _normalize_payer(value: str | None) -> str | None:
    if value is None:
        return None
    key = _to_key(value)
    if not key:
        return None
    normalized = _LEGACY_PAYER_MAP.get(key, key)
    if normalized in ALLOWED_PAYERS:
        return normalized
    return None



def _deduplicate_reimported_rows(conn: sqlite3.Connection) -> int:
    """
    Remove apenas duplicacoes com evidencia forte de reimportacao:
    - mesmo registro em multiplos caminhos de source_file, ou
    - mesmo registro importado em dias diferentes.
    """
    c = conn.cursor()
    c.execute(
        """
        SELECT
            id,
            date,
            raw_description,
            amount,
            account,
            type,
            COALESCE(source_file, ''),
            COALESCE(imported_at, '')
        FROM transactions
        WHERE COALESCE(source_file, '') <> 'manual_entry'
          AND import_uid IS NULL
        ORDER BY id ASC
        """
    )
    rows = c.fetchall()

    groups: dict[tuple, list[tuple[int, str, str, str]]] = defaultdict(list)
    source_updates: list[tuple[str, int]] = []

    for tx_id, date_text, raw_description, amount, account, tx_type, source_file, imported_at in rows:
        canonical_source = canonical_source_name(source_file) if source_file else ""
        if source_file and source_file != canonical_source:
            source_updates.append((canonical_source, int(tx_id)))

        key = (
            canonical_source.lower(),
            str(date_text or ""),
            str(raw_description or ""),
            float(amount or 0.0),
            str(account or ""),
            str(tx_type or ""),
        )
        groups[key].append(
            (
                int(tx_id),
                str(source_file or ""),
                str(imported_at or ""),
                canonical_source,
            )
        )

    if source_updates:
        c.executemany(
            "UPDATE transactions SET source_file = ? WHERE id = ?",
            source_updates,
        )

    ids_to_delete: list[tuple[int]] = []
    for items in groups.values():
        if len(items) <= 1:
            continue

        source_paths = {item[1] for item in items}
        import_days = {item[2][:10] for item in items if item[2]}

        # Critério conservador: remove apenas quando há sinal claro de reimport.
        if len(source_paths) <= 1 and len(import_days) <= 1:
            continue

        # Mantem o primeiro registro (menor id) e remove os demais.
        for tx_id, _, _, _ in items[1:]:
            ids_to_delete.append((tx_id,))

    if ids_to_delete:
        c.executemany("DELETE FROM transactions WHERE id = ?", ids_to_delete)

    return len(ids_to_delete)


def _backfill_import_uids(conn: sqlite3.Connection) -> int:
    c = conn.cursor()
    c.execute(
        """
        SELECT
            id,
            date,
            raw_description,
            amount,
            account,
            type,
            COALESCE(source_file, '')
        FROM transactions
        WHERE COALESCE(source_file, '') <> 'manual_entry'
          AND import_uid IS NULL
        ORDER BY id ASC
        """
    )
    rows = c.fetchall()
    if not rows:
        return 0

    occurrence_map: dict[tuple[str, str, str, str, str], int] = defaultdict(int)
    updates: list[tuple[str, int]] = []
    for tx_id, date_text, raw_description, amount, account, tx_type, source_file in rows:
        source_name = canonical_source_name(source_file) if source_file else ""
        if not source_name:
            continue

        key = (
            source_name.lower(),
            str(date_text or ""),
            str(raw_description or ""),
            f"{float(amount or 0.0):.2f}",
            str(account or ""),
            str(tx_type or ""),
        )
        occurrence_map[key] += 1
        import_uid = build_import_uid(
            source_name=source_name,
            date_iso=key[1],
            raw_description=key[2],
            amount=float(amount or 0.0),
            account=key[4],
            tx_type=key[5],
            occurrence=occurrence_map[key],
        )
        updates.append((import_uid, int(tx_id)))

    if updates:
        c.executemany(
            "UPDATE transactions SET import_uid = ? WHERE id = ?",
            updates,
        )
    return len(updates)


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
            note TEXT,
            source_file TEXT,
            import_uid TEXT,
            imported_at TEXT,
            description_ai TEXT,
            category_ai TEXT,
            ai_confidence REAL,
            ai_updated_at TEXT,
            confidence REAL,
            raw_description TEXT NOT NULL DEFAULT '',
            normalized_description TEXT,
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
        "note": "TEXT",
        "source_file": "TEXT",
        "import_uid": "TEXT",
        "imported_at": "TEXT",
        "description_ai": "TEXT",
        "category_ai": "TEXT",
        "ai_confidence": "REAL",
        "ai_updated_at": "TEXT",
        "confidence": "REAL",
        "raw_description": "TEXT NOT NULL DEFAULT ''",
        "normalized_description": "TEXT",
        "cleaned_description": "TEXT",
        "classification_source": "TEXT NOT NULL DEFAULT 'heuristic'",
        "is_recurring": "INTEGER NOT NULL DEFAULT 0",
        "recurrence_group_id": "TEXT",
        "recurrence_confidence": "REAL",
    }

    for column, column_type in required_columns.items():
        _add_column_if_missing(conn, "transactions", column, column_type)

    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_transactions_import_uid
        ON transactions(import_uid)
        WHERE import_uid IS NOT NULL
        """
    )

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
            confidence = COALESCE(confidence, ai_confidence, 0.0),
            note = COALESCE(note, ''),
            normalized_description = COALESCE(
                normalized_description,
                cleaned_description,
                raw_description,
                description
            )
        """
    )

    c.execute(
        """
        SELECT id, category, category_ai, payer, raw_description, description, normalized_description
        FROM transactions
        """
    )
    rows = c.fetchall()

    for tx_id, category, category_ai, payer, raw_description, description, normalized_description in rows:
        normalized_category = _normalize_category(category)
        normalized_category_ai = _normalize_category(category_ai)
        normalized_payer = _normalize_payer(payer)
        normalized_desc = normalize_description(
            str(raw_description or description or normalized_description or "")
        )
        c.execute(
            """
            UPDATE transactions
            SET category = ?,
                category_ai = ?,
                payer = ?,
                normalized_description = ?
            WHERE id = ?
            """,
            (
                normalized_category,
                normalized_category_ai,
                normalized_payer,
                normalized_desc,
                int(tx_id),
            ),
        )

    ensure_learned_patterns_table(conn)

    _deduplicate_reimported_rows(conn)
    _backfill_import_uids(conn)

    conn.commit()
    conn.close()


def insert_transaction(t: Transaction) -> bool:
    conn = connect()
    c = conn.cursor()

    raw_description = (t.raw_description or "").strip()
    if not raw_description:
        conn.close()
        raise ValueError("raw_description não pode ser vazio")

    import_uid = (t.import_uid or "").strip() or None
    if import_uid is not None:
        c.execute("SELECT 1 FROM transactions WHERE import_uid = ? LIMIT 1", (import_uid,))
        if c.fetchone() is not None:
            conn.close()
            return False

    imported_at = t.imported_at or datetime.now().isoformat()
    cleaned_description = capitalize_first(
        (t.cleaned_description or t.description_ai or t.description or raw_description).strip()
    )
    description = capitalize_first((t.description or raw_description).strip())
    description_ai = capitalize_first((t.description_ai or cleaned_description or description).strip())
    normalized_description = (t.normalized_description or normalize_description(raw_description)).strip()
    note = (t.note or "").strip()
    source_file = canonical_source_name(t.source_file) if t.source_file else ""

    classification_source = _normalize_source(t.classification_source)
    confidence_value = t.confidence if t.confidence is not None else t.ai_confidence
    confidence = _normalize_confidence(confidence_value, classification_source)

    category = _normalize_category(t.category)
    payer = _normalize_payer(t.payer)
    category_ai = _normalize_category(t.category_ai or category)
    if category is None and payer is None:
        classification_source = "heuristic"
        confidence = 0.0

    ai_updated_at = t.ai_updated_at
    if ai_updated_at is None and t.ai_confidence is not None:
        ai_updated_at = datetime.now().isoformat()

    c.execute(
        """
        INSERT INTO transactions
        (date, description, amount, account, type, category, payer, note, source_file, import_uid,
         imported_at, description_ai, category_ai, ai_confidence, ai_updated_at,
         confidence, raw_description, normalized_description, cleaned_description, classification_source, is_recurring,
         recurrence_group_id, recurrence_confidence)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            t.date.isoformat(),
            description,
            t.amount,
            t.account,
            t.type,
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
            raw_description,
            normalized_description,
            cleaned_description,
            classification_source,
            1 if t.is_recurring else 0,
            None,
            None,
        ),
    )

    conn.commit()
    conn.close()
    return True


def update_transaction_manual(
    tx_id: int,
    category: str | None = None,
    payer: str | None = None,
    description: str | None = None,
    amount: float | None = None,
    note: str | None = None,
) -> None:
    conn = connect()
    c = conn.cursor()

    c.execute(
        """
        SELECT raw_description, description, amount, note, category, payer
        FROM transactions
        WHERE id = ?
        """,
        (int(tx_id),),
    )
    row = c.fetchone()
    if row is None:
        conn.close()
        raise ValueError(f"Transação {tx_id} não encontrada.")

    raw_description, current_description, current_amount, current_note, current_category, current_payer = row
    final_description = (description if description is not None else current_description or raw_description or "").strip()
    if not final_description:
        final_description = str(raw_description or "").strip()
    final_description = capitalize_first(final_description)

    final_category = _normalize_category(category if category is not None else current_category) or "outros"
    final_payer = _normalize_payer(payer if payer is not None else current_payer)
    source_amount = current_amount if amount is None else amount
    final_amount = float(source_amount or 0.0)
    final_note = (current_note if note is None else note) or ""
    final_note = str(final_note).strip()
    normalized_description = normalize_description(str(raw_description or final_description or ""))

    c.execute(
        """
        UPDATE transactions
        SET description = ?,
            description_ai = ?,
            cleaned_description = ?,
            category = ?,
            category_ai = ?,
            payer = ?,
            amount = ?,
            note = ?,
            normalized_description = ?,
            classification_source = 'manual',
            confidence = 1.0,
            ai_confidence = 1.0,
            ai_updated_at = ?
        WHERE id = ?
        """,
        (
            final_description,
            final_description,
            final_description,
            final_category,
            final_category,
            final_payer,
            final_amount,
            final_note,
            normalized_description,
            datetime.now().isoformat(),
            int(tx_id),
        ),
    )

    ensure_learned_patterns_table(conn)
    upsert_learned_pattern(
        descricao_normalizada=normalized_description,
        descricao_editada_usuario=final_description,
        categoria=final_category,
        pagador=final_payer,
        conn=conn,
    )
    upsert_rule_from_manual_edit(
        original_description=str(raw_description or final_description or ""),
        description_final=final_description,
        category=final_category,
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
