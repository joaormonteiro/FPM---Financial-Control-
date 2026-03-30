"""
Public API for the core.db package.

All imports that previously targeted ``core.db`` (the monolithic module)
continue to work without changes.
"""

from core.db.connection import connect, get_db
from core.db.schema import init_db, normalize_category, normalize_payer
from core.db.transactions import (
    get_transactions,
    insert_transaction,
    reprocess_all_with_history,
    set_transaction_recurring,
    update_transaction_manual,
)
from core.db.patterns import (
    ensure_patterns_table,
    get_pattern,
    upsert_pattern,
    # backward-compat aliases
    ensure_learned_patterns_table,
    get_learned_pattern,
    upsert_learned_pattern,
)

__all__ = [
    # connection
    "connect",
    "get_db",
    # schema
    "init_db",
    "normalize_category",
    "normalize_payer",
    # transactions
    "insert_transaction",
    "update_transaction_manual",
    "set_transaction_recurring",
    "reprocess_all_with_history",
    "get_transactions",
    # patterns
    "ensure_patterns_table",
    "get_pattern",
    "upsert_pattern",
    # backward-compat
    "ensure_learned_patterns_table",
    "get_learned_pattern",
    "upsert_learned_pattern",
]
