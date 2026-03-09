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
        raise GeminiClientError("Gemini nao retornou JSON valido.")

    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise GeminiClientError("Gemini retornou JSON invalido.") from exc

    if not isinstance(parsed, dict):
        raise GeminiClientError("Gemini retornou JSON fora do formato esperado.")
    return parsed


def _build_prompt(descricao_original: str) -> str:
    return f"""
Voce e um classificador de transacoes financeiras pessoais.

Recebera a descricao de uma transacao bancaria.

Sua tarefa e:

1) gerar uma descricao curta e clara
2) classificar a categoria
3) sugerir quem pagou

Categorias possiveis:
alimentacao
lazer
transporte
educacao
moradia
assinaturas
outros

Regras:

- se nao tiver informacao suficiente -> categoria = outros
- nao inventar dados
- descricao curta e objetiva

Formato da resposta JSON:

{{
 "descricao": "...",
 "categoria": "...",
 "pagador": "eu | pais"
}}

Descricao da transacao:

{descricao_original}
""".strip()


def classify_with_gemini(descricao_original: str) -> dict[str, str]:
    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        raise GeminiClientError("GEMINI_API_KEY nao configurada.")

    model = (os.getenv("GEMINI_MODEL") or _DEFAULT_MODEL).strip()
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    payload = {
        "contents": [{"parts": [{"text": _build_prompt(descricao_original)}]}],
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
        raise GeminiClientError("Gemini retornou resposta nao JSON.") from exc

    candidates = data.get("candidates") or []
    if not candidates:
        raise GeminiClientError("Gemini nao retornou candidatos.")

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
