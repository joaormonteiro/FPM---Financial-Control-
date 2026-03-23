import hashlib
from pathlib import Path


def canonical_source_name(source_name: str | None) -> str:
    normalized = (source_name or "").strip().replace("\\", "/")
    if not normalized:
        return "inter.csv"
    return Path(normalized).name.strip() or "inter.csv"


def build_import_uid(
    source_name: str,
    date_iso: str,
    raw_description: str,
    amount: float,
    account: str,
    tx_type: str,
    occurrence: int,
) -> str:
    payload = "|".join(
        [
            source_name.lower(),
            date_iso,
            (raw_description or "").strip(),
            f"{float(amount):.2f}",
            (account or "").strip(),
            (tx_type or "").strip(),
            str(int(occurrence)),
        ]
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()
