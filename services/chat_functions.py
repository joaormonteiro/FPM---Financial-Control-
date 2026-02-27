from datetime import datetime
from typing import Any

from services.query_service import (
    get_growth_by_category as qs_get_growth_by_category,
    get_recurring as qs_get_recurring,
    get_top_expenses as qs_get_top_expenses,
    get_total_by_category as qs_get_total_by_category,
    get_total_by_month as qs_get_total_by_month,
)


def _validate_month(month: int | None) -> int | None:
    if month is None:
        return None
    m = int(month)
    if m < 1 or m > 12:
        raise ValueError("month deve estar entre 1 e 12")
    return m


def _validate_year(year: int | None) -> int:
    if year is None:
        raise ValueError("year e obrigatorio")
    y = int(year)
    if y < 1900 or y > 2100:
        raise ValueError("year fora do intervalo permitido")
    return y


def _month_range(year: int, month: int) -> tuple[str, str]:
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def get_total_by_month(month: int, year: int) -> dict[str, Any]:
    y = _validate_year(year)
    m = _validate_month(month)
    if m is None:
        raise ValueError("month e obrigatorio")

    monthly_data = qs_get_total_by_month(y)
    key = f"{y:04d}-{m:02d}"
    return {
        "month": m,
        "year": y,
        "period": key,
        "total": float(monthly_data.get(key, 0.0)),
    }


def get_total_by_category(month: int | None, year: int) -> dict[str, Any]:
    y = _validate_year(year)
    m = _validate_month(month)

    if m is None:
        start_date = f"{y:04d}-01-01"
        end_date = f"{y + 1:04d}-01-01"
    else:
        start_date, end_date = _month_range(y, m)

    data = qs_get_total_by_category(start_date, end_date)
    return {
        "month": m,
        "year": y,
        "totals": data,
    }


def get_top_expenses(month: int | None, year: int, limit: int = 10) -> list[dict[str, Any]]:
    y = _validate_year(year)
    m = _validate_month(month)
    lim = int(limit)
    if lim <= 0:
        raise ValueError("limit deve ser maior que zero")

    # Usa apenas query_service e filtra em memoria por periodo solicitado.
    rows = qs_get_top_expenses(limit=1000000)

    filtered: list[dict[str, Any]] = []
    for row in rows:
        date_str = str(row.get("date") or "")
        if len(date_str) < 7:
            continue

        row_year = int(date_str[0:4])
        row_month = int(date_str[5:7])

        if row_year != y:
            continue
        if m is not None and row_month != m:
            continue

        filtered.append(
            {
                "date": row.get("date"),
                "description": row.get("description"),
                "amount": float(row.get("amount") or 0.0),
                "category": row.get("category"),
            }
        )

        if len(filtered) >= lim:
            break

    return filtered


def get_recurring_expenses() -> list[dict[str, Any]]:
    return qs_get_recurring()


def get_category_growth(category: str, year: int) -> dict[str, Any]:
    if not category or not str(category).strip():
        raise ValueError("category e obrigatoria")

    y = _validate_year(year)
    series = qs_get_growth_by_category(str(category))

    filtered = {
        period: float(total)
        for period, total in series.items()
        if period.startswith(f"{y:04d}-")
    }

    return {
        "category": str(category),
        "year": y,
        "growth": filtered,
    }
