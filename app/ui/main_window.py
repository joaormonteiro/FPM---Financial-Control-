from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QWidget,
)

from app.ui.dashboard_page import DashboardPage
from app.ui.import_page import ImportPage
from app.ui.rules_page import RulesPage
from app.ui.transactions_page import TransactionsPage


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("FinancialControl")
        self.resize(1320, 820)

        root = QWidget()
        self.setCentralWidget(root)

        layout = QHBoxLayout(root)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(220)
        self.sidebar.setAlternatingRowColors(True)
        self.sidebar.setSelectionMode(QListWidget.SingleSelection)
        self.sidebar.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.stack = QStackedWidget()

        self.dashboard_page = DashboardPage()
        self.import_page = ImportPage()
        self.transactions_page = TransactionsPage()
        self.rules_page = RulesPage()

        self._pages = [
            ("Dashboard", self.dashboard_page),
            ("Importar Extrato", self.import_page),
            ("Transações", self.transactions_page),
            ("Regras", self.rules_page),
        ]

        for title, page in self._pages:
            self.sidebar.addItem(QListWidgetItem(title))
            self.stack.addWidget(page)

        layout.addWidget(self.sidebar)
        layout.addWidget(self.stack, stretch=1)

        self.sidebar.currentRowChanged.connect(self._on_sidebar_changed)
        self.import_page.data_changed.connect(self._refresh_data_pages)
        self.transactions_page.data_changed.connect(self._refresh_data_pages)

        self.sidebar.setCurrentRow(0)

    def _on_sidebar_changed(self, row: int) -> None:
        if row < 0:
            return

        self.stack.setCurrentIndex(row)
        current_widget = self.stack.currentWidget()
        if hasattr(current_widget, "refresh"):
            current_widget.refresh()

    def _refresh_data_pages(self) -> None:
        self.dashboard_page.refresh()
        self.transactions_page.refresh()
