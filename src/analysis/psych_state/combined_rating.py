# ============================================================
# analysis/psych_state/combined_rating.py (v25.4)
#!/usr/bin/env python3
"""
Скрипт исправления расчета GameR, SpeedR, CombinedR.
Устраняет системное завышение GameR (база 3140 вместо 3200) и 
убирает ломающие bias-костыли из combined_rating.py.
"""
import os
import ast
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent

METRIKI_FILE = ROOT / "src" / "core" / "метрики.py"
COMBINED_FILE = ROOT / "src" / "analysis" / "psych_state" / "combined_rating.py"


NEW_METRIKI_CONTENT = '''# src/core/метрики.py (v26.0)
"""
Единый источник правды для формул рейтинга и перформанса (PROJECT_RULES §17).
Все отчёты читают SpeedR/CombR/GameR/Perf ТОЛЬКО отсюда.

Калибровка для Bullet 1+0:
  GameR:  3140 - 10 * ACPL (при ACPL=60 дает 2540 - идеальное совпадение с Домом).
  SpeedR: speed_b + speed_k * avg_time (по умолчанию 3178 - 545 * t).
  CombR:  w1 * GameR + w2 * SpeedR (по умолчанию 0.75 / 0.25).
"""
import os
import json

# Константы GameR
GAMER_BASE = 3140.0
GAMER_SLOPE = 10.0

# Дефолтные коэффициенты (до первой калибровки)
_DEFAULT_SPEED_B = 3178.0
_DEFAULT_SPEED_K = -545.0
_DEFAULT_W1 = 0.75
_DEFAULT_W2 = 0.25

# Кэш чтения coefs.json (по mtime)
_COEFS_CACHE = {"mtime": 0.0, "coefs": None}


def _coefs_path():
    """Путь к data/combined_rating_coefs.json без жесткого импорта _common."""
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


def game_rating(acpl: float) -> float:
    """
    Потенциал точности по ACPL для 1+0.
    Формула: 3140 - acpl * 10, обрезка [1000, 3200].
    ACPL 40 → 2740 (пиковая форма)
    ACPL 60 → 2540 (базовый уровень 1+0)
    ACPL 80 → 2340 (спад/тильт)
    """
    if acpl is None or acpl <= 0:
        return 0.0
    return max(1000.0, min(3200.0, GAMER_BASE - float(acpl) * GAMER_SLOPE))


def speed_rating(avg_time: float, coefs=None) -> float:
    """
    Потенциал скорости по среднему времени на ход (1+0).
    coefs=None → читаем из data/combined_rating_coefs.json.
    Если файла нет → дефолт 3178 - 545 * avg_time.
    Обрезка [1000, 3200].
    """
    if avg_time is None or avg_time <= 0:
        return 0.0
    if coefs is None:
        coefs = _load_coefs()
    b = float(coefs.get("speed_b", _DEFAULT_SPEED_B))
    k = float(coefs.get("speed_k", _DEFAULT_SPEED_K))
    return max(1000.0, min(3200.0, b + k * float(avg_time)))


def combined_rating(game_r: float, speed_r: float, coefs=None) -> float:
    """
    CombinedR = w1 * GameR + w2 * SpeedR.
    Предиктивный композитный рейтинг качества и темпа.
    """
    if not game_r or not speed_r:
        return 0.0
    if coefs is None:
        coefs = _load_coefs()
    w1 = float(coefs.get("w1", _DEFAULT_W1))
    w2 = float(coefs.get("w2", _DEFAULT_W2))
    return max(1000.0, min(3200.0, w1 * float(game_r) + w2 * float(speed_r)))


def perf_rating(avg_opp: float, wins: int, draws: int, total: int) -> float:
    """
    Performance Rating (фактический результат турнирной выборки).
    avg_opp + (score - 0.5) * 800, где score = (wins + 0.5*draws) / total.
    """
    if not total or not avg_opp:
        return 0.0
    score = (wins + 0.5 * draws) / float(total)
    return avg_opp + (score - 0.5) * 800.0


def anchor(min_window: float, peak: float, avg_opp: float) -> float:
    """
    Якорь (дно, ниже которого не падаешь — диагностика).
    Среднее из трёх: минимум за окно, пик−150, ср.сопер×0.98.
    """
    if not min_window or not peak or not avg_opp:
        return 0.0
    return (min_window + (peak - 150.0) + avg_opp * 0.98) / 3.0


def home_zone(hist_peak: float, avg_my: float) -> float:
    """
    Домашняя зона (где рейтинг «живёт»).
    ((пик − 100) + средний + средний) / 3.
    """
    if not hist_peak or not avg_my:
        return 0.0
    return ((hist_peak - 100.0) + avg_my + avg_my) / 3.0
'''

