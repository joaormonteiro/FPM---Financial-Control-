from dataclasses import dataclass
from datetime import date
from typing import Optional


ALLOWED_CLASSIFICATION_SOURCES = {
    "manual",
    "rule",
    "heuristic",
    "history",
    "pattern",
    "gemini",
    "fallback",
}

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

ALLOWED_PAYERS = [
    "eu",
    "pais",
]


@dataclass
class Transaction:
    # Campos obrigatorios (sempre primeiro)
    date: date
    raw_description: str
    description: str
    amount: float
    account: str
    type: str

    # Campos opcionais sem default
    category: Optional[str] = None
    payer: Optional[str] = None
    source_file: Optional[str] = None
    import_uid: Optional[str] = None

    # Consolidacao Fase 2
    normalized_description: Optional[str] = None
    cleaned_description: Optional[str] = None
    classification_source: str = "heuristic"
    confidence: Optional[float] = None
    is_recurring: int = 0
    note: Optional[str] = None

    # Campos opcionais com default (deve vir por ultimo)
    id: Optional[int] = None
    imported_at: Optional[str] = None
    description_ai: Optional[str] = None
    category_ai: Optional[str] = None
    ai_confidence: Optional[float] = None
    ai_updated_at: Optional[str] = None
