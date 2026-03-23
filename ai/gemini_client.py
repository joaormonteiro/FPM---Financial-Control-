from __future__ import annotations

import json
import os
import re
from typing import Any

import requests

ALLOWED_CATEGORIES = {
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
}
ALLOWED_PAYERS = {"eu", "pais"}

_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}")
_DEFAULT_MODEL = "gemini-1.5-flash"


class GeminiClientError(Exception):
    pass


def is_gemini_available() -> bool:
    return bool((os.getenv("GEMINI_API_KEY") or "").strip())


def _extract_json_object(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        raise GeminiClientError("Gemini retornou resposta vazia.")

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    match = _JSON_BLOCK_RE.search(raw)
    if not match:
        raise GeminiClientError("Gemini não retornou JSON válido.")

    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise GeminiClientError("Gemini retornou JSON inválido.") from exc

    if not isinstance(parsed, dict):
        raise GeminiClientError("Gemini retornou JSON fora do formato esperado.")
    return parsed


def _build_prompt(descricao_original: str, amount: float, tx_kind: str) -> str:
    return f"""
Você é um assistente financeiro.

Receberá:
- descrição original da transação
- valor
- tipo (entrada ou saida)

Tarefa:
1) sugerir uma descrição final curta e clara
2) sugerir categoria
3) sugerir pagador (eu ou pais)

Categorias possíveis:
alimentacao
lazer
transporte
educacao
moradia
assinaturas
saude
investimentos
entrada
outros

Regras:
- não inventar dados
- se não tiver informação suficiente, usar categoria outros
- responder SOMENTE em JSON

Formato JSON obrigatório:
{{
  "descricao": "...",
  "categoria": "...",
  "pagador": "eu|pais"
}}

Dados:
descricao_original: {descricao_original}
valor: {amount:.2f}
tipo: {tx_kind}
""".strip()


def classify_with_gemini(
    descricao_original: str,
    amount: float = 0.0,
    tx_kind: str = "saida",
) -> dict[str, str]:
    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        raise GeminiClientError("GEMINI_API_KEY não configurada.")

    model = (os.getenv("GEMINI_MODEL") or _DEFAULT_MODEL).strip()
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    payload = {
        "contents": [{"parts": [{"text": _build_prompt(descricao_original, float(amount), tx_kind)}]}],
        "generationConfig": {
            "temperature": 0.1,
            "topK": 1,
            "topP": 0.9,
            "maxOutputTokens": 256,
        },
    }

    try:
        resp = requests.post(
            endpoint,
            params={"key": api_key},
            json=payload,
            timeout=20,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise GeminiClientError(f"Falha ao chamar Gemini: {exc}") from exc

    try:
        data = resp.json()
    except ValueError as exc:
        raise GeminiClientError("Gemini retornou resposta não JSON.") from exc

    candidates = data.get("candidates") or []
    if not candidates:
        raise GeminiClientError("Gemini não retornou candidatos.")

    parts = (
        candidates[0].get("content", {}).get("parts", [])
        if isinstance(candidates[0], dict)
        else []
    )
    text = ""
    for part in parts:
        if isinstance(part, dict) and isinstance(part.get("text"), str):
            text += part["text"]

    parsed = _extract_json_object(text)
    descricao = str(parsed.get("descricao") or "").strip()
    categoria = str(parsed.get("categoria") or "outros").strip().lower()
    pagador = str(parsed.get("pagador") or "eu").strip().lower()

    if categoria not in ALLOWED_CATEGORIES:
        categoria = "outros"
    if pagador not in ALLOWED_PAYERS:
        pagador = "eu"
    if not descricao:
        descricao = str(descricao_original or "").strip()

    return {
        "descricao": descricao,
        "categoria": categoria,
        "pagador": pagador,
    }
