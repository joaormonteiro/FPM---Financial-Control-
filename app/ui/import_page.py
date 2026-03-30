"""
Import page with CSV preview table and post-import summary.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.controllers.import_controller import ImportController


class ImportPage(QWidget):
    """CSV import page with a 10-row preview before committing."""

    data_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.controller = ImportController()
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(12)

        title = QLabel("Importar Extrato CSV")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        root.addWidget(title)

        # File picker row
        file_row = QHBoxLayout()
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("Selecione um arquivo CSV do Banco Inter")
        self.path_input.setReadOnly(True)
        self.select_button = QPushButton("Selecionar arquivo")
        self.preview_button = QPushButton("Pré-visualizar")
        file_row.addWidget(self.path_input, stretch=1)
        file_row.addWidget(self.select_button)
        file_row.addWidget(self.preview_button)
        root.addLayout(file_row)

        # Preview table (first 10 rows)
        preview_label = QLabel("Pré-visualização (primeiras 10 transações):")
        preview_label.setStyleSheet("font-weight: 600;")
        root.addWidget(preview_label)

        self.preview_table = QTableWidget()
        self.preview_table.setColumnCount(4)
        self.preview_table.setHorizontalHeaderLabels(
            ["Data", "Descrição", "Valor", "Categoria"]
        )
        self.preview_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.preview_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.preview_table.verticalHeader().setVisible(False)
        self.preview_table.setMaximumHeight(240)
        root.addWidget(self.preview_table)

        # Import row
        import_row = QHBoxLayout()
        self.import_button = QPushButton("Importar extrato")
        self.import_button.setStyleSheet("font-weight: 600; padding: 6px 20px;")
        import_row.addStretch(1)
        import_row.addWidget(self.import_button)
        root.addLayout(import_row)

        # Status
        self.status_label = QLabel("Nenhuma importação executada.")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)
        root.addStretch(1)

        # Connections
        self.select_button.clicked.connect(self._choose_file)
        self.preview_button.clicked.connect(self._preview)
        self.import_button.clicked.connect(self._import_csv)
        self.path_input.textChanged.connect(self._preview)

    def refresh(self) -> None:
        """No-op – page has no state that needs refreshing from the DB."""

    def _choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar extrato CSV",
            "",
            "CSV Files (*.csv)",
        )
        if path:
            self.path_input.setText(path)

    def _preview(self) -> None:
        csv_path = self.path_input.text().strip()
        if not csv_path:
            return
        rows = self.controller.preview_csv(csv_path, max_rows=10)
        self.preview_table.setRowCount(len(rows))
        for row_idx, tx in enumerate(rows):
            amount = float(tx.get("amount") or 0.0)
            amount_str = (
                f"R$ {abs(amount):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            )
            if amount < 0:
                amount_str = f"- {amount_str}"

            self.preview_table.setItem(row_idx, 0, QTableWidgetItem(str(tx.get("date") or "")))
            self.preview_table.setItem(row_idx, 1, QTableWidgetItem(str(tx.get("description") or "")))
            self.preview_table.setItem(row_idx, 2, QTableWidgetItem(amount_str))
            self.preview_table.setItem(row_idx, 3, QTableWidgetItem(str(tx.get("category") or "")))
        self.preview_table.resizeColumnsToContents()

    def _import_csv(self) -> None:
        csv_path = self.path_input.text().strip()
        ok, message, inserted, skipped = self.controller.import_csv(csv_path)

        self.status_label.setText(message)
        color = "#1b5e20" if ok else "#b71c1c"
        self.status_label.setStyleSheet(f"color: {color}; font-weight: 600;")

        if ok:
            self.data_changed.emit()
            # Clear preview after successful import
            self.preview_table.setRowCount(0)
