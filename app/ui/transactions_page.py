"""
Transactions page with a clean, artifact-free QComboBox category delegate.

Key delegate fixes:
  • updateEditorGeometry properly fills the cell rect
  • setFrame(False) removes border artifacts
  • paint() uses initStyleOption so text renders cleanly in all states
  • Category change is committed immediately on selection
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QDate, QModelIndex, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
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
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QStyle,
)

from app.controllers.transaction_controller import TransactionController
from core.models import ALLOWED_CATEGORIES, ALLOWED_PAYERS, capitalize_first

# ---------------------------------------------------------------------------
# Category options – keep in sync with ALLOWED_CATEGORIES
# ---------------------------------------------------------------------------
CATEGORY_OPTIONS: list[tuple[str, str]] = [
    ("alimentacao", "Alimentação"),
    ("assinaturas", "Assinaturas"),
    ("educacao", "Educação"),
    ("entrada", "Entrada"),
    ("investimentos", "Investimentos"),
    ("lazer", "Lazer"),
    ("moradia", "Moradia"),
    ("outros", "Outros"),
    ("saude", "Saúde"),
    ("transporte", "Transporte"),
]

CATEGORY_KEYS: set[str] = {k for k, _ in CATEGORY_OPTIONS}

# Subtle background tints per category
_CATEGORY_TINT: dict[str, str] = {
    "alimentacao": "#fff8e1",
    "assinaturas": "#e8eaf6",
    "educacao": "#e3f2fd",
    "entrada": "#e8f5e9",
    "investimentos": "#f3e5f5",
    "lazer": "#fce4ec",
    "moradia": "#e0f7fa",
    "outros": "#ffffff",
    "saude": "#fff3e0",
    "transporte": "#f1f8e9",
}

# Table column indices
_COL_DATE = 0
_COL_DESC = 1
_COL_CATEGORY = 2
_COL_PAYER = 3
_COL_AMOUNT = 4
_COL_SOURCE = 5
_COL_CONFIDENCE = 6
_COL_NOTE = 7
_COL_RECURRING = 8


def _key_to_label(value: str) -> str:
    key = (value or "").strip().lower()
    for cat_key, label in CATEGORY_OPTIONS:
        if cat_key == key:
            return label
    return "Outros"


def _label_to_key(value: str) -> str | None:
    text = (value or "").strip().lower()
    for cat_key, label in CATEGORY_OPTIONS:
        if text == label.lower():
            return cat_key
    if text in CATEGORY_KEYS:
        return text
    return None


# ---------------------------------------------------------------------------
# ComboBox delegate
# ---------------------------------------------------------------------------

class CategoryDelegate(QStyledItemDelegate):
    """
    Inline ComboBox editor for the category column.

    Fixes:
    - updateEditorGeometry fills the full cell rect (no offset artifacts)
    - setFrame(False) removes the extra border
    - paint() renders the display text cleanly in all states
    - currentIndexChanged triggers immediate commitData
    """

    def createEditor(
        self,
        parent: QWidget,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> QComboBox:
        combo = QComboBox(parent)
        combo.setFrame(False)
        for _, label in CATEGORY_OPTIONS:
            combo.addItem(label)
        # Commit immediately when the user picks an item
        combo.currentIndexChanged.connect(
            lambda _: self.commitData.emit(combo)  # type: ignore[attr-defined]
        )
        return combo

    def setEditorData(self, editor: QComboBox, index: QModelIndex) -> None:
        current = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        idx = editor.findText(current)
        if idx < 0:
            idx = editor.findText(_key_to_label(current))
        editor.setCurrentIndex(max(idx, 0))

    def setModelData(
        self,
        editor: QComboBox,
        model: object,
        index: QModelIndex,
    ) -> None:
        from PySide6.QtCore import Qt as _Qt

        getattr(model, "setData")(index, editor.currentText(), _Qt.ItemDataRole.EditRole)

    def updateEditorGeometry(
        self,
        editor: QWidget,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        editor.setGeometry(option.rect)

    def paint(
        self,
        painter: object,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        QApplication.style().drawControl(
            QStyle.ControlElement.CE_ItemViewItem, opt, painter  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Transactions page
# ---------------------------------------------------------------------------

class TransactionsPage(QWidget):
    """Main transactions view with inline category editing."""

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

        # Header
        header = QHBoxLayout()
        title = QLabel("Transações")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        self.refresh_button = QPushButton("Atualizar")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.refresh_button)
        root.addLayout(header)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels(
            ["Data", "Descrição", "Categoria", "Pagador", "Valor",
             "Origem", "Confiança", "Observação", "Recorrente"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(False)  # we paint our own tints
        self.table.setItemDelegateForColumn(_COL_CATEGORY, CategoryDelegate(self.table))
        self.table.itemChanged.connect(self._on_item_changed)
        root.addWidget(self.table, stretch=1)

        # Save button
        actions = QHBoxLayout()
        self.save_button = QPushButton("Salvar alterações")
        self.save_button.setStyleSheet("font-weight: 600;")
        actions.addStretch(1)
        actions.addWidget(self.save_button)
        root.addLayout(actions)

        # Recurrence
        recurring_box = QGroupBox("Recorrência")
        recurring_layout = QHBoxLayout(recurring_box)
        self.recurrence_group_input = QLineEdit()
        self.recurrence_group_input.setPlaceholderText(
            "Grupo de recorrência (ex: netflix_mensal)"
        )
        self.mark_recurring_button = QPushButton("Marcar selecionada como recorrente")
        recurring_layout.addWidget(self.recurrence_group_input, stretch=1)
        recurring_layout.addWidget(self.mark_recurring_button)
        root.addWidget(recurring_box)

        # Manual entry
        manual_box = QGroupBox("Lançamento Manual")
        manual_layout = QGridLayout(manual_box)
        self.manual_date = QDateEdit()
        self.manual_date.setCalendarPopup(True)
        self.manual_date.setDate(QDate.currentDate())
        self.manual_description = QLineEdit()
        self.manual_description.setPlaceholderText("Descrição")
        self.manual_amount = QDoubleSpinBox()
        self.manual_amount.setRange(-999_999_999.99, 999_999_999.99)
        self.manual_amount.setDecimals(2)
        self.manual_amount.setSingleStep(1.0)
        self.manual_category = QComboBox()
        for _, label in CATEGORY_OPTIONS:
            self.manual_category.addItem(label)
        self.manual_recurring = QCheckBox("Recorrente")
        self.manual_add_button = QPushButton("Adicionar lançamento")

        manual_layout.addWidget(QLabel("Data"), 0, 0)
        manual_layout.addWidget(self.manual_date, 0, 1)
        manual_layout.addWidget(QLabel("Descrição"), 0, 2)
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

        # Connections
        self.refresh_button.clicked.connect(self.refresh)
        self.save_button.clicked.connect(self._save_selected_row)
        self.mark_recurring_button.clicked.connect(self._mark_selected_recurring)
        self.manual_add_button.clicked.connect(self._add_manual_transaction)

    def refresh(self) -> None:
        """Reload transactions from the database."""
        self._rows = self.controller.list_transactions()
        self._populate_table()

    def _populate_table(self) -> None:
        self._is_loading = True
        self.table.blockSignals(True)
        self.table.setRowCount(len(self._rows))

        for row_idx, tx in enumerate(self._rows):
            date_text = self._fmt_date(str(tx.get("date") or ""))
            description = capitalize_first(str(tx.get("description") or ""))
            raw_desc = str(tx.get("raw_description") or "")
            category_label = _key_to_label(str(tx.get("category") or "outros"))
            payer = str(tx.get("payer") or "")
            amount = float(tx.get("amount") or 0.0)
            source = str(tx.get("classification_source") or "")
            confidence = float(tx.get("confidence") or 0.0)
            note = str(tx.get("note") or "")
            is_recurring = bool(tx.get("is_recurring"))
            cat_key = str(tx.get("category") or "outros")

            date_item = QTableWidgetItem(date_text)
            desc_item = QTableWidgetItem(description)
            if raw_desc and raw_desc != description:
                desc_item.setToolTip(f"Original: {raw_desc}")
            category_item = QTableWidgetItem(category_label)
            payer_item = QTableWidgetItem(payer)
            amount_item = QTableWidgetItem(f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            source_item = QTableWidgetItem(source)
            confidence_item = QTableWidgetItem(f"{confidence:.0%}")
            note_item = QTableWidgetItem(note)
            recurring_item = QTableWidgetItem("✓" if is_recurring else "")

            # Non-editable columns
            for item in (date_item, source_item, confidence_item, recurring_item):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            amount_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            # Amount colour
            if amount < 0:
                amount_item.setForeground(QColor("#b71c1c"))
            else:
                amount_item.setForeground(QColor("#1b5e20"))

            # Row tint by category
            tint = QColor(_CATEGORY_TINT.get(cat_key, "#ffffff"))
            for item in (date_item, desc_item, category_item, payer_item,
                         amount_item, source_item, confidence_item, note_item, recurring_item):
                item.setBackground(tint)

            self.table.setItem(row_idx, _COL_DATE, date_item)
            self.table.setItem(row_idx, _COL_DESC, desc_item)
            self.table.setItem(row_idx, _COL_CATEGORY, category_item)
            self.table.setItem(row_idx, _COL_PAYER, payer_item)
            self.table.setItem(row_idx, _COL_AMOUNT, amount_item)
            self.table.setItem(row_idx, _COL_SOURCE, source_item)
            self.table.setItem(row_idx, _COL_CONFIDENCE, confidence_item)
            self.table.setItem(row_idx, _COL_NOTE, note_item)
            self.table.setItem(row_idx, _COL_RECURRING, recurring_item)

        self.table.resizeColumnsToContents()
        self.table.blockSignals(False)
        self._is_loading = False
        self._set_status(f"{len(self._rows)} transações carregadas.", success=True)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        """Auto-save when the category ComboBox delegate commits a change."""
        if self._is_loading:
            return
        if item.column() == _COL_CATEGORY:
            self._save_row(item.row())

    def _save_selected_row(self) -> None:
        row_idx = self.table.currentRow()
        if row_idx < 0 or row_idx >= len(self._rows):
            QMessageBox.warning(self, "Transações", "Selecione uma transação na tabela.")
            return
        self._save_row(row_idx)

    def _save_row(self, row_idx: int) -> None:
        if row_idx < 0 or row_idx >= len(self._rows):
            return

        tx = self._rows[row_idx]
        tx_id = int(tx["id"])

        desc_item = self.table.item(row_idx, _COL_DESC)
        cat_item = self.table.item(row_idx, _COL_CATEGORY)
        payer_item = self.table.item(row_idx, _COL_PAYER)
        amount_item = self.table.item(row_idx, _COL_AMOUNT)
        note_item = self.table.item(row_idx, _COL_NOTE)

        if not all([desc_item, cat_item, payer_item, amount_item, note_item]):
            self._set_status("Linha incompleta — não foi possível salvar.", success=False)
            return

        new_desc = capitalize_first((desc_item.text() or "").strip())
        new_cat = _label_to_key((cat_item.text() or "").strip())
        new_payer = (payer_item.text() or "").strip().lower()
        note = (note_item.text() or "").strip()

        if not new_desc:
            self._set_status("Descrição não pode ficar vazia.", success=False)
            return
        if not new_cat or new_cat not in CATEGORY_KEYS:
            self._set_status("Categoria inválida.", success=False)
            return
        if new_payer and new_payer not in ALLOWED_PAYERS:
            self._set_status(f"Pagador inválido. Use: {', '.join(ALLOWED_PAYERS)}", success=False)
            return

        try:
            new_amount = self._parse_amount(amount_item.text())
        except ValueError:
            self._set_status("Valor inválido.", success=False)
            return

        try:
            self.controller.update_transaction(
                tx_id=tx_id,
                description=new_desc,
                category=new_cat,
                payer=new_payer or None,
                amount=new_amount,
                note=note or None,
            )
            self._set_status(f"Transação {tx_id} salva.", success=True)
            self.refresh()
            self.data_changed.emit()
        except Exception as exc:
            self._set_status(f"Erro ao salvar: {exc}", success=False)

    def _mark_selected_recurring(self) -> None:
        row_idx = self.table.currentRow()
        if row_idx < 0 or row_idx >= len(self._rows):
            QMessageBox.warning(self, "Transações", "Selecione uma transação.")
            return

        tx = self._rows[row_idx]
        tx_id = int(tx["id"])
        group = self.recurrence_group_input.text().strip() or f"manual_{tx_id}"
        try:
            self.controller.mark_recurring(tx_id=tx_id, group_name=group)
            self._set_status(f"Transação {tx_id} marcada como recorrente.", success=True)
            self.refresh()
            self.data_changed.emit()
        except Exception as exc:
            self._set_status(f"Erro: {exc}", success=False)

    def _add_manual_transaction(self) -> None:
        qdate = self.manual_date.date()
        tx_date = datetime(qdate.year(), qdate.month(), qdate.day()).date()
        description = capitalize_first(self.manual_description.text())
        amount = float(self.manual_amount.value())
        selected_label = self.manual_category.currentText()
        category = _label_to_key(selected_label) or "outros"
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

    def _set_status(self, message: str, success: bool) -> None:
        color = "#1b5e20" if success else "#b71c1c"
        self.status_label.setStyleSheet(f"color: {color}; font-weight: 600;")
        self.status_label.setText(message)

    @staticmethod
    def _parse_amount(text: str) -> float:
        cleaned = (text or "").strip().replace("R$", "").replace(" ", "")
        if "," in cleaned and "." in cleaned:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        elif "," in cleaned:
            cleaned = cleaned.replace(",", ".")
        if not cleaned:
            raise ValueError("empty amount")
        return float(cleaned)

    @staticmethod
    def _fmt_date(date_text: str) -> str:
        try:
            return datetime.strptime(date_text[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
        except Exception:
            return date_text
