# ============================================================
# analysis/psych_focus/common.py
# ============================================================
import sqlite3
import os
import _common

DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")
REPORTS_DIR = str(_common.REPORTS_DIR)
PLAYER = _common.CONFIG.get("player", "")

def _conn():
    return sqlite3.connect(DB_FILE)

def get_report_path(name: str) -> str:
    return os.path.join(REPORTS_DIR, name)