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

CATEGORY_OPTIONS: list[tuple[str, str]] = [
    ("alimentacao", "Alimentação"),
    ("transporte", "Transporte"),
    ("lazer", "Lazer"),
    ("assinaturas", "Assinaturas"),
    ("saude", "Saúde"),
    ("investimentos", "Investimentos"),
    ("entrada", "Entrada"),
    ("outros", "Outros"),
]


def _category_key_to_label(value: str) -> str:
    key = (value or "").strip().lower()
    for cat_key, label in CATEGORY_OPTIONS:
        if cat_key == key:
            return label
    return "Outros"


def _label_to_category_key(value: str) -> str:
    text = (value or "").strip().lower()
    for cat_key, label in CATEGORY_OPTIONS:
        if text == label.lower():
            return cat_key
    return "outros"


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
        title = QLabel("Gerenciador de Regras")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        self.refresh_button = QPushButton("Atualizar")
        self.delete_button = QPushButton("Excluir selecionada")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.refresh_button)
        header.addWidget(self.delete_button)
        root.addLayout(header)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Keywords", "Descrição Final", "Categoria", "Prioridade"]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        root.addWidget(self.table, stretch=1)

        create_box = QGroupBox("Criar nova regra")
        create_layout = QGridLayout(create_box)
        self.keywords_input = QLineEdit()
        self.keywords_input.setPlaceholderText("Ex: pix, gustavo, oliveira")
        self.description_input = QLineEdit()
        self.description_input.setPlaceholderText("Descrição final")
        self.category_combo = QComboBox()
        for _, label in CATEGORY_OPTIONS:
            self.category_combo.addItem(label)
        self.priority_input = QLineEdit()
        self.priority_input.setPlaceholderText("100")
        self.create_button = QPushButton("Criar regra")

        create_layout.addWidget(QLabel("Keywords (separadas por vírgula)"), 0, 0)
        create_layout.addWidget(self.keywords_input, 0, 1, 1, 3)
        create_layout.addWidget(QLabel("Descrição final"), 1, 0)
        create_layout.addWidget(self.description_input, 1, 1, 1, 3)
        create_layout.addWidget(QLabel("Categoria"), 2, 0)
        create_layout.addWidget(self.category_combo, 2, 1)
        create_layout.addWidget(QLabel("Prioridade"), 2, 2)
        create_layout.addWidget(self.priority_input, 2, 3)
        create_layout.addWidget(self.create_button, 3, 3)
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
                ", ".join(rule.get("keywords") or []),
                str(rule.get("description_final") or ""),
                _category_key_to_label(str(rule.get("category") or "")),
                str(rule.get("priority") or ""),
            ]
            for col_idx, value in enumerate(values):
                self.table.setItem(row_idx, col_idx, QTableWidgetItem(value))

        self.table.resizeColumnsToContents()
        self._set_status(f"{len(self._rules)} regras carregadas.", success=True)

    def _create_rule(self) -> None:
        ok, message = self.controller.create_rule(
            keywords_text=self.keywords_input.text(),
            description_final=self.description_input.text(),
            category=_label_to_category_key(self.category_combo.currentText()),
            priority_text=self.priority_input.text(),
        )
        self._set_status(message, success=ok)

        if ok:
            self.keywords_input.clear()
            self.description_input.clear()
            self.priority_input.clear()
            self.category_combo.setCurrentIndex(0)
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
