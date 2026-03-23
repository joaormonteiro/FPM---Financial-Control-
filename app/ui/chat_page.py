from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.controllers.chat_controller_adapter import ChatControllerAdapter


class ChatPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.controller = ChatControllerAdapter()
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        title = QLabel("Chat Financeiro")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        root.addWidget(title)

        self.chat_output = QTextEdit()
        self.chat_output.setReadOnly(True)
        self.chat_output.setPlaceholderText("Pergunte sobre seus gastos, categorias e recorrências.")
        root.addWidget(self.chat_output, stretch=1)

        input_row = QHBoxLayout()
        self.question_input = QLineEdit()
        self.question_input.setPlaceholderText("Digite sua pergunta financeira")
        self.ask_button = QPushButton("Perguntar")
        input_row.addWidget(self.question_input, stretch=1)
        input_row.addWidget(self.ask_button)
        root.addLayout(input_row)

        self.ask_button.clicked.connect(self._ask_question)
        self.question_input.returnPressed.connect(self._ask_question)

    def refresh(self) -> None:
        return

    def _ask_question(self) -> None:
        question = self.question_input.text().strip()
        if not question:
            return

        answer = self.controller.ask(question)
        stamp = datetime.now().strftime("%d/%m/%Y %H:%M")
        self.chat_output.append(f"[{stamp}] Voce: {question}")
        self.chat_output.append(f"[{stamp}] Assistente: {answer}")
        self.chat_output.append("")
        self.question_input.clear()
