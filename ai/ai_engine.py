from __future__ import annotations

import re
import unicodedata

from ai.description_normalizer import normalize_description
from ai.gemini_client import GeminiClientError, classify_with_gemini, is_gemini_available
from ai.learned_patterns import get_learned_pattern

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

_SPOTIFY_RE = re.compile(r"\bspotify\b", re.IGNORECASE)


def _strip_accents(text: str) -> str:
    return (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode("ascii")
    )


def _guess_category(normalized_description: str) -> str:
    d = _strip_accents(normalized_description).upper()

    if any(k in d for k in ["UBER", "99", "TAXI", "METRO", "ONIBUS", "PASSAGEM"]):
        return "transporte"
    if any(k in d for k in ["PADARIA", "MERCADO", "IFOOD", "RESTAURANTE", "LANCH", "PIZZA"]):
        return "alimentacao"
    if any(k in d for k in ["ESCOLA", "CURSO", "FACULDADE", "LIVRO"]):
        return "educacao"
    if any(k in d for k in ["ALUGUEL", "CONDOMINIO", "LUZ", "AGUA", "INTERNET"]):
        return "moradia"
    if any(k in d for k in ["SPOTIFY", "NETFLIX", "AMAZON PRIME", "YOUTUBE PREMIUM"]):
        return "assinaturas"
    if any(k in d for k in ["CINEMA", "SHOW", "BAR", "JOGO", "STEAM"]):
        return "lazer"
    return "outros"


def _guess_payer(normalized_description: str) -> str:
    d = _strip_accents(normalized_description).upper()
    parent_hints = ["ALUGUEL", "FACULDADE", "SPOTIFY", "NETFLIX", "MERCADO"]
    if any(k in d for k in parent_hints):
        return "pais"
    return "eu"


def _offline_classification(raw_description: str, normalized_description: str) -> tuple[str, str, str]:
    short_description = normalized_description or _strip_accents(raw_description).lower().strip()
    if not short_description:
        short_description = "transacao"
    category = _guess_category(short_description)
    payer = _guess_payer(short_description)
    return short_description, category, payer


def _sanitize_category(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    return normalized if normalized in ALLOWED_CATEGORIES else "outros"


def _sanitize_payer(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    return normalized if normalized in ALLOWED_PAYERS else "eu"


def enhance_transaction(raw_description: str, amount: float):
    """
    Fluxo:
    1) normaliza descricao
    2) regra fixa (spotify)
    3) busca padrao aprendido
    4) se nao houver padrao: Gemini (quando disponivel), com fallback offline

    Retorna:
    (descricao_editada, categoria, pagador, confianca, origem_classificacao, descricao_normalizada)
    """
    _ = amount  # reservado para regras futuras por valor
    raw = (raw_description or "").strip()
    normalized_description = normalize_description(raw)

    if _SPOTIFY_RE.search(raw) or _SPOTIFY_RE.search(normalized_description):
        return "spotify", "assinaturas", "pais", 1.0, "rule", normalized_description

    pattern = get_learned_pattern(normalized_description)
    if pattern is not None:
        learned_description = (pattern.get("descricao_editada_usuario") or "").strip() or raw
        learned_category = _sanitize_category(pattern.get("categoria"))
        learned_payer = _sanitize_payer(pattern.get("pagador"))
        usage = int(pattern.get("contador_uso") or 1)
        confidence = min(0.7 + (usage * 0.05), 1.0)
        return (
            learned_description,
            learned_category,
            learned_payer,
            confidence,
            "pattern",
            normalized_description,
        )

    fallback_description, fallback_category, fallback_payer = _offline_classification(
        raw,
        normalized_description,
    )

    if not is_gemini_available():
        return (
            fallback_description,
            fallback_category,
            fallback_payer,
            0.45,
            "fallback",
            normalized_description,
        )

    try:
        gemini_result = classify_with_gemini(raw)
    except GeminiClientError:
        return (
            fallback_description,
            fallback_category,
            fallback_payer,
            0.45,
            "fallback",
            normalized_description,
        )

    gemini_description = (gemini_result.get("descricao") or "").strip() or fallback_description
    gemini_category = _sanitize_category(gemini_result.get("categoria"))
    gemini_payer = _sanitize_payer(gemini_result.get("pagador"))

    # Se Gemini retornar "outros" e o fallback local tiver match forte, aproveita a melhoria local.
    if gemini_category == "outros" and fallback_category != "outros":
        gemini_category = fallback_category

    confidence = 0.8 if gemini_category != "outros" else 0.6
    return (
        gemini_description,
        gemini_category,
        gemini_payer,
        confidence,
        "gemini",
        normalized_description,
    )

