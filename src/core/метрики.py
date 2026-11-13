# src/core/метрики.py (v25.0)
"""
Единый источник правды для формул (PROJECT_RULES §17).
Все отчёты читают SpeedR/CombR/GameR/Perf ТОЛЬКО отсюда.

Дефолт при отсутствии data/combined_rating_coefs.json:
  SpeedR = 3178 - 545 * avg_time
  CombR  = 0.7 * GameR + 0.3 * SpeedR

После калибровки (combined_rating.py пишет coefs.json):
  SpeedR = speed_b + speed_k * avg_time  (обычно 2547 - 2 * t)
  CombR  = w1 * GameR + w2 * SpeedR      (обычно 0.7 / 0.3)
"""
import os
import json

# Дефолтные коэффициенты (до первой калибровки)
_DEFAULT_SPEED_B = 3178.0
_DEFAULT_SPEED_K = -545.0
_DEFAULT_W1 = 0.7
_DEFAULT_W2 = 0.3

# Кэш чтения coefs.json (по mtime)
_COEFS_CACHE = {"mtime": 0.0, "coefs": None}


def _coefs_path():
    """Путь к data/combined_rating_coefs.json без жёсткого импорта _common."""
    try:
        import _common
        return str(_common.BASE_DIR / "data" / "combined_rating_coefs.json")
    except Exception:
        return ""


def _load_coefs() -> dict:
    """
    Читает coefs.json. Кэш инвалидируется по mtime.
    Пустой dict, если файла нет — тогда используются дефолты.
    """
    global _COEFS_CACHE
    path = _coefs_path()
    if not path or not os.path.exists(path):
        return {}
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return {}
    if _COEFS_CACHE["mtime"] == mtime and _COEFS_CACHE["coefs"] is not None:
        return _COEFS_CACHE["coefs"]
    try:
        with open(path, "r", encoding="utf-8") as f:
            coefs = json.load(f)
        if not isinstance(coefs, dict):
            coefs = {}
        _COEFS_CACHE["mtime"] = mtime
        _COEFS_CACHE["coefs"] = coefs
        return coefs
    except Exception:
        return {}


def game_rating(acpl) -> float:
    """
    Потенциал точности по ACPL.
    Формула: 3200 - acpl * 10, обрезка [1000, 3200].
    40 ACPL → 2800, 60 ACPL → 2600.
    """
    if not acpl or acpl <= 0:
        return 0.0
    return max(1000.0, min(3200.0, 3200.0 - acpl * 10.0))


def speed_rating(avg_time, coefs=None) -> float:
    """
    Потенциал скорости по среднему времени на ход (1+0).
    coefs=None → читаем из data/combined_rating_coefs.json.
    Если файла нет → дефолт 3178 - 545 * avg_time.
    Обрезка [1000, 3200].
    """
    if not avg_time or avg_time <= 0:
        return 0.0
    if coefs is None:
        coefs = _load_coefs()
    b = float(coefs.get("speed_b", _DEFAULT_SPEED_B))
    k = float(coefs.get("speed_k", _DEFAULT_SPEED_K))
    return max(1000.0, min(3200.0, b + k * avg_time))


def combined_rating(game_r, speed_r, coefs=None) -> float:
    """
    CombinedR = w1 * GameR + w2 * SpeedR.
    coefs=None → читаем из data/combined_rating_coefs.json.
    Если файла нет → w1=0.7, w2=0.3.
    """
    if not game_r or not speed_r:
        return 0.0
    if coefs is None:
        coefs = _load_coefs()
    w1 = float(coefs.get("w1", _DEFAULT_W1))
    w2 = float(coefs.get("w2", _DEFAULT_W2))
    return w1 * game_r + w2 * speed_r


def perf_rating(avg_opp, wins, draws, total) -> float:
    """
    Performance Rating (результат).
    avg_opp + (score - 0.5) * 800, где score = (wins + 0.5*draws) / total.
    """
    if not total or not avg_opp:
        return 0.0
    score = (wins + 0.5 * draws) / total
    return avg_opp + (score - 0.5) * 800.0


def anchor(min_window, peak, avg_opp) -> float:
    """
    Якорь (дно, ниже которого не падаешь — диагностика).
    Среднее из трёх: минимум за окно, пик−150, ср.сопер×0.98.
    """
    if not min_window or not peak or not avg_opp:
        return 0.0
    return (min_window + (peak - 150) + avg_opp * 0.98) / 3.0


def home_zone(hist_peak, avg_my) -> float:
    """
    Домашняя зона (где рейтинг «живёт»).
    ((пик − 100) + средний + средний) / 3.
    Используется в 13 (build_sql_summary).
    """
    if not hist_peak or not avg_my:
        return 0.0
    return ((hist_peak - 100) + avg_my + avg_my) / 3.0