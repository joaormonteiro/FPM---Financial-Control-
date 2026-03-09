from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.controllers.import_controller import ImportController


class ImportPage(QWidget):
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

        line = QHBoxLayout()
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("Selecione um arquivo CSV do Banco Inter")
        self.path_input.setReadOnly(True)
        self.select_button = QPushButton("Selecionar arquivo")
        self.import_button = QPushButton("Importar extrato")
        line.addWidget(self.path_input, stretch=1)
        line.addWidget(self.select_button)
        line.addWidget(self.import_button)
        root.addLayout(line)

        self.status_label = QLabel("Nenhuma importacao executada.")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)
        root.addStretch(1)

        self.select_button.clicked.connect(self._choose_file)
        self.import_button.clicked.connect(self._import_csv)

    def refresh(self) -> None:
        return

    def _choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar extrato CSV",
            "",
            "CSV Files (*.csv)",
        )
        if path:
            self.path_input.setText(path)

    def _import_csv(self) -> None:
        csv_path = self.path_input.text().strip()
        ok, message, _ = self.controller.import_csv(csv_path)

        self.status_label.setText(message)
        color = "#136f1f" if ok else "#8a1f11"
        self.status_label.setStyleSheet(f"color: {color}; font-weight: 600;")

        if ok:
            self.data_changed.emit()
