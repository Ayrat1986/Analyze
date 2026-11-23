# ============================================================
# analysis/psych_state/combined_rating.py (v25.3)
# FIX v25.3:
#   - §17: строгая гармонизация с core/метрики.py.
#   - Только 1+0 (bullet) с проверкой is_primary(time_control).
#   - Безопасная калибровка весов (w1, w2) без искажения шкал GameR/SpeedR.
#   - Защита веб-дашборда от изменения сигнатуры coefs.
# ============================================================
import json
import statistics
import os
from datetime import datetime, timezone
import _common
from analysis.common import report_context, window_cutoff_ts
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
        if not isinstance(coefs, dict) or "w1" not in coefs or "speed_k" not in coefs:
            return {}
        return coefs
    except Exception:
        return {}


def _calibrate_combined(conn, days: int = 90):
    speed_calib = _calibrate(conn, days)
    if not speed_calib:
        return None
    k, b = _linear_fit(speed_calib)
    if k is None:
        return None
    if abs(k) < 50:
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
        game_r = game_rating(acpl)
        speed_r = b + k * avg_time
        perf = opp_rating + (((won or 0) + 0.5 * (draw or 0)) - 0.5) * 800
        samples.append({
            "game_r": game_r,
            "speed_r": speed_r,
            "perf": perf,
            "end_time": end_time,
        })

    if len(samples) < 30:
        return None

    samples.sort(key=lambda s: s["end_time"])
    split_idx = int(len(samples) * 0.7)
    train = samples[:split_idx] if split_idx >= 20 else samples
    test = samples[split_idx:] if split_idx >= 20 else samples

    best_w1 = 0.70
    best_mae_train = float("inf")
    # Подбор устойчивых весов с шагом 0.05 в разумном диапазоне [0.5, 0.85]
    for w1_int in range(10, 18):
        w1 = w1_int / 20.0
        w2 = 1.0 - w1
        mae = sum(abs((w1 * s["game_r"] + w2 * s["speed_r"]) - s["perf"]) for s in train) / len(train)
        if mae < best_mae_train:
            best_mae_train = mae
            best_w1 = w1

    best_w2 = round(1.0 - best_w1, 2)
    mae_test_comb = sum(abs((best_w1 * s["game_r"] + best_w2 * s["speed_r"]) - s["perf"]) for s in test) / len(test)
    mae_test_game = statistics.mean(abs(s["game_r"] - s["perf"]) for s in test)
    mae_test_speed = statistics.mean(abs(s["speed_r"] - s["perf"]) for s in test)

    return {
        "w1": best_w1,
        "w2": best_w2,
        "mae": round(mae_test_comb, 1),
        "game_r_mae": round(mae_test_game, 1),
        "speed_r_mae": round(mae_test_speed, 1),
        "n": len(samples),
        "n_train": len(train),
        "n_test": len(test),
        "speed_k": round(k, 1),
        "speed_b": round(b, 1),
        "calibrated_at": datetime.now(timezone.utc).isoformat(),
        "is_default": False,
    }


def report_combined_rating():
    conn = _conn()
    with report_context("combined_rating") as w:
        w.w_separator(title="COMBINED RATING (GameR + SpeedR)")
        w.w("CombinedR = w1 × GameR + w2 × SpeedR")
        w.w("GameR = 3200 − ACPL×10 (точность)")
        w.w("SpeedR = speed_b + speed_k × avg_time (скорость)")
        w.w("§17: все формулы синхронизированы с core/метрики.py")
        w.w("⚠️ Только 1+0 (bullet). База времени = 60 сек.")
        w.w()
        w.w_separator(title="КАЛИБРОВКА (90 дней)")
        coefs = _calibrate_combined(conn, days=90)
        if coefs:
            save_coefs(coefs)
            w.w(f" N = {coefs['n']} партий (train={coefs['n_train']}, test={coefs['n_test']})")
            w.w(f" w1 (GameR) = {coefs['w1']}")
            w.w(f" w2 (SpeedR) = {coefs['w2']}")
            w.w(f" SpeedR = {coefs['speed_b']:.0f} + ({coefs['speed_k']:.0f}) × avg_time")
            w.w()
            w.w(f" MAE (CombinedR vs Perf, test) = {coefs['mae']:.1f}")
            w.w(f" MAE (GameR vs Perf, test)    = {coefs['game_r_mae']:.1f}")
            w.w(f" MAE (SpeedR vs Perf, test)   = {coefs['speed_r_mae']:.1f}")
            w.w()
            if coefs["mae"] <= coefs["game_r_mae"]:
                w.w(" ✅ CombinedR устойчивее чистого GameR на тестовой выборке.")
            else:
                w.w(" ⚠️ GameR ближе к Perf, чем CombinedR. Внимание на контроль зевков.")
        else:
            coefs = load_coefs()
            w.w(" ⚠️ Недостаточно данных для перекалибровки (нужно 30+ чистых партий 1+0).")
            w.w(" Используются проверенные параметры:")
            w.w(" SpeedR = 3178 - 545 × avg_time")
            w.w(" CombR = 0.70 × GameR + 0.30 × SpeedR")
        w.w()

        w.w_separator(title="СЛАДКИЙ ТЕМП (max CombinedR)")
        cutoff = window_cutoff_ts(90)
        cur = conn.cursor()
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
            # Расчёт через функцию ядра
            g_val = game_rating(avg_acpl)
            s_val = speed_rating(mid[label], coefs if coefs else None)
            comb = combined_rating(g_val, s_val, coefs if coefs else None)
            if comb > best_c:
                best_c = comb
                best_b = label
            w.w(f"  {label:<12} {len(acpls):<6} {avg_acpl:<8.1f} {comb:<12.0f}")
        if best_b:
            w.w(f"\n  🎯 Сладкий темп: {best_b} сек/ход (CombinedR ≈ {best_c:.0f})")
            w.w("     Играй в этом темпе — максимальный рейтинг.")

    conn.close()
