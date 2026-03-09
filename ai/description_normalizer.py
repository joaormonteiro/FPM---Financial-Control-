from __future__ import annotations

import re
import unicodedata

_DATE_RE = re.compile(r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b")
_NUMBER_RE = re.compile(r"\b\d+\b")
_NON_WORD_RE = re.compile(r"[^a-z0-9\s]")
_SPACES_RE = re.compile(r"\s+")

# "pix" e mantido para preservar o tipo de transacao (ex: "pix joao silva").
GENERIC_BANK_WORDS = {
    "enviado",
    "enviada",
    "recebido",
    "recebida",
    "transferencia",
    "transferencias",
    "pagamento",
    "debito",
    "credito",
    "via",
    "banco",
    "sa",
    "ltda",
    "para",
    "de",
    "do",
    "da",
}


def _strip_accents(text: str) -> str:
    return (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode("ascii")
    )


def normalize_description(description: str) -> str:
    text = _strip_accents((description or "").strip().lower())
    if not text:
        return ""

    text = _DATE_RE.sub(" ", text)
    text = _NON_WORD_RE.sub(" ", text)
    text = _NUMBER_RE.sub(" ", text)
    tokens = [token for token in text.split() if token and token not in GENERIC_BANK_WORDS]
    normalized = _SPACES_RE.sub(" ", " ".join(tokens)).strip()
    return normalized

