from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from core.settings import DB_PATH


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def ensure_learned_patterns_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS padroes_aprendidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            descricao_normalizada TEXT NOT NULL UNIQUE,
            descricao_editada_usuario TEXT,
            categoria TEXT,
            pagador TEXT,
            ultima_atualizacao TEXT NOT NULL,
            contador_uso INTEGER NOT NULL DEFAULT 1
        )
        """
    )


def get_learned_pattern(
    descricao_normalizada: str,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    key = (descricao_normalizada or "").strip()
    if not key:
        return None

    owns_connection = conn is None
    if owns_connection:
        conn = _connect()
    assert conn is not None
    conn.row_factory = sqlite3.Row
    ensure_learned_patterns_table(conn)

    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            id,
            descricao_normalizada,
            descricao_editada_usuario,
            categoria,
            pagador,
            ultima_atualizacao,
            contador_uso
        FROM padroes_aprendidos
        WHERE descricao_normalizada = ?
        """,
        (key,),
    )
    row = cur.fetchone()

    if owns_connection:
        conn.close()

    if not row:
        return None

    return {
        "id": int(row["id"]),
        "descricao_normalizada": str(row["descricao_normalizada"] or ""),
        "descricao_editada_usuario": str(row["descricao_editada_usuario"] or ""),
        "categoria": str(row["categoria"] or ""),
        "pagador": str(row["pagador"] or ""),
        "ultima_atualizacao": str(row["ultima_atualizacao"] or ""),
        "contador_uso": int(row["contador_uso"] or 0),
    }


def upsert_learned_pattern(
    descricao_normalizada: str,
    descricao_editada_usuario: str | None,
    categoria: str | None,
    pagador: str | None,
    conn: sqlite3.Connection | None = None,
) -> None:
    key = (descricao_normalizada or "").strip()
    if not key:
        return

    owns_connection = conn is None
    if owns_connection:
        conn = _connect()
    assert conn is not None
    ensure_learned_patterns_table(conn)

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

    if row:
        cur.execute(
            """
            UPDATE padroes_aprendidos
            SET descricao_editada_usuario = ?,
                categoria = ?,
                pagador = ?,
                ultima_atualizacao = ?,
                contador_uso = ?
            WHERE id = ?
            """,
            (
                (descricao_editada_usuario or "").strip() or row[2],
                (categoria or "").strip() or row[3],
                (pagador or "").strip() or row[4],
                now,
                int(row[1] or 0) + 1,
                int(row[0]),
            ),
        )
    else:
        cur.execute(
            """
            INSERT INTO padroes_aprendidos
            (descricao_normalizada, descricao_editada_usuario, categoria, pagador, ultima_atualizacao, contador_uso)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                key,
                (descricao_editada_usuario or "").strip(),
                (categoria or "").strip(),
                (pagador or "").strip(),
                now,
                1,
            ),
        )

    if owns_connection:
        conn.commit()
        conn.close()
