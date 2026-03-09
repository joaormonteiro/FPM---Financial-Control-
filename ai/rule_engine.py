import json
import os
from functools import lru_cache
from typing import Optional, Tuple

KNOWLEDGE_BASE_PATH = os.path.join(
    os.path.dirname(__file__),
    "knowledge_base.json",
)


@lru_cache(maxsize=1)
def _load_knowledge_base():
    """
    Carrega o arquivo JSON de regras para memoria.
    """
    with open(KNOWLEDGE_BASE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _normalize(text: str) -> str:
    return text.lower().strip()


def _amount_matches(amount: float, rule: dict) -> bool:
    abs_amount = abs(amount)

    if "amounts" in rule:
        return abs_amount in rule["amounts"]

    if "amount_range" in rule:
        min_v, max_v = rule["amount_range"]
        return min_v <= abs_amount <= max_v

    if "max_amount" in rule:
        return abs_amount <= rule["max_amount"]

    if "approx_amount" in rule:
        target = rule["approx_amount"]
        return abs(abs_amount - target) <= 1.0

    return True


def apply_rules(raw_description: str, amount: float) -> Optional[Tuple[str, str, str, float]]:
    """
    Aplica regras deterministicas baseadas no knowledge_base.json.

    Retorno (quando ha match):
    (description, category, payer, confidence)

    Retorna None se nenhuma regra for aplicada.
    """
    kb = _load_knowledge_base()
    desc_norm = _normalize(raw_description)

    people = kb.get("people", {})

    for _, rules in people.items():
        aliases = rules.get("aliases", [])

        matched_alias = False
        for alias in aliases:
            if _normalize(alias) in desc_norm:
                matched_alias = True
                break

        if not matched_alias:
            continue

        if "conditional_rules" in rules:
            for cond in rules["conditional_rules"]:
                if _amount_matches(amount, cond):
                    return (
                        cond.get("description", raw_description),
                        cond.get("category", "outros"),
                        cond.get("payer", "eu"),
                        0.95,
                    )

        if not _amount_matches(amount, rules):
            continue

        description = rules.get("description", raw_description)
        category = rules.get("category", "outros")
        payer = rules.get("payer", "eu")

        return description, category, payer, 0.95

    return None
