# ============================================================
# core/метрики.py (v27.2)
# Единый источник формул (PROJECT_RULES §17).
# 4-факторная модель: Мышление (GameR) + Интуиция (SpeedR)
# + Ощущения (AggrR) + Чувства (StateR).
# ============================================================
import json
import os

GAMER_BASE = 3110.0
GAMER_SLOPE = 10.0

_DEFAULT_SPEED_B = 3178.0
_DEFAULT_SPEED_K = -545.0
_DEFAULT_W1 = 0.75
_DEFAULT_W2 = 0.25

_COEFS_CACHE = {"mtime": 0.0, "coefs": None}


def _coefs_path() -> str:
    try:
        import _common
        return str(_common.BASE_DIR / "data" / "combined_rating_coefs.json")
    except Exception:
        return ""


def _load_coefs() -> dict:
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


def game_rating(acpl: float) -> float:
    """Мышление (Материя). Точность ходов."""
    if acpl is None or acpl <= 0:
        return 0.0
    return max(1000.0, min(3200.0, GAMER_BASE - float(acpl) * GAMER_SLOPE))


def speed_rating(avg_time: float, coefs: dict = None) -> float:
    """Интуиция (Время). Скорость принятия решений."""
    if avg_time is None or avg_time <= 0:
        return 0.0
    if coefs is None:
        coefs = _load_coefs()
    b = float(coefs.get("speed_b", _DEFAULT_SPEED_B))
    k = float(coefs.get("speed_k", _DEFAULT_SPEED_K))
    return max(1000.0, min(3200.0, b + k * float(avg_time)))


def aggression_rating(aggr_score: float) -> float:
    """Ощущения (Пространство). Индекс агрессии (база 7.8 -> 2537)."""
    if aggr_score is None or aggr_score <= 0:
        return 0.0
    return max(1000.0, min(3200.0, 2537.0 + (float(aggr_score) - 7.8) * 60.0))


def state_rating(conv_pct: float, cascade_pct: float) -> float:
    """Чувства (Энергия). Конверсия +3.0 (база 80%) и анти-тильт (база 50%)."""
    if conv_pct is None or cascade_pct is None:
        return 0.0
    val = 2537.0 + (float(conv_pct) - 80.0) * 8.0 - (float(cascade_pct) - 50.0) * 2.0
    return max(1000.0, min(3200.0, val))


def combined_rating(game_r: float, speed_r: float, coefs: dict = None) -> float:
    """Базовая 2-факторная модель (обратная совместимость)."""
    if not game_r or not speed_r:
        return 0.0
    if coefs is None:
        coefs = _load_coefs()
    w1 = float(coefs.get("w1", _DEFAULT_W1))
    w2 = float(coefs.get("w2", _DEFAULT_W2))
    return w1 * float(game_r) + w2 * float(speed_r)


def combined_rating_v2(game_r: float, speed_r: float, aggr_r: float, state_r: float) -> float:
    """4-факторная модель: Мышление + Интуиция + Ощущения + Чувства."""
    if not all([game_r, speed_r, aggr_r, state_r]):
        return 0.0
    return (
        0.40 * float(game_r)
        + 0.20 * float(speed_r)
        + 0.20 * float(aggr_r)
        + 0.20 * float(state_r)
    )


def perf_rating(avg_opp: float, wins: int, draws: int, total: int) -> float:
    if not total or not avg_opp:
        return 0.0
    score = (wins + 0.5 * draws) / total
    return float(avg_opp) + (score - 0.5) * 800.0


def anchor(min_window: float, peak: float, avg_opp: float) -> float:
    if not min_window or not peak or not avg_opp:
        return 0.0
    return (float(min_window) + (float(peak) - 150.0) + float(avg_opp) * 0.98) / 3.0


def home_zone(hist_peak: float, avg_my: float) -> float:
    if not hist_peak or not avg_my:
        return 0.0
    return ((float(hist_peak) - 100.0) + float(avg_my) + float(avg_my)) / 3.0