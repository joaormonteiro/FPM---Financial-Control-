from pathlib import Path
import sqlite3

ROOT_DIR = Path(__file__).resolve().parents[1]
DB_PATH = ROOT_DIR / "data" / "finance.db"


def has_column(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    altered = False
    if not has_column(cursor, "transactions", "description_ai"):
        cursor.execute("ALTER TABLE transactions ADD COLUMN description_ai TEXT")
        altered = True

    if not has_column(cursor, "transactions", "category_ai"):
        cursor.execute("ALTER TABLE transactions ADD COLUMN category_ai TEXT")
        altered = True

    if not has_column(cursor, "transactions", "ai_confidence"):
        cursor.execute("ALTER TABLE transactions ADD COLUMN ai_confidence REAL")
        altered = True

    if not has_column(cursor, "transactions", "ai_updated_at"):
        cursor.execute("ALTER TABLE transactions ADD COLUMN ai_updated_at TEXT")
        altered = True

    conn.commit()
    conn.close()

    if altered:
        print("Migracao aplicada: colunas IA adicionadas.")
    else:
        print("Migracao nao necessaria: colunas ja existem.")


if __name__ == "__main__":
    main()
