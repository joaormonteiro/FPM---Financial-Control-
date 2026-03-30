"""
7-stage transaction classification pipeline.

Stages (cascade – stops at first stage that meets threshold):
  1. Knowledge-base rules   (knowledge_base.json)   → confidence 1.0
  2. User custom rules      (custom_rules.json)      → confidence 0.95
  3. Learned patterns       (padroes_aprendidos DB)  → confidence 0.70–1.0
  4. Google Gemini API      (optional)               → confidence 0.80
  5. TF-IDF history         (scikit-learn)           → confidence > 0.82
  6. Keyword heuristics     (strict allowlist)       → confidence 0.65
  7. Fallback               (category "outros")      → confidence 0.40
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

from ai.custom_rule_engine import apply_description_rules
from ai.description_normalizer import normalize_description, strip_accents
from ai.gemini_client import GeminiClientError, classify_with_gemini, is_gemini_available
from core.db.patterns import get_pattern
from core.models import ALLOWED_CATEGORIES, ALLOWED_PAYERS, capitalize_first
from core.settings import DB_PATH

_SPACES_RE = re.compile(r"\s+")
_NON_WORD_RE = re.compile(r"[^a-z0-9\s]")

# ---------------------------------------------------------------------------
# Per-run state
# ---------------------------------------------------------------------------
_IA_CACHE: dict[tuple[str, float, str], dict] = {}
_IA_CALL_COUNT = 0
_IA_MAX_CALLS = int((os.getenv("MAX_AI_SUGGESTIONS_PER_RUN") or "25").strip() or "25")

# ---------------------------------------------------------------------------
# Keyword allowlist for Stage 6 – strict: no match → fallback, not a guess
# ---------------------------------------------------------------------------
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "alimentacao": [
        "ifood", "rappi", "uber eats", "mcdonalds", "mc donalds", "burger king",
        "subway", "mercado", "supermercado", "padaria", "acougue", "hortifruti",
        "restaurante", "lanchonete", "pizzaria", "sushi", "delivery",
        "carrefour", "extra", "pao de acucar", "atacadao", "assai",
        "panificadora", "mercearia",
    ],
    "transporte": [
        "uber", "99app", "99taxi", "99 trip", "99*trip", "cabify", "lyft", "taxi",
        "combustivel", "gasolina", "etanol", "posto", "ipva",
        "onibus", "metro", "bilhete unico", "bom embarque",
        "estacionamento", "pedagio", "autopass", "sem parar",
        "detran", "veiculo", "oficina", "mecanico",
    ],
    "saude": [
        "farmacia", "drogaria", "droga", "medico", "clinica",
        "hospital", "laboratorio", "exame", "plano de saude",
        "unimed", "amil", "bradesco saude", "sulamerica saude",
        "dentista", "fisioterapia", "psicologia", "terapia",
    ],
    "educacao": [
        "escola", "faculdade", "universidade", "curso", "mensalidade",
        "livraria", "udemy", "coursera", "alura", "dio",
        "duolingo", "editora", "apostila",
    ],
    "lazer": [
        "cinema", "netflix", "spotify", "steam", "playstation", "xbox",
        "amazon prime", "disney", "hbo", "ingresso", "teatro",
        "parque", "hotel", "airbnb", "booking",
        "deezer", "crunchyroll", "twitch",
    ],
    "moradia": [
        "aluguel", "condominio", "agua", "luz", "energia", "gas",
        "internet", "telefone", "tim", "vivo", "claro", "oi",
        "enel", "sabesp", "comgas",
    ],
    "assinaturas": [
        "spotify", "netflix", "amazon prime", "disney plus", "disney+",
        "hbo max", "youtube premium", "deezer", "apple music",
        "microsoft", "google one", "icloud", "dropbox",
    ],
    "investimentos": [
        "cdb", "tesouro", "poupanca", "investimento", "renda fixa",
        "porquinho", "acoes", "fundo", "lci", "lca",
    ],
    "entrada": [
        "salario", "freelance", "pix recebido", "transferencia recebida",
        "rendimento", "dividendo", "cashback", "reembolso", "deposito",
    ],
}

# Flatten for fast lookup: normalized_keyword → category
_KEYWORD_INDEX: dict[str, str] = {}
for _cat, _kws in CATEGORY_KEYWORDS.items():
    for _kw in _kws:
        _normalized_kw = strip_accents(_kw.lower())
        if _normalized_kw not in _KEYWORD_INDEX:
            _KEYWORD_INDEX[_normalized_kw] = _cat

# ---------------------------------------------------------------------------
# Stage 1 helpers – knowledge_base.json
# ---------------------------------------------------------------------------
_KB_PATH = Path(__file__).with_name("knowledge_base.json")


@lru_cache(maxsize=1)
def _load_kb() -> list[dict]:
    """Load knowledge-base rules once and cache in memory."""
    try:
        data = json.loads(_KB_PATH.read_text(encoding="utf-8"))
        return [r for r in data.get("rules", []) if isinstance(r, dict)]
    except Exception:
        return []


def _apply_kb_rules(
    rules_norm: str,
) -> Optional[tuple[str, str, float, str]]:
    """
    Stage 1: match against knowledge_base.json.

    Matches if ANY keyword in the rule's keyword list is found in
    *rules_norm* (lowercase + accent-stripped, numbers retained).

    Returns (description, category, confidence, source) or None.
    """
    for rule in _load_kb():
        keywords: list[str] = rule.get("keywords", [])
        if not keywords:
            continue
        # ANY keyword match triggers the rule (keywords are synonyms)
        if any(strip_accents(kw.lower()) in rules_norm for kw in keywords):
            cat = str(rule.get("category") or "outros").lower()
            if cat not in ALLOWED_CATEGORIES:
                cat = "outros"
            desc = str(rule.get("description") or "").strip()
            return (desc, cat, float(rule.get("confidence", 1.0)), "rule")
    return None


# ---------------------------------------------------------------------------
# Stage 6 helper – keyword heuristics
# ---------------------------------------------------------------------------

def _keyword_heuristic(normalized_desc: str) -> Optional[str]:
    """
    Stage 6: strict keyword allowlist.

    Returns a category string or None if no keyword matches.
    Never returns a wrong guess – prefers returning None over a bad category.
    """
    for kw, cat in sorted(_KEYWORD_INDEX.items(), key=lambda x: -len(x[0])):
        if kw in normalized_desc:
            return cat
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sanitize_category(value: Optional[str]) -> str:
    v = (value or "").strip().lower()
    return v if v in ALLOWED_CATEGORIES else "outros"


def _sanitize_payer(value: Optional[str]) -> str:
    v = (value or "").strip().lower()
    return v if v in ALLOWED_PAYERS else "eu"


def _tx_kind(amount: float, tx_type: Optional[str]) -> str:
    tx = (tx_type or "").strip().lower()
    if tx in {"credit", "entrada"}:
        return "entrada"
    if tx in {"debit", "saida", "saída"}:
        return "saida"
    return "entrada" if float(amount) >= 0 else "saida"


def _guess_payer(normalized_desc: str) -> str:
    """Light heuristic for payer – defaults to 'eu'."""
    return "eu"


def _normalize_for_rules(text: str) -> str:
    n = strip_accents((text or "").lower().strip())
    n = _NON_WORD_RE.sub(" ", n)
    return _SPACES_RE.sub(" ", n).strip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def enhance_transaction(
    raw_description: str,
    amount: float,
    tx_type: Optional[str] = None,
) -> Optional[tuple[str, str, str, float, str, str]]:
    """
    Run the 7-stage classification pipeline.

    Returns:
        (cleaned_description, category, payer, confidence, source, normalized_description)
        or None if the transaction should be silently ignored (e.g. credit-card bill).

    The pipeline stops at the first stage that exceeds its confidence threshold.
    """
    global _IA_CALL_COUNT

    raw = (raw_description or "").strip()
    if not raw:
        return None

    # Pre-processing: detect credit-card bill (double-counting) → ignore
    # rules_norm retains numbers (e.g. "99") for better keyword matching
    rules_norm = _normalize_for_rules(raw)
    if "fatura" in rules_norm and "cartao" in rules_norm:
        return None

    # normalized strips numbers/dates — used for DB storage + import_uid
    normalized = normalize_description(raw) or rules_norm

    # ------------------------------------------------------------------
    # Stage 1 – Knowledge-base rules (confidence 1.0)
    # Uses rules_norm so numeric brands like "99" are detected
    # ------------------------------------------------------------------
    kb = _apply_kb_rules(rules_norm)
    if kb is not None:
        kb_desc, kb_cat, kb_conf, kb_src = kb
        final_desc = capitalize_first(kb_desc or raw)
        return (final_desc, kb_cat, _guess_payer(normalized), kb_conf, kb_src, normalized)

    # ------------------------------------------------------------------
    # Stage 2 – User custom rules (confidence 0.95)
    # ------------------------------------------------------------------
    custom = apply_description_rules(raw, amount, tx_type)
    if custom is not None:
        c_desc, c_cat, _priority = custom
        final_desc = capitalize_first((c_desc or raw).strip())
        final_cat = _sanitize_category(c_cat)
        return (final_desc, final_cat, _guess_payer(normalized), 0.95, "rule", normalized)

    # ------------------------------------------------------------------
    # Stage 3 – Learned patterns from DB (confidence 0.70–1.0)
    # ------------------------------------------------------------------
    pattern = get_pattern(normalized)
    if pattern is not None:
        p_cat = _sanitize_category(pattern.get("categoria"))
        p_payer = _sanitize_payer(pattern.get("pagador"))
        p_desc = capitalize_first(
            (pattern.get("descricao_editada_usuario") or raw).strip()
        )
        p_conf = float(pattern.get("confidence") or 0.7)
        return (p_desc, p_cat, p_payer, p_conf, "pattern", normalized)

    # ------------------------------------------------------------------
    # Stage 4 – Google Gemini API (confidence 0.80)
    # ------------------------------------------------------------------
    if is_gemini_available() and _IA_CALL_COUNT < _IA_MAX_CALLS:
        kind = _tx_kind(amount, tx_type)
        cache_key = (normalized, round(float(amount), 2), kind)
        if cache_key in _IA_CACHE:
            cached = _IA_CACHE[cache_key]
        else:
            _IA_CALL_COUNT += 1
            try:
                cached = classify_with_gemini(raw, float(amount), kind)
            except GeminiClientError:
                cached = {}
            _IA_CACHE[cache_key] = cached

        if cached and cached.get("categoria") and cached["categoria"] != "outros":
            g_desc = capitalize_first(str(cached.get("descricao") or raw).strip())
            g_cat = _sanitize_category(cached.get("categoria"))
            g_payer = _sanitize_payer(cached.get("pagador"))
            return (g_desc, g_cat, g_payer, 0.80, "gemini", normalized)

    # ------------------------------------------------------------------
    # Stage 5 – TF-IDF cosine similarity against historical transactions
    # ------------------------------------------------------------------
    try:
        from ai.history_classifier import HistoryBasedClassifier
        _classifier = HistoryBasedClassifier(DB_PATH)
        _classifier.build_index()
        tfidf = _classifier.predict(normalized)
        if tfidf is not None:
            t_cat, t_payer, t_score = tfidf
            if float(t_score) > 0.82:
                return (
                    capitalize_first(raw),
                    _sanitize_category(t_cat),
                    _sanitize_payer(t_payer),
                    float(t_score),
                    "history",
                    normalized,
                )
    except Exception:
        pass

    # ------------------------------------------------------------------
    # Stage 6 – Keyword heuristics (strict allowlist)
    # Uses rules_norm so numeric brands like "99" are detected
    # ------------------------------------------------------------------
    h_cat = _keyword_heuristic(rules_norm)
    if h_cat is not None:
        # Income detected → mark as entrada
        payer = "eu"
        return (capitalize_first(raw), h_cat, payer, 0.65, "heuristic", normalized)

    # ------------------------------------------------------------------
    # Stage 7 – Fallback
    # ------------------------------------------------------------------
    # If the transaction is clearly income (positive amount), use "entrada"
    if float(amount) > 0:
        return (capitalize_first(raw), "entrada", "eu", 0.50, "heuristic", normalized)

    return (capitalize_first(raw), "outros", "eu", 0.40, "fallback", normalized)


# ---------------------------------------------------------------------------
# Legacy helpers (kept for backward compatibility)
# ---------------------------------------------------------------------------

def sugerir_descricao_com_ia(transacao: dict) -> tuple[Optional[str], Optional[str]]:
    """
    Convenience wrapper used by financial_advisor and dashboard.
    Returns (description, category) or (None, None).
    """
    global _IA_CALL_COUNT

    raw = str(transacao.get("description") or transacao.get("raw_description") or "").strip()
    amount = float(transacao.get("amount") or 0.0)
    kind = _tx_kind(amount, str(transacao.get("type") or ""))

    if not raw or not is_gemini_available():
        return None, None
    if _IA_CALL_COUNT >= _IA_MAX_CALLS:
        return None, None

    normalized = _normalize_for_rules(raw)
    cache_key = (normalized, round(amount, 2), kind)
    if cache_key in _IA_CACHE:
        cached = _IA_CACHE[cache_key]
    else:
        _IA_CALL_COUNT += 1
        try:
            cached = classify_with_gemini(raw, amount, kind)
        except GeminiClientError:
            cached = {}
        _IA_CACHE[cache_key] = cached

    descricao = capitalize_first(str(cached.get("descricao") or "").strip()) or None
    categoria = str(cached.get("categoria") or "").strip().lower() or None
    return descricao, categoria
