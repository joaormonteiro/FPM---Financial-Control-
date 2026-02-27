import json
from datetime import datetime
from typing import Any

from ai.llm_client import LLMClientError, call_ollama
from services.chat_functions import (
    get_category_growth,
    get_recurring_expenses,
    get_top_expenses,
    get_total_by_category,
    get_total_by_month,
)

OUT_OF_SCOPE_TEXT = "Pergunta fora do escopo das suas finanças."

FUNCTION_SCHEMAS = {
    "get_total_by_month": {
        "description": "Retorna total do mes/ano.",
        "arguments": {"month": "int", "year": "int"},
    },
    "get_total_by_category": {
        "description": "Retorna totais por categoria para mes/ano.",
        "arguments": {"month": "int|null", "year": "int"},
    },
    "get_top_expenses": {
        "description": "Retorna maiores despesas no periodo.",
        "arguments": {"month": "int|null", "year": "int", "limit": "int"},
    },
    "get_recurring_expenses": {
        "description": "Retorna despesas recorrentes.",
        "arguments": {},
    },
    "get_category_growth": {
        "description": "Retorna crescimento mensal da categoria no ano.",
        "arguments": {"category": "str", "year": "int"},
    },
}

FUNCTIONS = {
    "get_total_by_month": get_total_by_month,
    "get_total_by_category": get_total_by_category,
    "get_top_expenses": get_top_expenses,
    "get_recurring_expenses": get_recurring_expenses,
    "get_category_growth": get_category_growth,
}


def _is_in_scope(question: str) -> bool:
    q = (question or "").lower()
    keywords = [
        "gasto",
        "despesa",
        "categoria",
        "recorr",
        "mes",
        "mês",
        "ano",
        "cres",
        "total",
        "finan",
        "receita",
        "quanto",
    ]
    return any(k in q for k in keywords)


def _extract_json_object(text: str) -> dict[str, Any] | None:
    content = (text or "").strip()
    if not content.startswith("{") or not content.endswith("}"):
        return None

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, dict):
        return None

    return parsed


def _build_function_call_system_prompt(current_month: int, current_year: int) -> str:
    schema_text = json.dumps(FUNCTION_SCHEMAS, ensure_ascii=False, indent=2)
    return (
        "Você é um roteador de funções financeiras. "
        "Responda SOMENTE com JSON válido no formato "
        '{"function":"nome","arguments":{}} sem texto extra.\\n'
        f"Mês atual: {current_month}\\n"
        f"Ano atual: {current_year}\\n"
        "Se o usuário disser 'este mês/esse mês', use o mês atual. "
        "Se disser 'este ano/esse ano', use o ano atual. "
        "Escolha apenas uma função da lista abaixo.\\n"
        f"{schema_text}"
    )


def _build_final_response_system_prompt() -> str:
    return (
        "Você formata respostas financeiras com base EXCLUSIVA nos dados fornecidos. "
        "Não invente números, não invente categorias e não use informação externa. "
        "Se os dados vierem vazios, diga que não encontrou dados para o período."
    )


def handle_user_question(question: str) -> str:
    if not _is_in_scope(question):
        return OUT_OF_SCOPE_TEXT

    now = datetime.now()
    current_month = now.month
    current_year = now.year

    first_prompt = (
        f"Pergunta do usuário: {question}\\n"
        "Escolha a função correta e retorne somente JSON com function e arguments."
    )

    try:
        routing_raw = call_ollama(
            prompt=first_prompt,
            system_prompt=_build_function_call_system_prompt(current_month, current_year),
        )
    except LLMClientError:
        return "Erro ao consultar o modelo local."

    routing_json = _extract_json_object(routing_raw)
    if routing_json is None:
        return "Erro: resposta de função inválida do modelo."

    function_name = routing_json.get("function")
    arguments = routing_json.get("arguments", {})

    if not isinstance(function_name, str) or function_name not in FUNCTIONS:
        return "Erro: função solicitada inválida."

    if not isinstance(arguments, dict):
        return "Erro: argumentos inválidos para execução."

    try:
        result = FUNCTIONS[function_name](**arguments)
    except TypeError:
        return "Erro: argumentos inválidos para execução."
    except ValueError as exc:
        return f"Erro de validação: {exc}"
    except Exception:
        return "Erro ao executar a consulta financeira."

    result_json = json.dumps(result, ensure_ascii=False)

    second_prompt = (
        f"Pergunta original: {question}\\n"
        f"Função executada: {function_name}\\n"
        f"Dados retornados (JSON): {result_json}\\n"
        "Gere uma resposta curta e clara em português, usando apenas esses dados."
    )

    try:
        final_text = call_ollama(
            prompt=second_prompt,
            system_prompt=_build_final_response_system_prompt(),
        )
    except LLMClientError:
        return "Erro ao consultar o modelo local."

    if not final_text.strip():
        return "Não foi possível gerar uma resposta com os dados disponíveis."

    return final_text.strip()
