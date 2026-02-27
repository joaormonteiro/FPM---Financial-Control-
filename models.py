from dataclasses import dataclass
from datetime import date
from typing import Optional


ALLOWED_CLASSIFICATION_SOURCES = {"manual", "rule", "heuristic"}

ALLOWED_CATEGORIES = [
    "Transporte",
    "Alimentação",
    "Saúde",
    "Lazer",
    "Outros",
]

ALLOWED_PAYERS = [
    "Joao",
    "Pais",
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

    # Consolidacao Fase 2
    cleaned_description: Optional[str] = None
    classification_source: str = "heuristic"
    confidence: Optional[float] = None
    is_recurring: int = 0

    # Campos opcionais com default (deve vir por ultimo)
    id: Optional[int] = None
    imported_at: Optional[str] = None
    description_ai: Optional[str] = None
    category_ai: Optional[str] = None
    ai_confidence: Optional[float] = None
    ai_updated_at: Optional[str] = None
