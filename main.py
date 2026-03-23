from pathlib import Path
import sys

from ai.recurrence_engine import detect_recurring_transactions
from core.db import connect, init_db, insert_transaction
from importers.inter_csv import parse_inter_csv


def _resolve_csv_path() -> str:
    if len(sys.argv) > 1:
        return sys.argv[1]

    default = "extrato_inter.csv"
    if Path(default).exists():
        return default

    csv_files = sorted(Path(".").glob("*.csv"))
    if len(csv_files) == 1:
        return str(csv_files[0])

    raise FileNotFoundError(
        "Informe o caminho do CSV como argumento ou deixe apenas um .csv na pasta."
    )


def main():
    init_db()

    file_path = _resolve_csv_path()
    transactions = parse_inter_csv(file_path)
    inserted = 0

    for t in transactions:
        if insert_transaction(t):
            inserted += 1

    conn = connect()
    detect_recurring_transactions(conn)
    conn.close()

    skipped = len(transactions) - inserted
    print(
        f"Importação concluída: {inserted} transações adicionadas, "
        f"{skipped} ignoradas (duplicadas)."
    )


if __name__ == "__main__":
    main()
