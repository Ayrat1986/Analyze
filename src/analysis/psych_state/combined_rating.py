# analysis/psych_state/combined_rating.py (v26.0)
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
    """Возвращает прямой CombinedR без скрытых вычитаний."""
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


def report_combined_rating():
    """Точка входа для 09_psych_state.py."""
    conn = _conn()
    try:
        with report_context("combined_rating") as w:
            w.w_separator(title="COMBINED RATING (GameR + SpeedR)")
            w.w("CombinedR = w1 × GameR + w2 × SpeedR")
            w.w("GameR = 3140 − ACPL×10 (калибровано для Bullet 1+0)")
            w.w("SpeedR = speed_b + speed_k × avg_time")
            w.w("§17: формулы — только из core/метрики.py")
            w.w()
            w.w_separator(title="КАЛИБРОВКА (90 дней)")
            coefs = _calibrate_combined(conn, days=90)
            if coefs:
                w.w(f" N = {coefs.get('n_samples', 0)} партий")
                w.w(f" w1 (GameR) = {coefs['w1']}, w2 (SpeedR) = {coefs['w2']}")
                w.w(f" SpeedR = {coefs['speed_b']:.0f} + ({coefs['speed_k']:.0f}) × avg_time")
                w.w(f" MAE (CombinedR vs Perf) = {coefs.get('train_mae', 0.0):.1f}")
            else:
                w.w(" ⚠️ Мало данных для калибровки, применены дефолты.")
            w.w()
    finally:
        conn.close()


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
        return "\n".join(lines)
    finally:
        if close_at_end:
            conn.close()


if __name__ == "__main__":
    report_combined_rating()
