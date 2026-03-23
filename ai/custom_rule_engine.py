from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from ai.description_normalizer import normalize_description

RULES_PATH = Path(__file__).with_name("custom_rules.json")

_NON_WORD_RE = re.compile(r"[^a-z0-9\s]")
_SPACES_RE = re.compile(r"\s+")


def _ensure_rules_file() -> None:
    if not RULES_PATH.exists():
        RULES_PATH.write_text("[]", encoding="utf-8")


def _normalize_text(value: str | None) -> str:
    text = (value or "").strip().lower()
    text = _NON_WORD_RE.sub(" ", text)
    text = _SPACES_RE.sub(" ", text).strip()
    return text


def _normalize_keywords(raw_keywords: list[str] | str) -> list[str]:
    if isinstance(raw_keywords, str):
        chunks = [item.strip() for item in raw_keywords.split(",")]
    else:
        chunks = [str(item).strip() for item in raw_keywords]

    keywords: list[str] = []
    for chunk in chunks:
        normalized = _normalize_text(chunk)
        if not normalized:
            continue
        if normalized not in keywords:
            keywords.append(normalized)
    return keywords


def _safe_priority(value: object, default: int = 100) -> int:
    try:
        return int(value)
    except Exception:
        return default


def load_custom_rules() -> list[dict]:
    _ensure_rules_file()
    try:
        data = json.loads(RULES_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def save_custom_rules(rules: list[dict]) -> None:
    RULES_PATH.write_text(
        json.dumps(rules, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def add_custom_rule(rule: dict) -> None:
    rules = load_custom_rules()
    rule_id = str(rule.get("id") or "").strip()
    if rule_id:
        rules = [r for r in rules if str(r.get("id") or "").strip() != rule_id]
    rules.append(rule)
    save_custom_rules(rules)


def delete_custom_rule(rule_id: str) -> None:
    rid = str(rule_id or "").strip()
    rules = load_custom_rules()
    rules = [r for r in rules if str(r.get("id") or "").strip() != rid]
    save_custom_rules(rules)


def create_description_rule(
    keywords: list[str] | str,
    description_final: str,
    category: str | None,
    priority: int = 100,
    rule_id: str | None = None,
    source: str = "ui",
) -> dict:
    normalized_keywords = _normalize_keywords(keywords)
    if not normalized_keywords:
        raise ValueError("Informe ao menos uma keyword válida.")

    desc_final = str(description_final or "").strip()
    if not desc_final:
        raise ValueError("Descrição final não pode ser vazia.")

    category_value = (category or "").strip().lower() or None
    priority_value = _safe_priority(priority, default=100)
    generated_id = rule_id
    if not generated_id:
        payload = "|".join(normalized_keywords + [desc_final.lower(), str(category_value or "")])
        generated_id = f"desc_{hashlib.sha1(payload.encode('utf-8')).hexdigest()[:10]}"

    rule = {
        "id": generated_id,
        "type": "description_rule",
        "keywords": normalized_keywords,
        "set_description": desc_final,
        "set_category": category_value,
        "priority": priority_value,
        "source": source,
    }
    add_custom_rule(rule)
    return rule


def upsert_rule_from_manual_edit(
    original_description: str,
    description_final: str,
    category: str | None,
) -> dict | None:
    normalized = normalize_description(original_description or "")
    tokens = [token for token in normalized.split() if token]
    if not tokens:
        return None

    keywords = tokens[:3]
    fingerprint = "|".join(keywords)
    rule_id = f"manual_{hashlib.sha1(fingerprint.encode('utf-8')).hexdigest()[:12]}"
    return create_description_rule(
        keywords=keywords,
        description_final=description_final,
        category=category,
        priority=20,
        rule_id=rule_id,
        source="manual_edit",
    )


def list_rules_for_ui() -> list[dict]:
    prepared: list[dict] = []
    for rule in load_custom_rules():
        rule_id = str(rule.get("id") or "").strip()
        if not rule_id:
            continue

        rule_type = str(rule.get("type") or "legacy").strip().lower()
        if rule_type == "description_rule":
            keywords = _normalize_keywords(rule.get("keywords") or [])
            description_final = str(rule.get("set_description") or "").strip()
            category = str(rule.get("set_category") or "").strip().lower()
            priority = _safe_priority(rule.get("priority"), default=100)
        else:
            description_contains = _normalize_text(rule.get("description_contains"))
            keywords = [description_contains] if description_contains else []
            description_final = str(rule.get("set_description") or "").strip()
            category = str(rule.get("set_category") or "").strip().lower()
            priority = _safe_priority(rule.get("priority"), default=500)

        prepared.append(
            {
                "id": rule_id,
                "type": rule_type,
                "keywords": keywords,
                "description_final": description_final,
                "category": category,
                "priority": priority,
            }
        )

    prepared.sort(key=lambda item: (int(item["priority"]), str(item["id"])))
    return prepared


def apply_description_rules(
    description: str,
    amount: float,
    tx_type: str | None = None,
    is_recurring: bool | None = None,
) -> tuple[str | None, str | None, int] | None:
    _ = tx_type
    normalized_desc = _normalize_text(description)
    abs_amount = abs(float(amount or 0.0))
    recurring_flag = bool(is_recurring)

    raw_rules = load_custom_rules()
    indexed_rules: list[tuple[int, dict]] = []
    for raw in raw_rules:
        rule_type = str(raw.get("type") or "legacy").strip().lower()
        priority = _safe_priority(raw.get("priority"), default=100 if rule_type == "description_rule" else 500)
        indexed_rules.append((priority, raw))
    indexed_rules.sort(key=lambda item: item[0])

    for priority, raw_rule in indexed_rules:
        rule_type = str(raw_rule.get("type") or "legacy").strip().lower()
        if rule_type == "description_rule":
            keywords = _normalize_keywords(raw_rule.get("keywords") or [])
            if keywords and not all(keyword in normalized_desc for keyword in keywords):
                continue
            return (
                str(raw_rule.get("set_description") or "").strip() or None,
                str(raw_rule.get("set_category") or "").strip().lower() or None,
                int(priority),
            )

        description_contains = _normalize_text(raw_rule.get("description_contains"))
        if description_contains and description_contains not in normalized_desc:
            continue

        amount_min = raw_rule.get("amount_min")
        amount_max = raw_rule.get("amount_max")
        recurring_cond = raw_rule.get("is_recurring")
        if amount_min is not None and abs_amount < float(amount_min):
            continue
        if amount_max is not None and abs_amount > float(amount_max):
            continue
        if recurring_cond is not None and bool(recurring_cond) != recurring_flag:
            continue

        return (
            str(raw_rule.get("set_description") or "").strip() or None,
            str(raw_rule.get("set_category") or "").strip().lower() or None,
            int(priority),
        )

    return None


def apply_custom_rule(
    description: str,
    amount: float,
    is_recurring: bool | None,
) -> tuple[str, float] | None:
    # Mantido para compatibilidade com recorrencia em core.db.set_transaction_recurring.
    result = apply_description_rules(
        description=description,
        amount=amount,
        is_recurring=is_recurring,
    )
    if result is None:
        return None

    _, category, _ = result
    if not category:
        return None
    return str(category), 0.9
