# ============================================================
# analysis/psych_state/combined_rating.py (v26.0)
# FIX v26.0:
#   - §17: прямой расчет через core/метрики.py без bias-костылей.
#   - Полный отчет по окнам (1/2/7/30/90/365) и 'Сладкий темп'.
#   - Безопасная калибровка весов (w1, w2) с train/test валидацией.
#   - Совместимость с веб-дашбордом и 09_psych_state.py.
# ============================================================
import json
import statistics
import os
from datetime import datetime, timezone
import _common
from analysis.common import report_context, WINDOWS, window_label, window_cutoff_ts
from core.метрики import game_rating, speed_rating, combined_rating
from core.time_control import is_primary
from .common import _conn, _is_player_white
from .speed_rating import _compute_avg_time, _calibrate, _linear_fit

COEFS_PATH = str(_common.BASE_DIR / "data" / "combined_rating_coefs.json")


def save_coefs(coefs: dict) -> None:
    os.makedirs(os.path.dirname(COEFS_PATH), exist_ok=True)
    with open(COEFS_PATH, "w", encoding="utf-8") as f:
        json.dump(coefs, f, ensure_ascii=False, indent=2)


def load_coefs() -> dict:
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


def combined_rating_value(acpl: float, avg_time: float, coefs: dict = None) -> float:
    """Прямой расчет CombinedR через функции ядра."""
    g_r = game_rating(acpl)
    s_r = speed_rating(avg_time, coefs)
    return combined_rating(g_r, s_r, coefs)


def _calibrate_combined(conn, days: int = 90):
    """Калибровка speed_b, speed_k и весов w1/w2 по фактическому перформансу."""
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
        if not is_primary(tc):
            continue
        player_is_white = _is_player_white(white)
        t = _compute_avg_time(clocks_raw, evals_raw, player_is_white, tc)
        if not t or t.get("avg") is None:
            continue
        avg_time = t["avg"]
        g_r = game_rating(acpl)
        s_r = max(1000.0, min(3200.0, b + k * avg_time))
        score = 1.0 if won else (0.5 if draw else 0.0)
        perf = opp_rating + (score - 0.5) * 800.0
        samples.append({
            "game_r": g_r,
            "speed_r": s_r,
            "perf": perf,
            "end_time": end_time
        })

    if len(samples) < 30:
        return {
            "speed_k": round(k, 1),
            "speed_b": round(b, 1),
            "w1": 0.75,
            "w2": 0.25,
            "mae": 0.0,
            "game_r_mae": 0.0,
            "speed_r_mae": 0.0,
            "n": len(samples),
            "n_train": len(samples),
            "n_test": 0,
            "calibrated_at": datetime.now(timezone.utc).isoformat(),
            "is_default": True
        }

    samples.sort(key=lambda s: s["end_time"])
    split_idx = int(len(samples) * 0.7)
    train = samples[:split_idx] if split_idx >= 20 else samples
    test = samples[split_idx:] if split_idx >= 20 else samples

    best_w1 = 0.75
    best_mae_train = float("inf")
    for w1_int in range(10, 19):  # w1 от 0.50 до 0.90
        w1 = round(w1_int * 0.05, 2)
        w2 = round(1.0 - w1, 2)
        mae = sum(abs((w1 * s["game_r"] + w2 * s["speed_r"]) - s["perf"]) for s in train) / len(train)
        if mae < best_mae_train:
            best_mae_train = mae
            best_w1 = w1

    best_w2 = round(1.0 - best_w1, 2)
    mae_test_comb = sum(abs((best_w1 * s["game_r"] + best_w2 * s["speed_r"]) - s["perf"]) for s in test) / len(test)
    mae_test_game = statistics.mean(abs(s["game_r"] - s["perf"]) for s in test)
    mae_test_speed = statistics.mean(abs(s["speed_r"] - s["perf"]) for s in test)

    coefs = {
        "speed_k": round(k, 1),
        "speed_b": round(b, 1),
        "w1": best_w1,
        "w2": best_w2,
        "mae": round(mae_test_comb, 1),
        "game_r_mae": round(mae_test_game, 1),
        "speed_r_mae": round(mae_test_speed, 1),
        "n": len(samples),
        "n_train": len(train),
        "n_test": len(test),
        "calibrated_at": datetime.now(timezone.utc).isoformat(),
        "is_default": False
    }
    save_coefs(coefs)
    return coefs


