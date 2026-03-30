"""Core domain models and constants for FinancialControl."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


ALLOWED_CATEGORIES = [
    "alimentacao",
    "lazer",
    "transporte",
    "educacao",
    "moradia",
    "assinaturas",
    "saude",
    "investimentos",
    "entrada",
    "outros",
]

ALLOWED_PAYERS = ["eu", "pais"]

ALLOWED_CLASSIFICATION_SOURCES = [
    "manual",
    "rule",
    "heuristic",
    "history",
    "pattern",
    "gemini",
    "ollama",
    "fallback",
]


def capitalize_first(value: Optional[str]) -> str:
    """Capitalize only the first character, preserving the rest."""
    text = str(value or "").strip()
    if not text:
        return text
    return text[:1].upper() + text[1:]


@dataclass
class Transaction:
    """Represents a single financial transaction."""

    # Required fields
    date: date
    raw_description: str
    description: str
    amount: float
    account: str
    type: str

    # Optional fields
    category: Optional[str] = "outros"
    payer: Optional[str] = None
    source_file: Optional[str] = None
    import_uid: Optional[str] = None

    normalized_description: Optional[str] = None
    cleaned_description: Optional[str] = None
    classification_source: str = "fallback"
    confidence: float = 0.4
    is_recurring: int = 0
    recurrence_group_id: Optional[str] = None
    note: Optional[str] = None

    # AI-enriched fields
    id: Optional[int] = None
    imported_at: Optional[str] = None
    description_ai: Optional[str] = None
    category_ai: Optional[str] = None
    ai_confidence: Optional[float] = None
    ai_updated_at: Optional[str] = None
