from __future__ import annotations

from ai.custom_rule_engine import (
    create_description_rule,
    delete_custom_rule,
    list_rules_for_ui,
)


class RulesController:
    def list_rules(self) -> list[dict]:
        return list_rules_for_ui()

    def create_rule(
        self,
        keywords_text: str,
        description_final: str,
        category: str,
        priority_text: str,
    ) -> tuple[bool, str]:
        try:
            priority = int(priority_text) if (priority_text or "").strip() else 100
            create_description_rule(
                keywords=keywords_text,
                description_final=description_final,
                category=category,
                priority=priority,
                source="ui",
            )
            return True, "Regra criada com sucesso."
        except ValueError as exc:
            return False, f"Regra inválida: {exc}"
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
