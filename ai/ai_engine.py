import re
import unicodedata

from .custom_rule_engine import apply_custom_rule
from .history_classifier import HistoryBasedClassifier
from .rule_engine import apply_rules

ENABLE_AI = False

ALLOWED_CATEGORIES = {
    "alimentacao": "Alimentação",
    "saude": "Saúde",
    "transporte": "Transporte",
    "lazer": "Lazer",
    "outros": "Outros",
}

PIX_RE = re.compile(r"^Pix\s+(enviado|recebido):\s*\"?(.+?)\"?$", re.IGNORECASE)
COMPRA_RE = re.compile(r"^Compra no debito:\s*\"?(.+?)\"?$", re.IGNORECASE)
_HISTORY_CLASSIFIER: HistoryBasedClassifier | None = None


def _strip_accents(text: str) -> str:
    return (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode("ascii")
    )


def _title_if_upper(text: str) -> str:
    if text and text.isupper():
        return text.title()
    return text


def _clean_merchant(text: str) -> str:
    cleaned = text
    cleaned = re.sub(r"^No estabelecimento\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^PAG\\*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bBRA\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bSP\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return _title_if_upper(cleaned)


def _clean_pix_party(text: str) -> str:
    cleaned = re.sub(r"^Cp\s*:\s*\d+\s*-?\s*", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"^\d+\s+\d+\s+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return _title_if_upper(cleaned)


def _clean_description(raw_description: str) -> str:
    raw = raw_description.strip()

    pix_match = PIX_RE.match(raw)
    if pix_match:
        direction = pix_match.group(1).lower()
        party = _clean_pix_party(pix_match.group(2))
        if party:
            return f"Pix {direction}: {party}"
        return f"Pix {direction}"

    compra_match = COMPRA_RE.match(raw)
    if compra_match:
        merchant = _clean_merchant(compra_match.group(1))
        return merchant or raw_description

    return _title_if_upper(raw_description.strip())


def _normalize_category(cat: str | None) -> str:
    if not cat:
        return "Outros"
    key = _strip_accents(cat).strip().lower()
    return ALLOWED_CATEGORIES.get(key, "Outros")


def _heuristic_category(text: str) -> str:
    d = _strip_accents(text).upper()
    if any(k in d for k in ["UBER", "99", "TAXI", "METRO", "ONIBUS", "COLETIVO"]):
        return "Transporte"
    if any(k in d for k in ["PADARIA", "MERCADO", "MERCEARIA", "IFOOD", "RESTAURANTE", "BAR"]):
        return "Alimentação"
    if any(k in d for k in ["FARMACIA", "CLINICA", "HOSPITAL", "TERAPIA"]):
        return "Saúde"
    if any(k in d for k in ["NETFLIX", "SPOTIFY", "CINEMA", "STREAMING", "AMAZON PRIME"]):
        return "Lazer"
    return "Outros"


def _get_history_classifier() -> HistoryBasedClassifier:
    global _HISTORY_CLASSIFIER
    if _HISTORY_CLASSIFIER is None:
        _HISTORY_CLASSIFIER = HistoryBasedClassifier("data/finance.db")
        _HISTORY_CLASSIFIER.build_index()
    return _HISTORY_CLASSIFIER


def enhance_transaction(raw_description: str, amount: float):
    """
    Enriquecimento offline de transacao financeira.
    Retorna: (cleaned_description, category, payer, confidence, classification_source)
    """
    cleaned_hint = _clean_description(raw_description)
    rule_result = apply_rules(raw_description, amount)

    if rule_result is not None:
        rule_desc, rule_category, rule_payer, rule_conf = rule_result
        return (
            rule_desc or cleaned_hint or raw_description,
            _normalize_category(rule_category),
            (rule_payer or "Joao").strip(),
            float(rule_conf),
            "rule",
        )

    custom_rule_result = apply_custom_rule(
        cleaned_hint or raw_description,
        amount,
        is_recurring=False,
    )
    if custom_rule_result is not None:
        custom_category, custom_confidence = custom_rule_result
        return (
            cleaned_hint or raw_description,
            _normalize_category(custom_category),
            "Joao",
            float(custom_confidence),
            "rule",
        )

    history_prediction = _get_history_classifier().predict(cleaned_hint or raw_description)
    if history_prediction is not None:
        category, payer, confidence = history_prediction
        return (
            cleaned_hint or raw_description,
            _normalize_category(category),
            (payer or "Joao").strip(),
            float(confidence),
            "history",
        )

    category = _heuristic_category(raw_description)
    return cleaned_hint or raw_description, category, "Joao", 0.0, "heuristic"
