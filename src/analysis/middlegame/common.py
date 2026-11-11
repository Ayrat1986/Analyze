# ============================================================
# analysis/middlegame/common.py — общие утилиты для миттельшпиля
# ============================================================
import sqlite3
import os
import json
from datetime import datetime

import _common

DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")
REPORTS_DIR = str(_common.REPORTS_DIR)
PLAYER = _common.CONFIG.get("player", "")


def _conn():
    return sqlite3.connect(DB_FILE)


def write_report(name: str, lines: list[str]):
    """Записывает отчет в файл и дублирует вывод в консоль."""
    path = os.path.join(REPORTS_DIR, f"{name}.txt")
    with open(path, "w", encoding="utf-8") as f:
        for line in lines:
            print(line)
            f.write(line + "\n")
    print(f"\n✅ {path}")
    return path


def get_base_filter() -> str:
    """Базовый фильтр для всех запросов миттельшпиля (без лагов, читеров и т.д.)"""
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