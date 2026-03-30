"""
Deterministic import UID generation for deduplication.

The UID is derived only from content-stable fields so that reimporting the
same CSV always yields the same UIDs — making re-import a true no-op.
"""

from __future__ import annotations

import hashlib
from datetime import date


def build_import_uid(
    normalized_description: str,
    date_iso: str,
    amount: float,
) -> str:
    """
    Return a SHA-1 hex digest that uniquely identifies a transaction.

    Uses normalized_description + date + amount only (no source file, no
    account name, no occurrence counter) so the UID is stable across multiple
    CSV exports of the same statement.
    """
    key = f"{normalized_description.strip()}|{date_iso}|{amount:.2f}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def build_import_uid_from_date(
    normalized_description: str,
    tx_date: date,
    amount: float,
) -> str:
    """Convenience overload that accepts a ``date`` object instead of ISO string."""
    return build_import_uid(normalized_description, tx_date.isoformat(), amount)
