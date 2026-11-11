# ============================================================
# analysis/psych_state/common.py
# ============================================================
import sqlite3
import os
import json
import _common
from _chess_utils import is_player_white as _is_player_white_util

DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")
REPORTS_DIR = str(_common.REPORTS_DIR)
PLAYER = _common.CONFIG.get("player", "")

def _conn():
    return sqlite3.connect(DB_FILE)

def _is_player_white(white: str) -> bool:
    return _is_player_white_util(white, PLAYER)

def _load_clocks_evals(clocks_raw, evals_raw):
    try:
        clocks = json.loads(clocks_raw) if clocks_raw else []
        evals = json.loads(evals_raw) if evals_raw else []
        return clocks, evals
    except Exception:
        return [], []

def get_report_path(name: str) -> str:
    return os.path.join(REPORTS_DIR, name)