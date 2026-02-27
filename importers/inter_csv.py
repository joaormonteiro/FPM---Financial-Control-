import csv
import re
from datetime import datetime

from ai.ai_engine import enhance_transaction
from models import Transaction

DATE_RE = re.compile(r"\d{2}/\d{2}/\d{4}")


def is_date(text: str) -> bool:
    return bool(DATE_RE.fullmatch(text.strip()))


def _get_field(row: dict, candidates: list[str]) -> str | None:
    for key in candidates:
        if key in row and row[key] is not None:
            return row[key]
    return None


def _read_lines_with_fallback(path: str) -> list[str]:
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            return f.readlines()
    except UnicodeDecodeError:
        with open(path, encoding="latin-1", newline="") as f:
            return f.readlines()


def parse_inter_csv(path: str):
    """
    Faz o parsing de um CSV exportado do Banco Inter e converte
    cada linha valida em um objeto Transaction.
    """
    transactions = []
    lines = _read_lines_with_fallback(path)

    header_index = None
    for i in range(len(lines) - 1):
        parts = lines[i].split(";")
        next_parts = lines[i + 1].split(";")
        if len(parts) >= 4 and len(next_parts) >= 4 and is_date(next_parts[0]):
            header_index = i
            break

    if header_index is None:
        raise Exception(
            "Nao foi possivel detectar a tabela de transacoes no CSV do Inter."
        )

    reader = csv.DictReader(lines[header_index:], delimiter=";")

    date_keys = ["Data Lancamento", "Data Lançamento", "Data"]
    desc_keys = ["Descricao", "Descrição", "Historico", "Histórico"]
    amount_keys = ["Valor", "Valor (R$)"]

    for row in reader:
        date_str = _get_field(row, date_keys)
        if not date_str or not is_date(date_str):
            continue

        raw_description = (_get_field(row, desc_keys) or "").strip()
        if not raw_description:
            continue

        amount_str = (_get_field(row, amount_keys) or "").strip()
        if not amount_str:
            continue

        amount = float(
            amount_str.replace("R$", "")
            .replace(" ", "")
            .replace(".", "")
            .replace(",", ".")
        )

        ttype = "debit" if amount < 0 else "credit"

        cleaned_description, category, payer, confidence, classification_source = enhance_transaction(
            raw_description,
            amount,
        )

        t = Transaction(
            date=datetime.strptime(date_str, "%d/%m/%Y").date(),
            raw_description=raw_description,
            description=raw_description,
            amount=amount,
            account="Inter",
            type=ttype,
            category=category,
            payer=payer,
            source_file=path,
            cleaned_description=cleaned_description,
            classification_source=classification_source,
            confidence=confidence,
            is_recurring=0,
            ai_confidence=confidence,
            description_ai=cleaned_description,
            category_ai=category,
            ai_updated_at=datetime.now().isoformat(),
        )

        transactions.append(t)

    return transactions
