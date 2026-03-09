from __future__ import annotations

import re
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from ai.financial_advisor import generate_financial_advice
from db import connect
from services.insight_service import generate_monthly_insights
from services.query_service import get_total_by_category

try:
    from PySide6.QtCharts import (
        QBarCategoryAxis,
        QBarSeries,
        QBarSet,
        QChart,
        QChartView,
        QValueAxis,
    )

    HAS_QT_CHARTS = True
except Exception:
    HAS_QT_CHARTS = False


def _format_brl(value: float) -> str:
    amount = float(value)
    text = f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {text}"


def _month_bounds(now: datetime) -> tuple[str, str]:
    start = datetime(now.year, now.month, 1)
    if now.month == 12:
        end = datetime(now.year + 1, 1, 1)
    else:
        end = datetime(now.year, now.month + 1, 1)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


class DashboardPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._latest_insights: dict | None = None
        self._investment_re = re.compile(r"\bAplicacao\b|\bCDB\b|\bInvest", re.IGNORECASE)
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        metric_grid = QGridLayout()
        metric_grid.setHorizontalSpacing(10)
        metric_grid.setVerticalSpacing(10)

        self.total_spent_label = QLabel("R$ 0,00")
        self.parents_paid_label = QLabel("R$ 0,00")
        self.total_received_label = QLabel("R$ 0,00")

        metric_grid.addWidget(self._metric_box("Total Gasto no Mes", self.total_spent_label), 0, 0)
        metric_grid.addWidget(self._metric_box("Pago pelos Pais", self.parents_paid_label), 0, 1)
        metric_grid.addWidget(self._metric_box("Total Recebido", self.total_received_label), 0, 2)

        root.addLayout(metric_grid)

        actions = QHBoxLayout()
        self.refresh_button = QPushButton("Atualizar Dashboard")
        self.analyze_button = QPushButton("Analisar meu mes")
        self.advice_button = QPushButton("Onde posso economizar?")
        actions.addWidget(self.refresh_button)
        actions.addWidget(self.analyze_button)
        actions.addWidget(self.advice_button)
        actions.addStretch(1)
        root.addLayout(actions)

        chart_box = QGroupBox("Gastos por Categoria")
        chart_layout = QVBoxLayout(chart_box)

        if HAS_QT_CHARTS:
            self.chart_view = QChartView()
            self.chart_view.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            chart_layout.addWidget(self.chart_view)
            self.chart_fallback = None
        else:
            self.chart_view = None
            self.chart_fallback = QPlainTextEdit()
            self.chart_fallback.setReadOnly(True)
            chart_layout.addWidget(self.chart_fallback)

        root.addWidget(chart_box, stretch=1)

        insights_layout = QHBoxLayout()
        self.insights_text = QPlainTextEdit()
        self.insights_text.setReadOnly(True)
        self.insights_text.setPlaceholderText("Insights mensais aparecerao aqui.")
        self.advice_text = QPlainTextEdit()
        self.advice_text.setReadOnly(True)
        self.advice_text.setPlaceholderText("Conselho financeiro aparecera aqui.")

        insights_group = QGroupBox("Insights Mensais")
        insights_group_layout = QVBoxLayout(insights_group)
        insights_group_layout.addWidget(self.insights_text)
        advice_group = QGroupBox("Aconselhamento Financeiro")
        advice_group_layout = QVBoxLayout(advice_group)
        advice_group_layout.addWidget(self.advice_text)
        insights_layout.addWidget(insights_group, stretch=1)
        insights_layout.addWidget(advice_group, stretch=1)

        root.addLayout(insights_layout, stretch=1)

        self.refresh_button.clicked.connect(self.refresh)
        self.analyze_button.clicked.connect(self._generate_insights)
        self.advice_button.clicked.connect(self._generate_advice)

    def _metric_box(self, title: str, value_label: QLabel) -> QGroupBox:
        box = QGroupBox(title)
        layout = QVBoxLayout(box)
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        value_label.setStyleSheet("font-size: 22px; font-weight: 600;")
        layout.addWidget(value_label)
        return box

    def refresh(self) -> None:
        now = datetime.now()
        start_date, end_date = _month_bounds(now)
        spent, parents_paid, received = self._compute_month_metrics(start_date, end_date)

        self.total_spent_label.setText(_format_brl(abs(spent)))
        self.parents_paid_label.setText(_format_brl(abs(parents_paid)))
        self.total_received_label.setText(_format_brl(received))

        category_totals = get_total_by_category(start_date, end_date)
        expenses_by_category = {
            (category or "Sem categoria"): abs(float(total))
            for category, total in category_totals.items()
            if float(total) < 0
        }
        self._update_category_chart(expenses_by_category)

    def _compute_month_metrics(self, start_date: str, end_date: str) -> tuple[float, float, float]:
        conn = connect()
        conn.row_factory = None
        cur = conn.cursor()
        cur.execute(
            """
            SELECT amount, payer, description, description_ai
            FROM transactions
            WHERE date >= ? AND date < ?
            """,
            (start_date, end_date),
        )
        rows = cur.fetchall()
        conn.close()

        total_spent = 0.0
        parents_paid = 0.0
        total_received = 0.0

        for amount, payer, description, description_ai in rows:
            value = float(amount or 0.0)
            raw_desc = str(description or "")
            ai_desc = str(description_ai or "")
            merged = f"{raw_desc} {ai_desc}"
            is_investment = bool(self._investment_re.search(merged))

            if value < 0 and not is_investment:
                total_spent += value
            if value < 0 and str(payer or "").strip() == "Pais":
                parents_paid += value
            if value > 0:
                total_received += value

        return total_spent, parents_paid, total_received

    def _update_category_chart(self, expenses_by_category: dict[str, float]) -> None:
        if HAS_QT_CHARTS and self.chart_view is not None:
            chart = QChart()
            chart.setTitle("Despesas por categoria")

            if not expenses_by_category:
                chart.setTitle("Despesas por categoria (sem dados no periodo)")
                self.chart_view.setChart(chart)
                return

            categories = list(expenses_by_category.keys())
            values = [float(expenses_by_category[key]) for key in categories]

            bar_set = QBarSet("Gastos")
            for value in values:
                bar_set.append(value)

            series = QBarSeries()
            series.append(bar_set)
            chart.addSeries(series)

            axis_x = QBarCategoryAxis()
            axis_x.append(categories)
            chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
            series.attachAxis(axis_x)

            max_value = max(values) if values else 0.0
            axis_y = QValueAxis()
            axis_y.setRange(0.0, max(10.0, max_value * 1.2))
            axis_y.setLabelFormat("R$ %.2f")
            chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
            series.attachAxis(axis_y)

            self.chart_view.setChart(chart)
            return

        if self.chart_fallback is None:
            return

        if not expenses_by_category:
            self.chart_fallback.setPlainText("Sem dados para o periodo atual.")
            return

        ordered = sorted(expenses_by_category.items(), key=lambda item: item[1], reverse=True)
        lines = [f"{category}: {_format_brl(value)}" for category, value in ordered]
        self.chart_fallback.setPlainText("\n".join(lines))

    def _generate_insights(self) -> None:
        now = datetime.now()
        self._latest_insights = generate_monthly_insights(now.month, now.year)
        self.insights_text.setPlainText(self._format_insights(self._latest_insights))

    def _generate_advice(self) -> None:
        if self._latest_insights is None:
            self._generate_insights()

        if self._latest_insights is None:
            return

        advice = generate_financial_advice(self._latest_insights)
        self.advice_text.setPlainText(advice)

    def _format_insights(self, insight_data: dict) -> str:
        superfluous = insight_data.get("superfluous", {})
        growth_alerts = insight_data.get("growth_alerts", [])
        small_expenses = insight_data.get("small_expenses", [])

        lines = [
            f"Gastos superfluos no mes: {_format_brl(float(superfluous.get('total_superfluous', 0.0)))}",
            f"Percentual sobre despesas do mes: {float(superfluous.get('percentage_of_month', 0.0)):.2f}%",
            "",
            "Categorias com crescimento acima de 15%:",
        ]

        if growth_alerts:
            for item in growth_alerts:
                lines.append(
                    f"- {item.get('category')}: {float(item.get('growth_percent', 0.0)):.2f}% "
                    f"(atual {_format_brl(float(item.get('current_month', 0.0)))}, "
                    f"anterior {_format_brl(float(item.get('previous_month', 0.0)))})"
                )
        else:
            lines.append("- Nenhuma categoria com crescimento acima de 15%.")

        lines.append("")
        lines.append("Pequenas despesas acumuladas (< R$ 40):")
        if small_expenses:
            for item in small_expenses:
                lines.append(
                    f"- {item.get('category')}: {_format_brl(float(item.get('small_expense_total', 0.0)))}"
                )
        else:
            lines.append("- Nao ha pequenas despesas acumuladas no periodo.")

        return "\n".join(lines)
