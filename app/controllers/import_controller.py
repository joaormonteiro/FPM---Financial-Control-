from __future__ import annotations

from ai.recurrence_engine import detect_recurring_transactions
from classifier import classify
from db import connect, insert_transaction
from importers.inter_csv import parse_inter_csv


class ImportController:
    def import_csv(self, file_path: str) -> tuple[bool, str, int]:
        if not file_path or not file_path.strip():
            return False, "Selecione um arquivo CSV.", 0

        try:
            transactions = parse_inter_csv(file_path)
            for transaction in transactions:
                classify(transaction)
                insert_transaction(transaction)

            conn = connect()
            try:
                detect_recurring_transactions(conn)
            finally:
                conn.close()

            total = len(transactions)
            return True, f"Importacao concluida: {total} transacoes adicionadas.", total
        except Exception as exc:
            return False, f"Erro na importacao: {exc}", 0
