"""
Google Gemini API client with exponential back-off retry logic.

Gracefully degrades to ("outros", 0.4) when the API is unavailable,
rate-limited, or returns unparseable output.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import requests

from core.models import ALLOWED_CATEGORIES, ALLOWED_PAYERS

_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*?\}")
_DEFAULT_MODEL = "gemini-1.5-flash"

MAX_CALLS_PER_RUN = int(os.getenv("MAX_AI_SUGGESTIONS_PER_RUN", "25"))
RETRY_ATTEMPTS = 3
RETRY_DELAYS = [1, 2, 4]  # seconds – exponential back-off


class GeminiClientError(Exception):
    """Raised when the Gemini API call fails unrecoverably."""


def is_gemini_available() -> bool:
    """Return True if the GEMINI_API_KEY environment variable is set."""
    return bool((os.getenv("GEMINI_API_KEY") or "").strip())


def _extract_json_object(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        raise GeminiClientError("Gemini returned an empty response.")

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    for match in _JSON_BLOCK_RE.finditer(raw):
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue

    raise GeminiClientError("Gemini did not return valid JSON.")


def _build_prompt(description: str, amount: float, tx_kind: str) -> str:
    categories = "\n".join(ALLOWED_CATEGORIES)
    return f"""
Você é um assistente financeiro pessoal para usuários brasileiros.

Você receberá uma descrição de transação bancária, o valor e o tipo (entrada ou saida).

Sua tarefa é:
1. Sugerir uma descrição curta e clara (máx. 40 caracteres)
2. Classificar em uma das categorias abaixo
3. Indicar se o pagador é "eu" ou "pais"

Categorias disponíveis:
{categories}

Regras importantes:
- Se não tiver informação suficiente, use "outros"
- Não invente dados
- Responda APENAS em JSON, sem texto adicional

Formato obrigatório:
{{"descricao": "...", "categoria": "...", "pagador": "eu|pais"}}

Dados da transação:
descricao_original: {description}
valor: R$ {amount:.2f}
tipo: {tx_kind}
""".strip()


def _do_classify(
    description: str,
    amount: float,
    tx_kind: str,
    api_key: str,
    model: str,
) -> dict[str, str]:
    """Execute a single Gemini API call. May raise requests.RequestException."""
    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    )
    payload = {
        "contents": [
            {"parts": [{"text": _build_prompt(description, float(amount), tx_kind)}]}
        ],
        "generationConfig": {
            "temperature": 0.1,
            "topK": 1,
            "topP": 0.9,
            "maxOutputTokens": 256,
        },
    }
    resp = requests.post(
        endpoint,
        params={"key": api_key},
        json=payload,
        timeout=20,
    )
    resp.raise_for_status()

    data = resp.json()
    candidates = data.get("candidates") or []
    if not candidates:
        raise GeminiClientError("Gemini returned no candidates.")

    parts = (
        candidates[0].get("content", {}).get("parts", [])
        if isinstance(candidates[0], dict)
        else []
    )
    text = "".join(
        p["text"] for p in parts if isinstance(p, dict) and isinstance(p.get("text"), str)
    )

    parsed = _extract_json_object(text)
    descricao = str(parsed.get("descricao") or description).strip()
    categoria = str(parsed.get("categoria") or "outros").strip().lower()
    pagador = str(parsed.get("pagador") or "eu").strip().lower()

    if categoria not in ALLOWED_CATEGORIES:
        categoria = "outros"
    if pagador not in ALLOWED_PAYERS:
        pagador = "eu"

    return {"descricao": descricao, "categoria": categoria, "pagador": pagador}


def classify_with_gemini(
    descricao_original: str,
    amount: float = 0.0,
    tx_kind: str = "saida",
) -> dict[str, str]:
    """
    Classify a transaction using the Gemini API.

    Retries up to RETRY_ATTEMPTS times with exponential back-off on HTTP 429.
    Returns a safe fallback dict on any unrecoverable error.

    Raises GeminiClientError if GEMINI_API_KEY is not configured.
    """
    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        raise GeminiClientError("GEMINI_API_KEY is not configured.")

    model = (os.getenv("GEMINI_MODEL") or _DEFAULT_MODEL).strip()

    last_exc: Exception = GeminiClientError("Unknown error")
    for attempt, delay in enumerate(RETRY_DELAYS):
        try:
            return _do_classify(descricao_original, float(amount), tx_kind, api_key, model)
        except requests.HTTPError as exc:
            last_exc = exc
            if exc.response is not None and exc.response.status_code == 429:
                if attempt < RETRY_ATTEMPTS - 1:
                    time.sleep(delay)
                    continue
            # Non-retryable HTTP error → return fallback
            return {
                "descricao": str(descricao_original or ""),
                "categoria": "outros",
                "pagador": "eu",
            }
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < RETRY_ATTEMPTS - 1:
                time.sleep(delay)
                continue
            return {
                "descricao": str(descricao_original or ""),
                "categoria": "outros",
                "pagador": "eu",
            }
        except GeminiClientError:
            return {
                "descricao": str(descricao_original or ""),
                "categoria": "outros",
                "pagador": "eu",
            }

    return {
        "descricao": str(descricao_original or ""),
        "categoria": "outros",
        "pagador": "eu",
    }
