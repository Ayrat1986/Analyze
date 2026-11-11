# src/core/пороги.py
"""
Загрузчик порогов из data/пороги.json.
Fallback на DEFAULTS, если файла нет или он битый.
"""
import json
import os

import _common

POROGI_FILE = str(_common.BASE_DIR / "data" / "пороги.json")

DEFAULTS = {
    "blunder_threshold_cp": 150,
    "acpl_mid_red": 75,
    "min_games_for_opening": 10,
    "min_n_for_hours": 20,
    "session_gap_minutes": 30,
    "true_berserk_min_moves": 15,
    "true_berserk_min_length": 60,
    "position_type_chaotic_cm": 15,
    "position_type_positional_cm": 4,
    "position_type_positional_min_length": 60,
    "position_type_tactical_loss_cp": 250,
    "exhaustion_acpl_drop": 5,
    "checkin_lookback_days": 90,
    "checkin_min_pairs": 5,
}


def load():
    if os.path.exists(POROGI_FILE):
        try:
            with open(POROGI_FILE, "r", encoding="utf-8") as f:
                user = json.load(f)
            result = dict(DEFAULTS)
            result.update(user)
            return result
        except Exception as e:
            print(f"⚠️ Пороги не загружены ({e}), используем defaults")
            return dict(DEFAULTS)
    return dict(DEFAULTS)


POROGI = load()


def get(key, default=None):
    """Возвращает порог по ключу. Fallback: DEFAULTS → default."""
    return POROGI.get(key, DEFAULTS.get(key, default))