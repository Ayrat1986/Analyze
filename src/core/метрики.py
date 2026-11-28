# ============================================================
# core/метрики.py (v27.6)
# Единый источник формул (PROJECT_RULES §17).
# Основной CombR — 4-факторная модель:
#   Точность/Мышление (GameR) + Скорость/Интуиция (SpeedR)
#   + Агрессия/Ощущения (AggrR) + Тильт/Чувства (StateR).
# Калибровка: Δ = CombR − Дом ≈ 0 на окнах 90 и 365 дней (база 2538).
# ============================================================
import json
import os

GAMER_BASE = 3110.0
GAMER_SLOPE = 10.0

CALIBRATED_HOME_BASE = 2538.0
AGGR_BASELINE = 7.4
CONV_BASELINE = 66.0
CASCADE_BASELINE = 71.5

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
    """Точность/Мышление (Материя)."""
    if acpl is None or acpl <= 0:
        return 0.0
    return max(1000.0, min(3200.0, GAMER_BASE - float(acpl) * GAMER_SLOPE))


def speed_rating(avg_time: float, coefs: dict = None) -> float:
    """Скорость/Интуиция (Время)."""
    if avg_time is None or avg_time <= 0:
        return 0.0
    if coefs is None:
        coefs = _load_coefs()
    b = float(coefs.get("speed_b", _DEFAULT_SPEED_B))
    k = float(coefs.get("speed_k", _DEFAULT_SPEED_K))
    return max(1000.0, min(3200.0, b + k * float(avg_time)))


def aggression_rating(aggr_score: float) -> float:
    """Агрессия/Ощущения (Пространство). База 7.4 -> 2538."""
    if aggr_score is None or aggr_score <= 0:
        return 0.0
    val = CALIBRATED_HOME_BASE + (float(aggr_score) - AGGR_BASELINE) * 60.0
    return max(1000.0, min(3200.0, val))


def state_rating(conv_pct: float, cascade_pct: float) -> float:
    """Тильт/Чувства (Энергия). Конверсия +3.0 (база 66%) и каскадный тильт (база 71.5%)."""
    if conv_pct is None or cascade_pct is None:
        return 0.0
    val = (
        CALIBRATED_HOME_BASE
        + (float(conv_pct) - CONV_BASELINE) * 6.0
        - (float(cascade_pct) - CASCADE_BASELINE) * 2.5
    )
    return max(1000.0, min(3200.0, val))


def combined_rating(
    game_r: float,
    speed_r: float,
    aggr_r: float = None,
    state_r: float = None,
    coefs: dict = None,
) -> float:
    """
    Основной CombR (4-факторная модель при передаче aggr_r и state_r;
    2-факторный фолбэк для обратной совместимости со старыми модулями).
    """
    if isinstance(aggr_r, dict):
        coefs = aggr_r
        aggr_r = None

    if aggr_r is not None and state_r is not None:
        if not all([game_r, speed_r, aggr_r, state_r]):
            return 0.0
        return (
            0.40 * float(game_r)
            + 0.20 * float(speed_r)
            + 0.20 * float(aggr_r)
            + 0.20 * float(state_r)
        )

    if not game_r or not speed_r:
        return 0.0
    if coefs is None:
        coefs = _load_coefs()
    w1 = float(coefs.get("w1", _DEFAULT_W1))
    w2 = float(coefs.get("w2", _DEFAULT_W2))
    return w1 * float(game_r) + w2 * float(speed_r)


def combined_rating_v2(game_r: float, speed_r: float, aggr_r: float, state_r: float) -> float:
    """Алиас обратной совместимости на основной 4-факторный combined_rating."""
    return combined_rating(game_r, speed_r, aggr_r, state_r)


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