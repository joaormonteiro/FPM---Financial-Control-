from __future__ import annotations

from ai.chat_controller import handle_user_question


class ChatControllerAdapter:
    def ask(self, question: str) -> str:
        user_question = (question or "").strip()
        if not user_question:
            return "Digite uma pergunta."
        return handle_user_question(user_question)
