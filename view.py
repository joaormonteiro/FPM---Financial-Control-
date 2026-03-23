import sqlite3

from core.settings import DB_PATH


def main(limit: int = 20) -> None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT date, description, amount, category, payer
        FROM transactions
        ORDER BY date DESC
        LIMIT ?
        """,
        (int(limit),),
    )

    for row in cursor.fetchall():
        print(row)

    conn.close()


if __name__ == "__main__":
    main()
