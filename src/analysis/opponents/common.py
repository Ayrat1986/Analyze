# ============================================================
# analysis/opponents/common.py — общие утилиты для отчётов
# ============================================================
import sqlite3
import os
import csv
from importlib import import_module
import _common

DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")
REPORTS_DIR = str(_common.REPORTS_DIR)
AI_LATEST = os.path.join(REPORTS_DIR, "ai_export", "latest")
PLAYER = _common.CONFIG.get("player", "")


def _conn():
    return sqlite3.connect(DB_FILE)


def _style_csv():
    """Читает opponent_style.csv из ai_export/latest."""
    path = os.path.join(AI_LATEST, "opponent_style.csv")
    if not os.path.exists(path):
        return None
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                rows.append({
                    "style": r.get("opponent_style", "?"),
                    "games": int(r.get("games", 0)),
                    "wins": int(r.get("wins", 0)),
                    "win_rate": float(str(r.get("win_rate", "0")).replace("%", "")),
                    "my_acpl": float(r.get("my_avg_acpl", 0) or 0),
                })
            except (ValueError, TypeError):
                continue
    return rows