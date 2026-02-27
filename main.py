from pathlib import Path
import sys

from ai.recurrence_engine import detect_recurring_transactions
from classifier import classify
from db import connect, init_db, insert_transaction
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

    for t in transactions:
        classify(t)
        insert_transaction(t)

    conn = connect()
    detect_recurring_transactions(conn)
    conn.close()

    print(f"{len(transactions)} transacoes importadas com sucesso.")


if __name__ == "__main__":
    main()
