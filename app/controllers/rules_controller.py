from __future__ import annotations

import uuid

from ai.custom_rule_engine import add_custom_rule, delete_custom_rule, load_custom_rules


class RulesController:
    def list_rules(self) -> list[dict]:
        return load_custom_rules()

    def create_rule(
        self,
        description_contains: str,
        amount_min_text: str,
        amount_max_text: str,
        recurring_option: str,
        set_category: str,
    ) -> tuple[bool, str]:
        try:
            amount_min = float(amount_min_text) if amount_min_text.strip() else None
            amount_max = float(amount_max_text) if amount_max_text.strip() else None

            is_recurring = None
            normalized_recurring = recurring_option.strip().lower()
            if normalized_recurring == "sim":
                is_recurring = True
            elif normalized_recurring in {"nao", "não"}:
                is_recurring = False

            rule = {
                "id": f"rule_{uuid.uuid4().hex[:8]}",
                "description_contains": description_contains.strip() or None,
                "amount_min": amount_min,
                "amount_max": amount_max,
                "is_recurring": is_recurring,
                "set_category": set_category.strip() or None,
            }
            add_custom_rule(rule)
            return True, "Regra criada com sucesso."
        except ValueError:
            return False, "Valor mínimo/máximo inválido."
        except Exception as exc:
            return False, f"Erro ao criar regra: {exc}"

    def remove_rule(self, rule_id: str) -> tuple[bool, str]:
        rid = (rule_id or "").strip()
        if not rid:
            return False, "Selecione uma regra para excluir."

        try:
            delete_custom_rule(rid)
            return True, "Regra excluída com sucesso."
        except Exception as exc:
            return False, f"Erro ao excluir regra: {exc}"
