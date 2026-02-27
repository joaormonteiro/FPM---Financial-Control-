from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class Transaction:
    # Campos obrigatórios (sempre primeiro)
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

    # Campos opcionais com default (deve vir por último)
    id: Optional[int] = None
    imported_at: Optional[str] = None
    description_ai: Optional[str] = None
    category_ai: Optional[str] = None
    ai_confidence: Optional[float] = None
    ai_updated_at: Optional[str] = None
