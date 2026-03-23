from __future__ import annotations

from dataclasses import dataclass
import os
import re
import unicodedata

from ai.custom_rule_engine import apply_description_rules
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
    "saude",
    "investimentos",
    "entrada",
    "outros",
}
ALLOWED_PAYERS = {"eu", "pais"}

_SPACES_RE = re.compile(r"\s+")
_NON_WORD_RE = re.compile(r"[^a-z0-9\s]")
_DIGITS_RE = re.compile(r"\d+")

_FAMILY_RULES: list[tuple[tuple[str, ...], str]] = [
    (("rubens", "monteiro"), "Rubens Monteiro"),
    (("juliana", "monteiro"), "Juliana Monteiro"),
    (("solange", "monteiro"), "Solange Monteiro"),
]

_NAME_STOPWORDS = {
    "pix",
    "enviado",
    "enviada",
    "recebido",
    "recebida",
    "de",
    "do",
    "da",
    "para",
    "por",
    "cp",
    "cpf",
    "no",
    "na",
    "estabelecimento",
    "ted",
    "doc",
    "transf",
    "transferencia",
    "transferencias",
    "pagamento",
}

_IA_CACHE: dict[tuple[str, float, str], tuple[str | None, str | None]] = {}
_IA_CALL_COUNT = 0


