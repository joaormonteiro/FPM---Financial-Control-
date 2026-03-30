"""
Banco Inter CSV parser.

Reads the semicolon-delimited statement exported by Banco Inter, classifies
each transaction through the AI pipeline, and returns a list of Transaction
objects ready to be persisted.

The import_uid is derived solely from (normalized_description, date, amount)
so that re-importing the same CSV is always a no-op.
"""

from __future__ import annotations

import csv
import re
from datetime import datetime

from ai.ai_engine import enhance_transaction
from ai.description_normalizer import normalize_description
from core.import_uid import build_import_uid
from core.models import Transaction

_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")


def _is_date(text: str) -> bool:
    return bool(_DATE_RE.match((text or "").strip()))


def _get_field(row: dict, candidates: list[str]) -> str | None:
    for key in candidates:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _read_lines(path: str) -> list[str]:
    """Read the file trying UTF-8 first, then Latin-1."""
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            with open(path, encoding=encoding, newline="") as f:
                return f.readlines()
        except UnicodeDecodeError:
            continue
    raise OSError(f"Cannot read file with UTF-8 or Latin-1: {path}")


def _find_header_index(lines: list[str]) -> int:
    """
    Locate the header row by finding the first row whose *next* row
    starts with a valid date.
    """
    for i in range(len(lines) - 1):
        next_parts = lines[i + 1].split(";")
        if next_parts and _is_date(next_parts[0]):
            return i
    raise ValueError(
        "Could not detect the transaction table in the Inter CSV file."
    )


def parse_inter_csv(
    path: str,
    source_name: str | None = None,
) -> list[Transaction]:
    """
    Parse a Banco Inter CSV statement.

    Args:
        path:        Path to the CSV file.
        source_name: Optional label stored as ``source_file``; defaults to
                     the file's basename.

    Returns:
        A list of Transaction objects (may include items later rejected as
        duplicates by insert_transaction).
    """
    from pathlib import Path

    source_label = source_name or Path(path).name

    lines = _read_lines(path)
    header_index = _find_header_index(lines)
    reader = csv.DictReader(lines[header_index:], delimiter=";")

    date_keys = ["Data Lancamento", "Data Lançamento", "Data"]
    desc_keys = ["Descricao", "Descrição", "Historico", "Histórico"]
    amount_keys = ["Valor", "Valor (R$)"]

    transactions: list[Transaction] = []

    for row in reader:
        date_str = _get_field(row, date_keys)
        if not date_str or not _is_date(date_str):
            continue

        raw_description = _get_field(row, desc_keys) or ""
        if not raw_description:
            continue

        amount_str = _get_field(row, amount_keys) or ""
        if not amount_str:
            continue

        try:
            amount = float(
                amount_str.replace("R$", "")
                .replace(" ", "")
                .replace(".", "")
                .replace(",", ".")
            )
        except ValueError:
            continue

        try:
            tx_date = datetime.strptime(date_str, "%d/%m/%Y").date()
        except ValueError:
            continue

        tx_type = "debit" if amount < 0 else "credit"

        # Stable deduplication key: uses only content-derived fields
        normalized = normalize_description(raw_description) or raw_description.lower().strip()
        import_uid = build_import_uid(normalized, tx_date.isoformat(), amount)

        enhanced = enhance_transaction(raw_description, amount, tx_type=tx_type)
        if enhanced is None:
            # Transaction should be ignored (e.g. credit-card bill)
            continue

        (
            cleaned_description,
            category,
            payer,
            confidence,
            classification_source,
            normalized_description,
        ) = enhanced

        t = Transaction(
            date=tx_date,
            raw_description=raw_description,
            description=raw_description,
            amount=amount,
            account="Inter",
            type=tx_type,
            category=category,
            payer=payer,
            source_file=source_label,
            import_uid=import_uid,
            normalized_description=normalized_description or normalized,
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
