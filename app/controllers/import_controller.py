from __future__ import annotations

from ai.recurrence_engine import detect_recurring_transactions
from core.db import connect, insert_transaction
from importers.inter_csv import parse_inter_csv


class ImportController:
    def import_csv(self, file_path: str) -> tuple[bool, str, int]:
        if not file_path or not file_path.strip():
            return False, "Selecione um arquivo CSV.", 0

        try:
            transactions = parse_inter_csv(file_path)
            inserted = 0
            for transaction in transactions:
                if insert_transaction(transaction):
                    inserted += 1

            conn = connect()
            try:
                detect_recurring_transactions(conn)
            finally:
                conn.close()

            skipped = len(transactions) - inserted
            return (
                True,
                f"Importação concluída: {inserted} transações adicionadas, {skipped} ignoradas (duplicadas).",
                inserted,
            )
        except Exception as exc:
            return False, f"Erro na importação: {exc}", 0
