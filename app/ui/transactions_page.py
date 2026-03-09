from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
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

from app.controllers.transaction_controller import TransactionController
from models import ALLOWED_CATEGORIES, ALLOWED_PAYERS


def _format_brl(value: float) -> str:
    text = f"{float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {text}"


class TransactionsPage(QWidget):
    data_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.controller = TransactionController()
        self._rows: list[dict] = []
        self._is_loading = False
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("Transacoes")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        self.refresh_button = QPushButton("Atualizar")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.refresh_button)
        root.addLayout(header)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["Data", "Descricao", "Categoria", "Pagador", "Valor", "Recorrente"]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(
            QTableWidget.EditTrigger.DoubleClicked
            | QTableWidget.EditTrigger.SelectedClicked
            | QTableWidget.EditTrigger.EditKeyPressed
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        root.addWidget(self.table, stretch=1)

        recurring_box = QGroupBox("Recorrencia")
        recurring_layout = QHBoxLayout(recurring_box)
        self.recurrence_group_input = QLineEdit()
        self.recurrence_group_input.setPlaceholderText(
            "Grupo de recorrencia (opcional, ex: manual_123)"
        )
        self.mark_recurring_button = QPushButton("Marcar selecionada como recorrente")
        recurring_layout.addWidget(self.recurrence_group_input, stretch=1)
        recurring_layout.addWidget(self.mark_recurring_button)
        root.addWidget(recurring_box)

        manual_box = QGroupBox("Lancamento Manual")
        manual_layout = QGridLayout(manual_box)
        self.manual_date = QDateEdit()
        self.manual_date.setCalendarPopup(True)
        self.manual_date.setDate(QDate.currentDate())
        self.manual_description = QLineEdit()
        self.manual_amount = QDoubleSpinBox()
        self.manual_amount.setRange(-999999999.99, 999999999.99)
        self.manual_amount.setDecimals(2)
        self.manual_amount.setSingleStep(1.0)
        self.manual_category = QComboBox()
        self.manual_category.addItems(ALLOWED_CATEGORIES)
        self.manual_recurring = QCheckBox("Recorrente")
        self.manual_add_button = QPushButton("Adicionar lancamento")

        manual_layout.addWidget(QLabel("Data"), 0, 0)
        manual_layout.addWidget(self.manual_date, 0, 1)
        manual_layout.addWidget(QLabel("Descricao"), 0, 2)
        manual_layout.addWidget(self.manual_description, 0, 3)
        manual_layout.addWidget(QLabel("Valor"), 1, 0)
        manual_layout.addWidget(self.manual_amount, 1, 1)
        manual_layout.addWidget(QLabel("Categoria"), 1, 2)
        manual_layout.addWidget(self.manual_category, 1, 3)
        manual_layout.addWidget(self.manual_recurring, 2, 0)
        manual_layout.addWidget(self.manual_add_button, 2, 3)
        root.addWidget(manual_box)

        self.status_label = QLabel("")
        root.addWidget(self.status_label)

        self.refresh_button.clicked.connect(self.refresh)
        self.table.itemChanged.connect(self._on_item_changed)
        self.mark_recurring_button.clicked.connect(self._mark_selected_recurring)
        self.manual_add_button.clicked.connect(self._add_manual_transaction)

    def refresh(self) -> None:
        self._rows = self.controller.list_transactions()
        self._populate_table()

    def _populate_table(self) -> None:
        self._is_loading = True
        self.table.blockSignals(True)
        self.table.setRowCount(len(self._rows))

        for row_idx, tx in enumerate(self._rows):
            date_text = self._format_date(str(tx.get("date") or ""))
            description = str(tx.get("description") or "")
            category = str(tx.get("category") or "Outros")
            payer = str(tx.get("payer") or "")
            amount = float(tx.get("amount") or 0.0)
            is_recurring = bool(tx.get("is_recurring"))

            date_item = QTableWidgetItem(date_text)
            desc_item = QTableWidgetItem(description)
            category_item = QTableWidgetItem(category)
            payer_item = QTableWidgetItem(payer)
            amount_item = QTableWidgetItem(_format_brl(amount))
            recurring_item = QTableWidgetItem("Sim" if is_recurring else "Nao")

            date_item.setFlags(date_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            desc_item.setFlags(desc_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            amount_item.setFlags(amount_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            recurring_item.setFlags(recurring_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            self.table.setItem(row_idx, 0, date_item)
            self.table.setItem(row_idx, 1, desc_item)
            self.table.setItem(row_idx, 2, category_item)
            self.table.setItem(row_idx, 3, payer_item)
            self.table.setItem(row_idx, 4, amount_item)
            self.table.setItem(row_idx, 5, recurring_item)

        self.table.resizeColumnsToContents()
        self.table.blockSignals(False)
        self._is_loading = False
        self._set_status(f"{len(self._rows)} transacoes carregadas.", success=True)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._is_loading:
            return

        row_idx = item.row()
        col_idx = item.column()
        if row_idx < 0 or row_idx >= len(self._rows):
            return

        if col_idx not in (2, 3):
            return

        tx = self._rows[row_idx]
        tx_id = int(tx["id"])

        category_item = self.table.item(row_idx, 2)
        payer_item = self.table.item(row_idx, 3)
        if category_item is None or payer_item is None:
            return

        new_category = category_item.text().strip()
        new_payer = payer_item.text().strip()

        if not new_category:
            self._revert_row(row_idx, tx)
            self._set_status("Categoria nao pode ficar vazia.", success=False)
            return

        if new_category not in ALLOWED_CATEGORIES:
            allowed = ", ".join(ALLOWED_CATEGORIES)
            self._revert_row(row_idx, tx)
            self._set_status(f"Categoria invalida. Use: {allowed}", success=False)
            return

        if new_payer and new_payer not in ALLOWED_PAYERS:
            allowed = ", ".join(ALLOWED_PAYERS)
            self._revert_row(row_idx, tx)
            self._set_status(f"Pagador invalido. Use vazio ou: {allowed}", success=False)
            return

        try:
            self.controller.update_transaction(tx_id=tx_id, category=new_category, payer=new_payer or None)
            tx["category"] = new_category
            tx["payer"] = new_payer
            self._set_status(f"Transacao {tx_id} atualizada.", success=True)
            self.data_changed.emit()
        except Exception as exc:
            self._revert_row(row_idx, tx)
            self._set_status(f"Erro ao atualizar transacao {tx_id}: {exc}", success=False)

    def _mark_selected_recurring(self) -> None:
        row_idx = self.table.currentRow()
        if row_idx < 0 or row_idx >= len(self._rows):
            QMessageBox.warning(self, "Transacoes", "Selecione uma transacao na tabela.")
            return

        tx = self._rows[row_idx]
        tx_id = int(tx["id"])
        group_name = self.recurrence_group_input.text().strip() or f"manual_{tx_id}"

        try:
            self.controller.mark_recurring(tx_id=tx_id, group_name=group_name)
            self._set_status(f"Transacao {tx_id} marcada como recorrente.", success=True)
            self.refresh()
            self.data_changed.emit()
        except Exception as exc:
            self._set_status(f"Erro ao marcar recorrencia: {exc}", success=False)

    def _add_manual_transaction(self) -> None:
        qdate = self.manual_date.date()
        tx_date = datetime(qdate.year(), qdate.month(), qdate.day()).date()
        description = self.manual_description.text()
        amount = float(self.manual_amount.value())
        category = self.manual_category.currentText()
        is_recurring = self.manual_recurring.isChecked()

        ok, message = self.controller.add_manual_transaction(
            tx_date=tx_date,
            description=description,
            amount=amount,
            category=category,
            is_recurring=is_recurring,
        )
        self._set_status(message, success=ok)

        if ok:
            self.manual_description.clear()
            self.manual_amount.setValue(0.0)
            self.manual_recurring.setChecked(False)
            self.refresh()
            self.data_changed.emit()

    def _revert_row(self, row_idx: int, tx: dict) -> None:
        self.table.blockSignals(True)
        category_item = self.table.item(row_idx, 2)
        payer_item = self.table.item(row_idx, 3)
        if category_item is not None:
            category_item.setText(str(tx.get("category") or "Outros"))
        if payer_item is not None:
            payer_item.setText(str(tx.get("payer") or ""))
        self.table.blockSignals(False)

    def _set_status(self, message: str, success: bool) -> None:
        color = "#136f1f" if success else "#8a1f11"
        self.status_label.setStyleSheet(f"color: {color}; font-weight: 600;")
        self.status_label.setText(message)

    @staticmethod
    def _format_date(date_text: str) -> str:
        try:
            dt = datetime.strptime(date_text[:10], "%Y-%m-%d")
            return dt.strftime("%d/%m/%Y")
        except Exception:
            return date_text