NEW_COMBINED_CONTENT = '''# analysis/psych_state/combined_rating.py (v26.0)
"""
Расчет и калибровка CombinedR, SpeedR и GameR.
Единый расчет без искусственных bias-смещений.
"""
import json
import os
from datetime import datetime, timezone
import _common
from analysis.common import report_context, WINDOWS, window_label, window_cutoff_ts
from core.метрики import game_rating, speed_rating, combined_rating
from .common import _conn, _is_player_white
from .speed_rating import _compute_avg_time, _calibrate, _linear_fit

COEFS_PATH = str(_common.BASE_DIR / "data" / "combined_rating_coefs.json")


def save_coefs(coefs):
    os.makedirs(os.path.dirname(COEFS_PATH), exist_ok=True)
    with open(COEFS_PATH, "w", encoding="utf-8") as f:
        json.dump(coefs, f, ensure_ascii=False, indent=2)


def load_coefs():
    if not os.path.exists(COEFS_PATH):
        return {}
    try:
        with open(COEFS_PATH, "r", encoding="utf-8") as f:
            coefs = json.load(f)
        if not isinstance(coefs, dict) or "w1" not in coefs:
            return {}
        return coefs
    except Exception:
        return {}


def combined_rating_value(acpl, avg_time, coefs=None):
    """Возвращает прямой честный CombinedR без скрытых вычитаний."""
    if coefs is None:
        coefs = load_coefs()
    g_r = game_rating(acpl)
    s_r = speed_rating(avg_time, coefs)
    return combined_rating(g_r, s_r, coefs)


def _calibrate_combined(conn, days=90):
    """Калибрует параметры SpeedR (k, b) и веса CombinedR (w1, w2) по Perf."""
    speed_calib = _calibrate(conn, days)
    if not speed_calib:
        return None
    k, b = _linear_fit(speed_calib)
    if k is None or abs(k) < 50:
        k = -545.0
        b = 3178.0

    cutoff = window_cutoff_ts(days)
    cur = conn.cursor()
    cur.execute("""
        SELECT clocks, eval_history, white, my_rating, opp_rating, won, draw, acpl, time_control, end_time
        FROM games
        WHERE is_lag=0 AND is_cheater=0 AND end_time >= ?
          AND my_rating > 0 AND acpl > 0
          AND clocks IS NOT NULL AND clocks != '[]'
          AND eval_history IS NOT NULL AND eval_history != '[]'
        ORDER BY end_time
    """, (cutoff,))

    samples = []
    for clocks_raw, evals_raw, white, my_rating, opp_rating, won, draw, acpl, tc, end_time in cur.fetchall():
        player_is_white = _is_player_white(white)
        t = _compute_avg_time(clocks_raw, evals_raw, player_is_white, tc)
        if not t or not t.get("avg"):
            continue
        avg_time = t["avg"]
        g_r = game_rating(acpl)
        s_r = max(1000.0, min(3200.0, b + k * avg_time))
        # Perf для одной партии (score: 1.0 победа, 0.5 ничья, 0.0 поражение)
        score = 1.0 if won else (0.5 if draw else 0.0)
        perf_single = opp_rating + (score - 0.5) * 800.0
        samples.append((g_r, s_r, perf_single))

    if len(samples) < 30:
        return {
            "speed_k": k, "speed_b": b,
            "w1": 0.75, "w2": 0.25,
            "calibrated_at": datetime.now(timezone.utc).isoformat(),
            "n_samples": len(samples)
        }

    # Подбор весов w1, w2 с шагом 0.05 для минимизации MAE к фактическому Perf
    best_w1 = 0.75
    best_mae = float("inf")
    for step in range(10, 19):  # w1 от 0.50 до 0.90
        w1_cand = round(step * 0.05, 2)
        w2_cand = round(1.0 - w1_cand, 2)
        mae = sum(abs((w1_cand * g + w2_cand * s) - p) for g, s, p in samples) / len(samples)
        if mae < best_mae:
            best_mae = mae
            best_w1 = w1_cand

    coefs = {
        "speed_k": round(k, 1),
        "speed_b": round(b, 1),
        "w1": best_w1,
        "w2": round(1.0 - best_w1, 2),
        "calibrated_at": datetime.now(timezone.utc).isoformat(),
        "n_samples": len(samples),
        "train_mae": round(best_mae, 1)
    }
    save_coefs(coefs)
    return coefs


def run(conn=None):
    close_at_end = False
    if conn is None:
        conn = _conn()
        close_at_end = True

    try:
        coefs = _calibrate_combined(conn, days=90)
        if not coefs:
            coefs = load_coefs()

        lines = [
            "# Combined Rating Analysis (v26.0)",
            f"# Сформировано: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            f"# Параметры: SpeedR = {coefs.get('speed_b', 3178)} + ({coefs.get('speed_k', -545)}) * avg_t",
            f"# Веса: CombR = {coefs.get('w1', 0.75)} * GameR + {coefs.get('w2', 0.25)} * SpeedR",
            ""
        ]
        return "\\n".join(lines)
    finally:
        if close_at_end:
            conn.close()


if __name__ == "__main__":
    report = run()
    print(report)
'''


def apply_patch():
    for path, content in [(METRIKI_FILE, NEW_METRIKI_CONTENT), (COMBINED_FILE, NEW_COMBINED_CONTENT)]:
        if not path.exists():
            print(f"❌ Файл не найден: {path}")
            continue

        # Проверка синтаксиса перед записью
        ast.parse(content, filename=str(path))

        # Создание резервной копии
        backup = path.with_suffix(".py.v25_bak")
        shutil.copyfile(path, backup)
        print(f"📦 Создан бэкап: {backup.name}")

        # Запись
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✅ Успешно обновлен: {path.name}")


if __name__ == "__main__":
    apply_patch()
