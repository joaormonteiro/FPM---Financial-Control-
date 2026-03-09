from __future__ import annotations

from datetime import date, datetime
from sqlite3 import Row

from ai.description_normalizer import normalize_description
from db import connect, insert_transaction, set_transaction_recurring, update_transaction_manual
from models import Transaction


class TransactionController:
    def list_transactions(self) -> list[dict]:
        conn = connect()
        conn.row_factory = Row
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                id,
                date,
                COALESCE(description_ai, description) AS description,
                COALESCE(category_ai, category) AS category,
                payer,
                amount,
                note,
                is_recurring,
                recurrence_group_id
            FROM transactions
            ORDER BY date DESC, id DESC
            """
        )
        rows = cur.fetchall()
        conn.close()

        return [
            {
                "id": int(row["id"]),
                "date": str(row["date"] or ""),
                "description": str(row["description"] or ""),
                "category": str(row["category"] or "outros"),
                "payer": str(row["payer"] or ""),
                "amount": float(row["amount"] or 0.0),
                "note": str(row["note"] or ""),
                "is_recurring": bool(row["is_recurring"]),
                "recurrence_group_id": str(row["recurrence_group_id"] or ""),
            }
            for row in rows
        ]

    def update_transaction(
        self,
        tx_id: int,
        description: str,
        category: str,
        payer: str | None,
        amount: float,
        note: str | None,
    ) -> None:
        update_transaction_manual(
            tx_id=int(tx_id),
            description=description,
            category=category,
            payer=payer,
            amount=amount,
            note=note,
        )

    def mark_recurring(self, tx_id: int, group_name: str) -> None:
        set_transaction_recurring(int(tx_id), group_name.strip())

    def add_manual_transaction(
        self,
        tx_date: date,
        description: str,
        amount: float,
        category: str,
        is_recurring: bool,
    ) -> tuple[bool, str]:
        try:
            clean_description = (description or "").strip()
            if not clean_description:
                return False, "Descricao e obrigatoria."

            tx_type = "debit" if float(amount) < 0 else "credit"
            tx = Transaction(
                date=tx_date,
                raw_description=clean_description,
                description=clean_description,
                amount=float(amount),
                account="Manual",
                type=tx_type,
                category=category,
                payer="eu",
                source_file="manual_entry",
                normalized_description=normalize_description(clean_description),
                cleaned_description=clean_description,
                classification_source="manual",
                confidence=1.0,
                is_recurring=1 if is_recurring else 0,
                ai_confidence=1.0,
                description_ai=clean_description,
                category_ai=category,
                ai_updated_at=datetime.now().isoformat(),
            )
            insert_transaction(tx)

            if is_recurring:
                conn = connect()
                cur = conn.cursor()
                cur.execute("SELECT MAX(id) AS id FROM transactions")
                row = cur.fetchone()
                conn.close()
                if row and row[0] is not None:
                    set_transaction_recurring(int(row[0]), f"manual_{int(row[0])}")

            return True, "Lancamento manual adicionado com sucesso."
        except Exception as exc:
            return False, f"Erro ao adicionar lancamento manual: {exc}"
