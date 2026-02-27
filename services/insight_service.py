from __future__ import annotations

from datetime import datetime
from typing import Any

from services.query_service import get_top_expenses, get_total_by_category

SUPERFLUOUS_CATEGORIES = {
    "LAZER",
    "DELIVERY",
    "RESTAURANTE",
    "ASSINATURA",
    "COMPRAS",
}


def _month_bounds(year: int, month: int) -> tuple[str, str]:
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def _previous_month(year: int, month: int) -> tuple[int, int]:
    if month == 1:
        return year - 1, 12
    return year, month - 1


def _normalize_category(category: str | None) -> str:
    return (category or "Sem categoria").strip().upper()


def _month_expenses_rows(month: int, year: int) -> list[dict[str, Any]]:
    rows = get_top_expenses(limit=1_000_000)
    filtered: list[dict[str, Any]] = []

    for row in rows:
        date_str = str(row.get("date") or "")
        if len(date_str) < 7:
            continue

        row_year = int(date_str[0:4])
        row_month = int(date_str[5:7])
        if row_year == year and row_month == month:
            filtered.append(row)

    return filtered


def _compute_superfluous(month: int, year: int) -> dict[str, float]:
    start_date, end_date = _month_bounds(year, month)
    category_totals = get_total_by_category(start_date, end_date)

    total_superfluous = 0.0
    for category, total in category_totals.items():
        if _normalize_category(category) in SUPERFLUOUS_CATEGORIES and float(total) < 0:
            total_superfluous += abs(float(total))

    month_expenses = _month_expenses_rows(month, year)
    total_month_expenses = sum(abs(float(r.get("amount") or 0.0)) for r in month_expenses)

    percentage_of_month = 0.0
    if total_month_expenses > 0:
        percentage_of_month = (total_superfluous / total_month_expenses) * 100.0

    return {
        "total_superfluous": round(total_superfluous, 2),
        "percentage_of_month": round(percentage_of_month, 2),
    }


def _compute_growth_alerts(month: int, year: int) -> list[dict[str, float | str]]:
    current_start, current_end = _month_bounds(year, month)
    prev_year, prev_month = _previous_month(year, month)
    prev_start, prev_end = _month_bounds(prev_year, prev_month)

    current_totals = get_total_by_category(current_start, current_end)
    previous_totals = get_total_by_category(prev_start, prev_end)

    alerts: list[dict[str, float | str]] = []
    categories = set(current_totals.keys()) | set(previous_totals.keys())

    for category in sorted(categories):
        current_value = abs(float(current_totals.get(category, 0.0)))
        previous_value = abs(float(previous_totals.get(category, 0.0)))

        if current_value <= 0:
            continue

        if previous_value <= 0:
            growth_percent = 100.0
        else:
            growth_percent = ((current_value - previous_value) / previous_value) * 100.0

        if growth_percent > 15.0:
            alerts.append(
                {
                    "category": category,
                    "current_month": round(current_value, 2),
                    "previous_month": round(previous_value, 2),
                    "growth_percent": round(growth_percent, 2),
                }
            )

    return alerts


def _compute_small_expenses(month: int, year: int) -> list[dict[str, float | str]]:
    month_expenses = _month_expenses_rows(month, year)

    grouped: dict[str, float] = {}
    for row in month_expenses:
        amount = float(row.get("amount") or 0.0)
        if not (-40.0 < amount < 0.0):
            continue

        category = str(row.get("category") or "Sem categoria")
        grouped[category] = grouped.get(category, 0.0) + abs(amount)

    result = [
        {
            "category": category,
            "small_expense_total": round(total, 2),
        }
        for category, total in grouped.items()
    ]

    result.sort(key=lambda item: float(item["small_expense_total"]), reverse=True)
    return result


def generate_monthly_insights(month: int, year: int) -> dict[str, Any]:
    return {
        "superfluous": _compute_superfluous(month, year),
        "growth_alerts": _compute_growth_alerts(month, year),
        "small_expenses": _compute_small_expenses(month, year),
    }
