import sqlite3

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

SIMILARITY_THRESHOLD = 0.82


class HistoryBasedClassifier:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.vectorizer: TfidfVectorizer | None = None
        self.matrix = None
        self.labels: list[tuple[str, str | None]] = []
        self._built = False

    def build_index(self) -> None:
        if self._built:
            return

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            """
            SELECT cleaned_description, category, payer
            FROM transactions
            WHERE classification_source IN ('manual', 'rule')
              AND category IS NOT NULL
              AND cleaned_description IS NOT NULL
              AND TRIM(cleaned_description) <> ''
              AND confidence >= 0.7
            """
        )
        rows = c.fetchall()
        conn.close()

        if not rows:
            self.vectorizer = None
            self.matrix = None
            self.labels = []
            self._built = True
            return

        descriptions = [str(r[0]).strip().lower() for r in rows]
        self.labels = [(str(r[1]), r[2]) for r in rows]

        self.vectorizer = TfidfVectorizer()
        self.matrix = self.vectorizer.fit_transform(descriptions)
        self._built = True

    def predict(self, description: str) -> tuple | None:
        self.build_index()

        if not self.vectorizer or self.matrix is None:
            return None

        query = (description or "").strip().lower()
        if not query:
            return None

        q_vec = self.vectorizer.transform([query])
        sims = cosine_similarity(q_vec, self.matrix)[0]

        if sims.size == 0:
            return None

        best_idx = int(np.argmax(sims))
        best_score = float(sims[best_idx])

        if best_score < SIMILARITY_THRESHOLD:
            return None

        category, payer = self.labels[best_idx]
        return category, payer, best_score
