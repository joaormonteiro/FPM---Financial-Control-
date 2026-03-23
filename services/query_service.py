import sqlite3
from typing import Any

from core.settings import DB_PATH


def get_total_by_month(year: int) -> dict[str, float]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        """
        SELECT strftime('%Y-%m', date) AS ym, SUM(amount) AS total
        FROM transactions
        WHERE strftime('%Y', date) = ?
        GROUP BY ym
        ORDER BY ym ASC
        """,
        (str(year),),
    )
    rows = cur.fetchall()
    conn.close()

    return {row["ym"]: float(row["total"] or 0.0) for row in rows if row["ym"]}


def get_total_by_category(start_date: str | None, end_date: str | None) -> dict[str, float]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    base_sql = """
        SELECT category, SUM(amount) AS total
        FROM transactions
    """
    params: list[Any] = []

    if start_date is None and end_date is None:
        where_sql = ""
    elif start_date is not None and end_date is not None:
        where_sql = "WHERE date >= ? AND date <= ?"
        params.extend([start_date, end_date])
    elif start_date is not None:
        where_sql = "WHERE date >= ?"
        params.append(start_date)
    else:
        where_sql = "WHERE date <= ?"
        params.append(end_date)

    sql = f"""
        {base_sql}
        {where_sql}
        GROUP BY category
        ORDER BY category ASC
    """

    cur.execute(sql, tuple(params))
    rows = cur.fetchall()
    conn.close()

    result: dict[str, float] = {}
    for row in rows:
        key = row["category"] if row["category"] is not None else ""
        result[str(key)] = float(row["total"] or 0.0)
    return result


def get_top_expenses(limit: int = 10) -> list[dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        """
        SELECT date, description, amount, category
        FROM transactions
        WHERE amount < 0
        ORDER BY amount ASC
        LIMIT ?
        """,
        (int(limit),),
    )
    rows = cur.fetchall()
    conn.close()

    return [
        {
            "date": row["date"],
            "description": row["description"],
            "amount": float(row["amount"] or 0.0),
            "category": row["category"],
        }
        for row in rows
    ]


def get_recurring() -> list[dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            COALESCE(cleaned_description, description) AS description,
            amount,
            category,
            NULL AS recurrence_frequency,
            recurrence_group_id
        FROM transactions
        WHERE is_recurring = 1
        ORDER BY date ASC
        """
    )
    rows = cur.fetchall()
    conn.close()

    return [
        {
            "description": row["description"],
            "amount": float(row["amount"] or 0.0),
            "category": row["category"],
            "recurrence_frequency": row["recurrence_frequency"],
            "recurrence_group_id": row["recurrence_group_id"],
        }
        for row in rows
    ]


def get_growth_by_category(category: str) -> dict[str, float]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        """
        SELECT strftime('%Y-%m', date) AS ym, SUM(amount) AS total
        FROM transactions
        WHERE category = ?
        GROUP BY ym
        ORDER BY ym ASC
        """,
        (category,),
    )
    rows = cur.fetchall()
    conn.close()

    return {row["ym"]: float(row["total"] or 0.0) for row in rows if row["ym"]}
