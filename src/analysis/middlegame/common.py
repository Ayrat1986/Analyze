# ============================================================
# analysis/middlegame/common.py (v25.0)
# Убран REPORTS_DIR (использовался только positional_weaknesses).
# ============================================================
import sqlite3
import os
import json

import _common

DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")
PLAYER = _common.CONFIG.get("player", "")


def _conn():
    return sqlite3.connect(DB_FILE)


def get_base_filter() -> str:
    """Базовый фильтр для всех запросов миттельшпиля."""
    return "is_lag=0 AND is_cheater=0"


def safe_json_load(raw_data, default=None):
    """Безопасная загрузка JSON."""
    if not raw_data:
        return default if default is not None else []
    try:
        return json.loads(raw_data)
    except (json.JSONDecodeError, TypeError):
        return default if default is not None else []


def get_phase_bounds():
    """Границы фаз в ходах."""
    return {
        "opening": (1, 10),
        "middlegame": (11, 30),
        "endgame": (31, 999),
    }


def get_threshold(key, default):
    """Обертка для получения порогов из core.пороги."""
    from core.пороги import get as get_core_threshold
    return get_core_threshold(key, default)