"""
Backward-compatibility shim.

All logic has moved to core/db/patterns.py.  Importing from this module
continues to work without changes.
"""

from core.db.patterns import (
    ensure_learned_patterns_table,
    get_learned_pattern,
    upsert_learned_pattern,
)

__all__ = [
    "ensure_learned_patterns_table",
    "get_learned_pattern",
    "upsert_learned_pattern",
]