def report_combined_rating():
    """Формирование полного отчета по Combined Rating."""
    conn = _conn()
    try:
        with report_context("combined_rating") as w:
            w.w_separator(title="COMBINED RATING (GameR + SpeedR)")
            w.w("CombinedR = w1 × GameR + w2 × SpeedR")
            w.w("GameR = 3140 − ACPL×10 (калибровано для Bullet 1+0)")
            w.w("SpeedR = speed_b + speed_k × avg_time")
            w.w("§17: формулы — только из core/метрики.py")
            w.w("⚠️ Только 1+0 (bullet). База времени = 60 сек.")
            w.w()
            w.w_separator(title="КАЛИБРОВКА (90 дней)")
            coefs = _calibrate_combined(conn, days=90)
            if coefs and not coefs.get("is_default"):
                w.w(f" N = {coefs['n']} партий (train={coefs['n_train']}, test={coefs['n_test']})")
                w.w(f" w1 (GameR) = {coefs['w1']}, w2 (SpeedR) = {coefs['w2']}")
                w.w(f" SpeedR = {coefs['speed_b']:.0f} + ({coefs['speed_k']:.0f}) × avg_time")
                w.w()
                w.w(f" MAE (CombinedR vs Perf, test) = {coefs['mae']:.1f}")
                w.w(f" MAE (GameR vs Perf, test)    = {coefs['game_r_mae']:.1f}")
                w.w(f" MAE (SpeedR vs Perf, test)   = {coefs['speed_r_mae']:.1f}")
                w.w()
                if coefs["mae"] <= coefs["game_r_mae"]:
                    w.w(" ✅ CombinedR точнее чистого GameR на тестовой выборке.")
                else:
                    w.w(" ⚠️ CombinedR уступает GameR. Основной фокус на контроле зевков.")
            else:
                coefs = load_coefs()
                w.w(" ⚠️ Мало данных для динамической калибровки, применены стандартные веса:")
                w.w(" SpeedR = 3178 - 545 × avg_time")
                w.w(" CombR = 0.75 × GameR + 0.25 × SpeedR")
            w.w()

            # Динамика по всем окнам
            w.w_separator(title="ДИНАМИКА ПО ОКНАМ")
            cur = conn.cursor()
            for days in WINDOWS:
                cutoff = window_cutoff_ts(days)
                cur.execute("""
                    SELECT clocks, eval_history, white, my_rating, opp_rating, won, draw, acpl, time_control
                    FROM games
                    WHERE is_lag=0 AND is_cheater=0 AND end_time >= ?
                      AND my_rating > 0 AND acpl > 0
                      AND clocks IS NOT NULL AND clocks != '[]'
                      AND eval_history IS NOT NULL AND eval_history != '[]'
                """, (cutoff,))
                rows = cur.fetchall()
                if not rows:
                    w.w(f"  Окно {window_label(days):<10}: нет данных")
                    continue

                acpls, times, perfs = [], [], []
                for clocks_raw, evals_raw, white, my_r, opp_r, won, draw, acpl_val, tc in rows:
                    if not is_primary(tc):
                        continue
                    p_white = _is_player_white(white)
                    t_info = _compute_avg_time(clocks_raw, evals_raw, p_white, tc)
                    if not t_info or t_info.get("avg") is None:
                        continue
                    acpls.append(acpl_val)
                    times.append(t_info["avg"])
                    score = 1.0 if won else (0.5 if draw else 0.0)
                    perfs.append(opp_r + (score - 0.5) * 800.0)

                if not acpls:
                    w.w(f"  Окно {window_label(days):<10}: мало партий 1+0")
                    continue

                avg_acpl = statistics.mean(acpls)
                avg_t = statistics.mean(times)
                avg_perf = statistics.mean(perfs)
                g_val = game_rating(avg_acpl)
                s_val = speed_rating(avg_t, coefs)
                c_val = combined_rating(g_val, s_val, coefs)
                delta = g_val - s_val

                w.w(f"  Окно {window_label(days):<10} ({len(acpls)} игр):")
                w.w(f"     GameR: {g_val:.0f} | SpeedR: {s_val:.0f} | CombR: {c_val:.0f} | Perf: {avg_perf:.0f} | Δ: {delta:+.0f}")
            w.w()

            # Секция 'Сладкий темп'
            w.w_separator(title="СЛАДКИЙ ТЕМП (max CombinedR)")
            cutoff = window_cutoff_ts(90)
            cur.execute("""
                SELECT clocks, eval_history, white, acpl, time_control
                FROM games
                WHERE is_lag=0 AND is_cheater=0 AND end_time >= ?
                  AND my_rating > 0 AND acpl > 0
                  AND clocks IS NOT NULL AND clocks != '[]'
                  AND eval_history IS NOT NULL AND eval_history != '[]'
            """, (cutoff,))

            buckets = {"< 0.7": [], "0.7-0.9": [], "0.9-1.1": [], "1.1-1.3": [],
                       "1.3-1.6": [], "1.6-2.0": [], "> 2.0": []}
            for clocks_raw, evals_raw, white, acpl, tc in cur.fetchall():
                if not is_primary(tc):
                    continue
                player_is_white = _is_player_white(white)
                t = _compute_avg_time(clocks_raw, evals_raw, player_is_white, tc)
                if not t or t.get("avg") is None:
                    continue
                avg = t["avg"]
                if avg < 0.7: k = "< 0.7"
                elif avg < 0.9: k = "0.7-0.9"
                elif avg < 1.1: k = "0.9-1.1"
                elif avg < 1.3: k = "1.1-1.3"
                elif avg < 1.6: k = "1.3-1.6"
                elif avg < 2.0: k = "1.6-2.0"
                else: k = "> 2.0"
                buckets[k].append(acpl)

            mid = {"< 0.7": 0.6, "0.7-0.9": 0.8, "0.9-1.1": 1.0, "1.1-1.3": 1.2,
                   "1.3-1.6": 1.45, "1.6-2.0": 1.8, "> 2.0": 2.2}
            w.w(f"  {'Время/ход':<12} {'Игр':<6} {'ACPL':<8} {'CombinedR':<12}")
            w.w("  " + "-" * 45)
            best_b, best_c = None, 0
            for label, acpls in buckets.items():
                if not acpls:
                    continue
                avg_acpl = statistics.mean(acpls)
                comb = combined_rating_value(avg_acpl, mid[label], coefs)
                if comb > best_c:
                    best_c = comb
                    best_b = label
                w.w(f"  {label:<12} {len(acpls):<6} {avg_acpl:<8.1f} {comb:<12.0f}")
            if best_b:
                w.w(f"\n  🎯 Сладкий темп: {best_b} сек/ход (CombinedR ≈ {best_c:.0f})")
                w.w("     Играй в этом темпе — максимальный рейтинг.")

    finally:
        conn.close()


if __name__ == "__main__":
    report_combined_rating()
