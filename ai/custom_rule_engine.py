import json
from pathlib import Path

RULES_PATH = Path(__file__).with_name("custom_rules.json")


def _ensure_rules_file() -> None:
    if not RULES_PATH.exists():
        RULES_PATH.write_text("[]", encoding="utf-8")


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
    rules = [r for r in rules if r.get("id") != rule.get("id")]
    rules.append(rule)
    save_custom_rules(rules)


def delete_custom_rule(rule_id: str) -> None:
    rules = load_custom_rules()
    rules = [r for r in rules if r.get("id") != rule_id]
    save_custom_rules(rules)


def _to_upper_text(value: str | None) -> str:
    return (value or "").strip().upper()


def apply_custom_rule(
    description: str,
    amount: float,
    is_recurring: bool | None,
) -> tuple[str, float] | None:
    desc = _to_upper_text(description)
    recurring_flag = bool(is_recurring)

    for rule in load_custom_rules():
        description_contains = _to_upper_text(rule.get("description_contains"))
        amount_min = rule.get("amount_min")
        amount_max = rule.get("amount_max")
        recurring_cond = rule.get("is_recurring")
        set_category = rule.get("set_category")

        if description_contains and description_contains not in desc:
            continue

        abs_amount = abs(float(amount))

        if amount_min is not None and abs_amount < float(amount_min):
            continue

        if amount_max is not None and abs_amount > float(amount_max):
            continue

        if recurring_cond is not None and bool(recurring_cond) != recurring_flag:
            continue

        if set_category:
            return str(set_category), 0.9

    return None