def _safe_int_env(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(0, value)


_IA_MAX_CALLS_PER_RUN = _safe_int_env("MAX_AI_SUGGESTIONS_PER_RUN", 25)


@dataclass(frozen=True)
class DescricaoProcessada:
    descricao_normalizada: str
    descricao_final: str
    categoria: str | None
    ignore: bool
    matched_rule: bool


def _strip_accents(text: str) -> str:
    return (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode("ascii")
    )


def _normalize_for_rules(text: str) -> str:
    normalized = _strip_accents((text or "").lower().strip())
    normalized = _NON_WORD_RE.sub(" ", normalized)
    normalized = _SPACES_RE.sub(" ", normalized).strip()
    return normalized


def _capitalize_first(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return text
    return text[:1].upper() + text[1:]


def _determine_pix_direction(
    amount: float,
    normalized_text: str,
    normalized_tx_type: str = "",
) -> str:
    if "pix enviado" in normalized_tx_type:
        return "enviado"
    if "pix recebido" in normalized_tx_type:
        return "recebido"

    if amount < 0:
        return "enviado"
    if amount > 0:
        return "recebido"

    if "enviado" in normalized_text or "enviada" in normalized_text:
        return "enviado"
    return "recebido"


def _extract_name(description: str) -> str:
    normalized = _normalize_for_rules(description)
    tokens: list[str] = []
    for token in normalized.split():
        token = _DIGITS_RE.sub("", token)
        token = token.strip()
        if not token:
            continue
        if token in _NAME_STOPWORDS:
            continue
        if len(token) <= 1:
            continue
        tokens.append(token)

    if not tokens:
        return "Pessoa"

    if len(tokens) >= 3:
        selected = tokens[-3:]
    elif len(tokens) == 2:
        selected = tokens[-2:]
    else:
        selected = tokens

    return " ".join(part.capitalize() for part in selected)


def _guess_category(normalized_description: str) -> str:
    d = _strip_accents(normalized_description).upper()

    if "INVESTIMENTO" in d:
        return "investimentos"
    if "SALARIO" in d:
        return "entrada"
    if any(k in d for k in ["UBER", "99", "TAXI", "METRO", "ONIBUS", "PASSAGEM", "CARONA"]):
        return "transporte"
    if any(k in d for k in ["PADARIA", "MERCADO", "IFOOD", "RESTAURANTE", "LANCH", "PIZZA"]):
        return "alimentacao"
    if any(k in d for k in ["ESCOLA", "CURSO", "FACULDADE", "LIVRO"]):
        return "educacao"
    if any(k in d for k in ["ALUGUEL", "CONDOMINIO", "LUZ", "AGUA", "INTERNET"]):
        return "moradia"
    if any(k in d for k in ["SPOTIFY", "NETFLIX", "AMAZON PRIME", "YOUTUBE PREMIUM"]):
        return "assinaturas"
    if any(k in d for k in ["FARMACIA", "HOSPITAL", "MEDICO", "CLINICA", "TERAPIA"]):
        return "saude"
    if any(k in d for k in ["CINEMA", "SHOW", "BAR", "JOGO", "STEAM"]):
        return "lazer"
    return "outros"


def _guess_payer(normalized_description: str) -> str:
    d = _strip_accents(normalized_description).upper()
    parent_hints = ["ALUGUEL", "FACULDADE", "SPOTIFY", "NETFLIX", "MERCADO"]
    if any(k in d for k in parent_hints):
        return "pais"
    return "eu"


def _sanitize_category(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    return normalized if normalized in ALLOWED_CATEGORIES else "outros"


def _sanitize_payer(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    return normalized if normalized in ALLOWED_PAYERS else "eu"


def _tx_kind_for_ia(amount: float, tx_type: str | None) -> str:
    tx = (tx_type or "").strip().lower()
    if tx in {"credit", "entrada"}:
        return "entrada"
    if tx in {"debit", "saida", "saída"}:
        return "saida"
    return "entrada" if float(amount) >= 0 else "saida"


def sugerir_descricao_com_ia(transacao: dict) -> tuple[str | None, str | None]:
    global _IA_CALL_COUNT
    if not is_gemini_available():
        return None, None

    raw_description = str(transacao.get("description") or transacao.get("raw_description") or "").strip()
    amount = float(transacao.get("amount") or 0.0)
    tx_kind = _tx_kind_for_ia(amount, str(transacao.get("type") or ""))
    if not raw_description:
        return None, None
    cache_key = (_normalize_for_rules(raw_description), float(amount), tx_kind)
    if cache_key in _IA_CACHE:
        return _IA_CACHE[cache_key]

    if _IA_CALL_COUNT >= _IA_MAX_CALLS_PER_RUN:
        return None, None

    _IA_CALL_COUNT += 1

    try:
        result = classify_with_gemini(
            descricao_original=raw_description,
            amount=amount,
            tx_kind=tx_kind,
        )
    except GeminiClientError:
        _IA_CACHE[cache_key] = (None, None)
        return None, None

    descricao = _capitalize_first(str(result.get("descricao") or "").strip()) or None
    categoria = str(result.get("categoria") or "").strip().lower() or None
    _IA_CACHE[cache_key] = (descricao, categoria)
    return descricao, categoria


def processar_descricao(transacao: dict) -> DescricaoProcessada:
    raw_description = str(transacao.get("description") or transacao.get("raw_description") or "").strip()
    amount = float(transacao.get("amount") or 0.0)
    tx_type = str(transacao.get("type") or "")

    descricao_normalizada = normalize_description(raw_description)
    normalized_rules = _normalize_for_rules(raw_description)
    normalized_tx_type = _normalize_for_rules(tx_type)

    # 1) Ignorar fatura de cartão.
    if "fatura" in normalized_rules and "cartao" in normalized_rules:
        return DescricaoProcessada(
            descricao_normalizada=descricao_normalizada,
            descricao_final=raw_description or "Fatura cartao",
            categoria=None,
            ignore=True,
            matched_rule=True,
        )

    is_pix = (
        "pix" in normalized_rules
        or "pix" in descricao_normalizada
        or "pix" in normalized_tx_type
    )
    pix_direction = _determine_pix_direction(
        amount=amount,
        normalized_text=normalized_rules,
        normalized_tx_type=normalized_tx_type,
    )
    is_pix_enviado = is_pix and pix_direction == "enviado"

    # 2) Carona (prioridade máxima).
    if is_pix_enviado and 4.0 <= abs(amount) <= 6.0:
        return DescricaoProcessada(
            descricao_normalizada=descricao_normalizada,
            descricao_final="Carona Unifesp",
            categoria="transporte",
            ignore=False,
            matched_rule=True,
        )

    # 3) Investimentos.
    if "cdb" in normalized_rules or "porquinho" in normalized_rules:
        return DescricaoProcessada(
            descricao_normalizada=descricao_normalizada,
            descricao_final="Investimento",
            categoria="investimentos",
            ignore=False,
            matched_rule=True,
        )

    # 4) Salário.
    if "salario" in normalized_rules:
        return DescricaoProcessada(
            descricao_normalizada=descricao_normalizada,
            descricao_final="Salário",
            categoria="entrada",
            ignore=False,
            matched_rule=True,
        )

    # Regras customizadas (determinísticas).
    custom = apply_description_rules(
        description=raw_description,
        amount=amount,
        tx_type=tx_type,
        is_recurring=None,
    )
    if custom is not None:
        custom_description, custom_category, _priority = custom
        return DescricaoProcessada(
            descricao_normalizada=descricao_normalizada,
            descricao_final=_capitalize_first(custom_description or raw_description or "Transação"),
            categoria=custom_category,
            ignore=False,
            matched_rule=True,
        )

    # 5) Família.
    for tokens, family_name in _FAMILY_RULES:
        if all(token in normalized_rules for token in tokens):
            return DescricaoProcessada(
                descricao_normalizada=descricao_normalizada,
                descricao_final=f"Pix {pix_direction} {family_name}",
                categoria=None,
                ignore=False,
                matched_rule=True,
            )

    # 6) Pix genérico (fallback determinístico).
    if is_pix:
        extracted_name = _extract_name(raw_description)
        return DescricaoProcessada(
            descricao_normalizada=descricao_normalizada,
            descricao_final=f"Pix {pix_direction} {extracted_name}",
            categoria=None,
            ignore=False,
            matched_rule=True,
        )

    fallback_description = _capitalize_first(raw_description or "Transação")
    return DescricaoProcessada(
        descricao_normalizada=descricao_normalizada,
        descricao_final=fallback_description,
        categoria=None,
        ignore=False,
        matched_rule=False,
    )


def enhance_transaction(
    raw_description: str,
    amount: float,
    tx_type: str | None = None,
) -> tuple[str, str, str, float, str, str] | None:
    """
    Pipeline:
    1) normaliza/processa descrição
    2) aplica regras determinísticas
    3) se não houver regra, consulta IA
    4) com descrição final pronta, deriva categoria e pagador
    """
    processed = processar_descricao(
        {
            "description": raw_description,
            "amount": amount,
            "type": tx_type,
        }
    )
    if processed.ignore:
        return None

    descricao_final = _capitalize_first((processed.descricao_final or "").strip() or (raw_description or "").strip())
    descricao_final_normalizada = normalize_description(descricao_final) or processed.descricao_normalizada

    # Determinístico: regra explícita.
    if processed.matched_rule:
        category = _sanitize_category(processed.categoria or _guess_category(descricao_final_normalizada))
        payer = _sanitize_payer(_guess_payer(descricao_final_normalizada))
        return (
            descricao_final,
            category,
            payer,
            1.0,
            "rule",
            descricao_final_normalizada,
        )

    # Aprendizado por histórico (determinístico por edição prévia).
    pattern = get_learned_pattern(descricao_final_normalizada)
    if pattern is not None:
        learned_category = _sanitize_category(pattern.get("categoria"))
        learned_payer = _sanitize_payer(pattern.get("pagador"))
        learned_description = _capitalize_first(
            (pattern.get("descricao_editada_usuario") or "").strip() or descricao_final
        )
        usage = int(pattern.get("contador_uso") or 1)
        confidence = min(0.7 + (usage * 0.05), 1.0)
        return (
            learned_description,
            learned_category,
            learned_payer,
            confidence,
            "pattern",
            normalize_description(learned_description) or descricao_final_normalizada,
        )

    # IA: somente quando nenhuma regra determinística casou.
    ia_description, ia_category = sugerir_descricao_com_ia(
        {
            "description": raw_description,
            "amount": amount,
            "type": tx_type,
        }
    )
    if ia_description is not None or ia_category is not None:
        final_description = _capitalize_first(ia_description or descricao_final)
        final_normalized = normalize_description(final_description) or descricao_final_normalizada
        category = _sanitize_category(ia_category or _guess_category(final_normalized))
        payer = _sanitize_payer(_guess_payer(final_normalized))
        return (
            final_description,
            category,
            payer,
            0.8,
            "gemini",
            final_normalized,
        )

    # Fallback local.
    fallback_category = _sanitize_category(_guess_category(descricao_final_normalizada))
    fallback_payer = _sanitize_payer(_guess_payer(descricao_final_normalizada))
    return (
        descricao_final,
        fallback_category,
        fallback_payer,
        0.45,
        "fallback",
        descricao_final_normalizada,
    )
