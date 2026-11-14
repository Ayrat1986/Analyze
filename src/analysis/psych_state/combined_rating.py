# ============================================================
# analysis/psych_state/combined_rating.py (v25.1)
# FIX: Защита от k=0. Если калибровка не находит корреляции 
#      между временем и рейтингом, используется дефолт из ядра.
# ============================================================
import json
import statistics
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
        if not isinstance(coefs, dict) or "w1" not in coefs or "speed_k" not in coefs:
            return {}
        return coefs
    except Exception:
        return {}


def combined_rating_value(acpl, avg_time, coefs=None):
    if coefs is None:
        coefs = load_coefs()
    game_r = game_rating(acpl)
    speed_r = speed_rating(avg_time, coefs)
    return combined_rating(game_r, speed_r, coefs)


def _calibrate_combined(conn, days=90):
    speed_calib = _calibrate(conn, days)
    if not speed_calib:
        return None
    k, b = _linear_fit(speed_calib)
    if k is None:
        return None

    # ФИКС: Если k около нуля, это значит, что рейтинг не зависит от времени.
    # В этом случае мы используем дефолтную теоретическую формулу, чтобы SpeedR работал.
    if abs(k) < 50:
        print("⚠️ Калибровка SpeedR дала k≈0. Используем дефолт (3178 - 545*t).")
        k = -545.0
        b = 3178.0

    cutoff = window_cutoff_ts(days)
    cur = conn.cursor()
    cur.execute("""
        SELECT clocks, eval_history, white, my_rating, opp_rating, won, draw, acpl, time_control
        FROM games
        WHERE is_lag=0 AND is_cheater=0 AND end_time >= ?
          AND my_rating > 0 AND acpl > 0
          AND clocks IS NOT NULL AND clocks != '[]'
          AND eval_history IS NOT NULL AND eval_history != '[]'
    """, (cutoff,))

    samples = []
    for clocks_raw, evals_raw, white, my_rating, opp_rating, won, draw, acpl, tc in cur.fetchall():
        player_is_white = _is_player_white(white)
        t = _compute_avg_time(clocks_raw, evals_raw, player_is_white, tc)
        if not t:
            continue
        avg_time = t["avg"]
        game_r = game_rating(acpl)
        speed_r = b + k * avg_time
        perf = opp_rating + (((won or 0) + 0.5 * (draw or 0)) - 0.5) * 800
        samples.append({"game_r": game_r, "speed_r": speed_r, "perf": perf})

    if len(samples) < 50:
        return None

    best_w1 = 0.5
    best_mae = float("inf")
    for w1_int in range(0, 21):
        w1 = w1_int / 20
        mae = sum(abs(w1 * s["game_r"] + (1 - w1) * s["speed_r"] - s["perf"])
                  for s in samples) / len(samples)
        if mae < best_mae:
            best_mae = mae
            best_w1 = w1

    game_r_mae = sum(abs(s["game_r"] - s["perf"]) for s in samples) / len(samples)
    speed_r_mae = sum(abs(s["speed_r"] - s["perf"]) for s in samples) / len(samples)

    return {
        "w1": round(best_w1, 2),
        "w2": round(1 - best_w1, 2),
        "mae": round(best_mae, 1),
        "game_r_mae": round(game_r_mae, 1),
        "speed_r_mae": round(speed_r_mae, 1),
        "n": len(samples),
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
        w.w("Веса калибруются: min MAE(CombinedR − Perf_факт)")
        w.w("§17: формулы — только из core/метрики.py")
        w.w("⚠️ Только 1+0 (bullet). База времени = 60 сек.")
        w.w()

        w.w_separator(title="КАЛИБРОВКА (90 дней)")
        coefs = _calibrate_combined(conn, days=90)

        if coefs:
            save_coefs(coefs)
            w.w(f"  N = {coefs['n']} партий")
            w.w(f"  w1 (GameR)  = {coefs['w1']}")
            w.w(f"  w2 (SpeedR) = {coefs['w2']}")
            w.w(f"  SpeedR = {coefs['speed_b']:.0f} + ({coefs['speed_k']:.0f}) × avg_time")
            w.w()
            w.w(f"  MAE (CombinedR vs Perf) = {coefs['mae']:.1f}")
            w.w(f"  MAE (GameR только)      = {coefs['game_r_mae']:.1f}")
            w.w(f"  MAE (SpeedR только)     = {coefs['speed_r_mae']:.1f}")
            w.w()
            if coefs["mae"] < coefs["game_r_mae"]:
                imp = (coefs["game_r_mae"] - coefs["mae"]) / coefs["game_r_mae"] * 100
                w.w(f"  ✅ CombinedR точнее GameR на {imp:.0f}%")
            else:
                w.w(f"  ⚠️ CombinedR НЕ точнее GameR. Используй только GameR.")
        else:
            w.w("  ⚠️ Мало данных для калибровки (нужно 50+ партий).")
            w.w("  💡 Ядро (core.метрики) использует дефолт:")
            w.w("     SpeedR = 3178 - 545 × avg_time")
            w.w("     CombR  = 0.7 × GameR + 0.3 × SpeedR")
            w.w("  💡 coefs.json создастся автоматически после первой калибровки.")
        w.w()

        for days in WINDOWS:
            w.w_separator(title=f"ОКНО: {window_label(days)}")
            cutoff = window_cutoff_ts(days)
            cur = conn.cursor()
            cur.execute("""
                SELECT clocks, eval_history, white, my_rating, opp_rating, won, draw, acpl, time_control
                FROM games
                WHERE is_lag=0 AND is_cheater=0 AND end_time >= ?
                  AND my_rating > 0 AND acpl > 0
                  AND clocks IS NOT NULL AND clocks != '[]'
                  AND eval_history IS NOT NULL AND eval_history != '[]'
            """, (cutoff,))

            comb, game, speed, perf, myr = [], [], [], [], []
            for clocks_raw, evals_raw, white, my_rating, opp_rating, won, draw, acpl, tc in cur.fetchall():
                player_is_white = _is_player_white(white)
                t = _compute_avg_time(clocks_raw, evals_raw, player_is_white, tc)
                if not t:
                    continue
                avg_time = t["avg"]
                g_r = game_rating(acpl)
                s_r = speed_rating(avg_time, coefs)
                comb.append(combined_rating(g_r, s_r, coefs))
                game.append(g_r)
                speed.append(s_r)
                perf.append(opp_rating + (((won or 0) + 0.5 * (draw or 0)) - 0.5) * 800)
                myr.append(my_rating)

            if len(comb) < 5:
                w.w("  ⚠️ Мало данных.")
                w.w()
                continue

            w.w(f"  Партий: {len(comb)}")
            w.w(f"  {'Метрика':<15} {'Среднее':<10} {'MAE vs Perf':<15}")
            w.w("  " + "-" * 42)
            mae_g = statistics.mean(abs(g - p) for g, p in zip(game, perf))
            mae_s = statistics.mean(abs(s - p) for s, p in zip(speed, perf))
            mae_c = statistics.mean(abs(c - p) for c, p in zip(comb, perf))
            w.w(f"  {'GameR':<15} {statistics.mean(game):<10.0f} {mae_g:<15.1f}")
            w.w(f"  {'SpeedR':<15} {statistics.mean(speed):<10.0f} {mae_s:<15.1f}")
            w.w(f"  {'CombinedR':<15} {statistics.mean(comb):<10.0f} {mae_c:<15.1f}")
            w.w(f"  {'Perf (факт)':<15} {statistics.mean(perf):<10.0f} {'—':<15}")
            w.w(f"  {'Реальный рейт':<15} {statistics.mean(myr):<10.0f} {'—':<15}")
            w.w()
            if mae_c < mae_g:
                w.w(f"  ✅ CombinedR точнее GameR на {(mae_g-mae_c)/mae_g*100:.0f}%")
            w.w()

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
            player_is_white = _is_player_white(white)
            t = _compute_avg_time(clocks_raw, evals_raw, player_is_white, tc)
            if not t:
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
            w.w(f"     Играй в этом темпе — максимальный рейтинг.")

    conn.close()