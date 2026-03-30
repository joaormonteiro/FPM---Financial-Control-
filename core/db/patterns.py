"""
CRUD operations for the padroes_aprendidos (learned patterns) table.

Each entry maps a normalised transaction description to the user-chosen
category, payer, and a human-readable description.  The usage counter drives
confidence growth: confidence = min(0.7 + usage_count * 0.05, 1.0).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Optional

from core.settings import DB_PATH


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_patterns_table(conn: sqlite3.Connection) -> None:
    """Create the padroes_aprendidos table if it does not exist."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS padroes_aprendidos (
            id                       INTEGER PRIMARY KEY AUTOINCREMENT,
            descricao_normalizada    TEXT    NOT NULL UNIQUE,
            descricao_editada_usuario TEXT,
            categoria                TEXT,
            pagador                  TEXT,
            ultima_atualizacao       TEXT    NOT NULL,
            contador_uso             INTEGER NOT NULL DEFAULT 1
        )
        """
    )


def get_pattern(
    normalized_desc: str,
    conn: Optional[sqlite3.Connection] = None,
) -> Optional[dict[str, Any]]:
    """
    Retrieve a learned pattern by its normalised description.

    Returns a dict or ``None`` if no pattern exists.
    """
    key = (normalized_desc or "").strip()
    if not key:
        return None

    owns = conn is None
    if owns:
        conn = _connect()

    assert conn is not None
    ensure_patterns_table(conn)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, descricao_normalizada, descricao_editada_usuario,
               categoria, pagador, ultima_atualizacao, contador_uso
        FROM padroes_aprendidos
        WHERE descricao_normalizada = ?
        """,
        (key,),
    )
    row = cur.fetchone()
    if owns:
        conn.close()

    if row is None:
        return None

    usage = int(row["contador_uso"] or 1)
    confidence = min(0.7 + usage * 0.05, 1.0)
    return {
        "id": int(row["id"]),
        "descricao_normalizada": str(row["descricao_normalizada"] or ""),
        "descricao_editada_usuario": str(row["descricao_editada_usuario"] or ""),
        "categoria": str(row["categoria"] or ""),
        "pagador": str(row["pagador"] or ""),
        "ultima_atualizacao": str(row["ultima_atualizacao"] or ""),
        "contador_uso": usage,
        "confidence": round(confidence, 4),
    }


def upsert_pattern(
    normalized_desc: str,
    description_user: Optional[str],
    category: Optional[str],
    payer: Optional[str],
    conn: Optional[sqlite3.Connection] = None,
) -> None:
    """
    Insert or update a learned pattern.

    If a record already exists for *normalized_desc*, the usage counter is
    incremented and non-empty incoming values overwrite stored ones.
    """
    key = (normalized_desc or "").strip()
    if not key:
        return

    owns = conn is None
    if owns:
        conn = _connect()

    assert conn is not None
    ensure_patterns_table(conn)
    now = datetime.now().isoformat()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, contador_uso, descricao_editada_usuario, categoria, pagador
        FROM padroes_aprendidos
        WHERE descricao_normalizada = ?
        """,
        (key,),
    )
    row = cur.fetchone()

    if row is not None:
        new_desc = (description_user or "").strip() or str(row["descricao_editada_usuario"] or "")
        new_cat = (category or "").strip() or str(row["categoria"] or "")
        new_payer = (payer or "").strip() or str(row["pagador"] or "")
        new_count = int(row["contador_uso"] or 0) + 1
        cur.execute(
            """
            UPDATE padroes_aprendidos
            SET descricao_editada_usuario = ?,
                categoria                 = ?,
                pagador                   = ?,
                ultima_atualizacao        = ?,
                contador_uso              = ?
            WHERE id = ?
            """,
            (new_desc, new_cat, new_payer, now, new_count, int(row["id"])),
        )
    else:
        cur.execute(
            """
            INSERT INTO padroes_aprendidos
                (descricao_normalizada, descricao_editada_usuario, categoria,
                 pagador, ultima_atualizacao, contador_uso)
            VALUES (?, ?, ?, ?, ?, 1)
            """,
            (
                key,
                (description_user or "").strip(),
                (category or "").strip(),
                (payer or "").strip(),
                now,
            ),
        )

    if owns:
        conn.commit()
        conn.close()


# ---------------------------------------------------------------------------
# Backward-compat aliases used by ai/learned_patterns.py
# ---------------------------------------------------------------------------

def ensure_learned_patterns_table(conn: sqlite3.Connection) -> None:
    """Alias for ensure_patterns_table (backward compatibility)."""
    ensure_patterns_table(conn)


def get_learned_pattern(
    descricao_normalizada: str,
    conn: Optional[sqlite3.Connection] = None,
) -> Optional[dict[str, Any]]:
    """Alias for get_pattern (backward compatibility)."""
    return get_pattern(descricao_normalizada, conn)


def upsert_learned_pattern(
    descricao_normalizada: str,
    descricao_editada_usuario: Optional[str],
    categoria: Optional[str],
    pagador: Optional[str],
    conn: Optional[sqlite3.Connection] = None,
) -> None:
    """Alias for upsert_pattern (backward compatibility)."""
    upsert_pattern(descricao_normalizada, descricao_editada_usuario, categoria, pagador, conn)
