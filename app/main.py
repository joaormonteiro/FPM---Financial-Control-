from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.ui.main_window import MainWindow
from db import init_db


def _runtime_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return ROOT_DIR


def _bundle_dir() -> Path:
    maybe_meipass = getattr(sys, "_MEIPASS", None)
    if maybe_meipass:
        return Path(maybe_meipass)
    return ROOT_DIR


def _ensure_local_db(runtime_dir: Path, bundle_dir: Path) -> None:
    data_dir = runtime_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    target_db = data_dir / "finance.db"
    if target_db.exists():
        return

    candidates = [
        bundle_dir / "data" / "finance.db",
        ROOT_DIR / "data" / "finance.db",
    ]
    for source_db in candidates:
        if source_db.exists():
            shutil.copy2(source_db, target_db)
            return


def _prepare_runtime_environment() -> None:
    runtime_dir = _runtime_dir()
    bundle_dir = _bundle_dir()
    _ensure_local_db(runtime_dir, bundle_dir)
    os.chdir(runtime_dir)


def main() -> None:
    _prepare_runtime_environment()
    init_db()

    app = QApplication(sys.argv)
    app.setApplicationName("FinancialControl")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
