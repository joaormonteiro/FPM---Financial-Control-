"""
FinancialControl – single application entry point.

Launches the PySide6 GUI.  The previous CLI import functionality is
available via --import <csv_path> for headless/scripted use.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def _runtime_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return ROOT_DIR


def _bundle_dir() -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    return Path(meipass) if meipass else ROOT_DIR


def _ensure_data_dir() -> None:
    runtime = _runtime_dir()
    bundle = _bundle_dir()

    data_dir = runtime / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    target_db = data_dir / "finance.db"
    if not target_db.exists():
        for candidate in [
            bundle / "data" / "finance.db",
            ROOT_DIR / "data" / "finance.db",
        ]:
            if candidate.exists():
                shutil.copy2(candidate, target_db)
                break

    os.chdir(runtime)


def _run_gui() -> None:
    from PySide6.QtWidgets import QApplication

    from app.ui.main_window import MainWindow
    from core.db import init_db

    _ensure_data_dir()
    init_db()

    app = QApplication(sys.argv)
    app.setApplicationName("FinancialControl")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


def _run_cli_import(csv_path: str) -> None:
    from ai.recurrence_engine import detect_recurring_transactions
    from core.db import connect, init_db, insert_transaction
    from importers.inter_csv import parse_inter_csv

    _ensure_data_dir()
    init_db()

    transactions = parse_inter_csv(csv_path)
    inserted = 0
    for t in transactions:
        if insert_transaction(t):
            inserted += 1

    conn = connect()
    try:
        detect_recurring_transactions(conn)
    finally:
        conn.close()

    skipped = len(transactions) - inserted
    print(
        f"Importação concluída: {inserted} transações adicionadas, "
        f"{skipped} ignoradas (duplicadas)."
    )


def main() -> None:
    args = sys.argv[1:]

    if args and args[0] == "--import" and len(args) >= 2:
        _run_cli_import(args[1])
        return

    _run_gui()


if __name__ == "__main__":
    main()
