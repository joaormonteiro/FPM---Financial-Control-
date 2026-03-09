from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.controllers.rules_controller import RulesController


class RulesPage(QWidget):
    data_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.controller = RulesController()
        self._rules: list[dict] = []
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("Regras Personalizadas")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        self.refresh_button = QPushButton("Atualizar")
        self.delete_button = QPushButton("Excluir selecionada")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.refresh_button)
        header.addWidget(self.delete_button)
        root.addLayout(header)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            [
                "ID",
                "Descricao contem",
                "Valor minimo",
                "Valor maximo",
                "Recorrente",
                "Categoria destino",
            ]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        root.addWidget(self.table, stretch=1)

        create_box = QGroupBox("Criar nova regra")
        create_layout = QGridLayout(create_box)
        self.description_contains_input = QLineEdit()
        self.amount_min_input = QLineEdit()
        self.amount_max_input = QLineEdit()
        self.recurring_combo = QComboBox()
        self.recurring_combo.addItems(["Qualquer", "Sim", "Nao"])
        self.category_input = QLineEdit()
        self.create_button = QPushButton("Criar regra")

        create_layout.addWidget(QLabel("Descricao contem"), 0, 0)
        create_layout.addWidget(self.description_contains_input, 0, 1)
        create_layout.addWidget(QLabel("Valor minimo"), 0, 2)
        create_layout.addWidget(self.amount_min_input, 0, 3)
        create_layout.addWidget(QLabel("Valor maximo"), 1, 0)
        create_layout.addWidget(self.amount_max_input, 1, 1)
        create_layout.addWidget(QLabel("Recorrente"), 1, 2)
        create_layout.addWidget(self.recurring_combo, 1, 3)
        create_layout.addWidget(QLabel("Categoria destino"), 2, 0)
        create_layout.addWidget(self.category_input, 2, 1, 1, 2)
        create_layout.addWidget(self.create_button, 2, 3)
        root.addWidget(create_box)

        self.status_label = QLabel("")
        root.addWidget(self.status_label)

        self.refresh_button.clicked.connect(self.refresh)
        self.create_button.clicked.connect(self._create_rule)
        self.delete_button.clicked.connect(self._delete_selected_rule)

    def refresh(self) -> None:
        self._rules = self.controller.list_rules()
        self.table.setRowCount(len(self._rules))

        for row_idx, rule in enumerate(self._rules):
            values = [
                str(rule.get("id") or ""),
                str(rule.get("description_contains") or ""),
                "" if rule.get("amount_min") is None else str(rule.get("amount_min")),
                "" if rule.get("amount_max") is None else str(rule.get("amount_max")),
                self._format_recurring(rule.get("is_recurring")),
                str(rule.get("set_category") or ""),
            ]
            for col_idx, value in enumerate(values):
                self.table.setItem(row_idx, col_idx, QTableWidgetItem(value))

        self.table.resizeColumnsToContents()
        self._set_status(f"{len(self._rules)} regras carregadas.", success=True)

    def _create_rule(self) -> None:
        ok, message = self.controller.create_rule(
            description_contains=self.description_contains_input.text(),
            amount_min_text=self.amount_min_input.text(),
            amount_max_text=self.amount_max_input.text(),
            recurring_option=self.recurring_combo.currentText(),
            set_category=self.category_input.text(),
        )
        self._set_status(message, success=ok)

        if ok:
            self.description_contains_input.clear()
            self.amount_min_input.clear()
            self.amount_max_input.clear()
            self.category_input.clear()
            self.recurring_combo.setCurrentIndex(0)
            self.refresh()
            self.data_changed.emit()

    def _delete_selected_rule(self) -> None:
        row_idx = self.table.currentRow()
        if row_idx < 0 or row_idx >= len(self._rules):
            QMessageBox.warning(self, "Regras", "Selecione uma regra para excluir.")
            return

        rule_id = str(self._rules[row_idx].get("id") or "")
        ok, message = self.controller.remove_rule(rule_id)
        self._set_status(message, success=ok)

        if ok:
            self.refresh()
            self.data_changed.emit()

    def _set_status(self, message: str, success: bool) -> None:
        color = "#136f1f" if success else "#8a1f11"
        self.status_label.setStyleSheet(f"color: {color}; font-weight: 600;")
        self.status_label.setText(message)

    @staticmethod
    def _format_recurring(value: object) -> str:
        if value is True:
            return "Sim"
        if value is False:
            return "Nao"
        return "Qualquer"
