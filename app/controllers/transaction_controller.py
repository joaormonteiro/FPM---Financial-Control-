"""Transaction controller – list, manual-add, update, and mark-recurring."""

from __future__ import annotations

from datetime import date, datetime

from ai.description_normalizer import normalize_description
from core.db import connect, insert_transaction, set_transaction_recurring, update_transaction_manual
from core.db.transactions import get_transactions
from core.models import Transaction


class TransactionController:
    """CRUD operations for the transactions table."""

    def list_transactions(self) -> list[dict]:
        """Return all transactions ordered by date descending."""
        return get_transactions()

    def update_transaction(
        self,
        tx_id: int,
        description: str,
        category: str,
        payer: str | None,
        amount: float,
        note: str | None,
    ) -> None:
        """Persist a manual edit and update learned patterns."""
        update_transaction_manual(
            tx_id=int(tx_id),
            description=description,
            category=category,
            payer=payer,
            amount=amount,
            note=note,
        )

    def mark_recurring(self, tx_id: int, group_name: str) -> None:
        """Mark a transaction as recurring in the given recurrence group."""
        set_transaction_recurring(int(tx_id), group_name.strip())

    def add_manual_transaction(
        self,
        tx_date: date,
        description: str,
        amount: float,
        category: str,
        is_recurring: bool,
    ) -> tuple[bool, str]:
        """
        Insert a manually entered transaction.

        Returns (success, message).
        """
        try:
            clean = (description or "").strip()
            if not clean:
                return False, "Descrição é obrigatória."

            tx_type = "debit" if float(amount) < 0 else "credit"
            from core.import_uid import build_import_uid_from_date
            normalized = normalize_description(clean)
            uid = build_import_uid_from_date(normalized, tx_date, amount)

            t = Transaction(
                date=tx_date,
                raw_description=clean,
                description=clean,
                amount=float(amount),
                account="Manual",
                type=tx_type,
                category=category,
                payer="eu",
                source_file="manual_entry",
                import_uid=uid,
                normalized_description=normalized,
                cleaned_description=clean,
                classification_source="manual",
                confidence=1.0,
                is_recurring=1 if is_recurring else 0,
                ai_confidence=1.0,
                description_ai=clean,
                category_ai=category,
                ai_updated_at=datetime.now().isoformat(),
            )
            inserted = insert_transaction(t)

            if inserted and is_recurring:
                conn = connect()
                cur = conn.cursor()
                cur.execute("SELECT MAX(id) FROM transactions")
                row = cur.fetchone()
                conn.close()
                if row and row[0] is not None:
                    set_transaction_recurring(int(row[0]), f"manual_{int(row[0])}")

            return True, "Lançamento manual adicionado com sucesso."
        except Exception as exc:
            return False, f"Erro ao adicionar lançamento manual: {exc}"
