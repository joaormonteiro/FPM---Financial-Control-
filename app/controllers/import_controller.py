"""Import controller – orchestrates CSV parsing and DB insertion."""

from __future__ import annotations

from ai.recurrence_engine import detect_recurring_transactions
from core.db import connect, insert_transaction
from importers.inter_csv import parse_inter_csv


class ImportController:
    """Handles CSV import workflow including recurrence detection."""

    def import_csv(self, file_path: str) -> tuple[bool, str, int, int]:
        """
        Parse *file_path* and insert new transactions.

        Returns:
            (success, message, inserted_count, skipped_count)
        """
        if not file_path or not file_path.strip():
            return False, "Selecione um arquivo CSV.", 0, 0

        try:
            transactions = parse_inter_csv(file_path)
            inserted = 0
            for t in transactions:
                if insert_transaction(t):
                    inserted += 1

            conn = connect()
            try:
                detect_recurring_transactions(conn)
            finally:
                conn.close()

            skipped = len(transactions) - inserted
            msg = (
                f"Importação concluída: {inserted} transações adicionadas, "
                f"{skipped} ignoradas (duplicadas)."
            )
            return True, msg, inserted, skipped
        except Exception as exc:
            return False, f"Erro na importação: {exc}", 0, 0

    def preview_csv(self, file_path: str, max_rows: int = 10) -> list[dict]:
        """
        Parse *file_path* and return the first *max_rows* as plain dicts for
        preview – does NOT write to the database.
        """
        if not file_path or not file_path.strip():
            return []
        try:
            transactions = parse_inter_csv(file_path)
            preview = []
            for t in transactions[:max_rows]:
                preview.append(
                    {
                        "date": t.date.strftime("%d/%m/%Y"),
                        "description": t.raw_description,
                        "amount": t.amount,
                        "category": t.category or "outros",
                    }
                )
            return preview
        except Exception:
            return []
