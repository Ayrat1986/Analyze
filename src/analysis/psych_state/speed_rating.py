# ============================================================
# analysis/psych_state/speed_rating.py (v19.4)
# SpeedR — аналог GameR, но на основе avg_time.
# Исправлено: base_time из time_control (1+0 или 3+2).
# ============================================================
import json
import statistics
from analysis.common import report_context, WINDOWS, window_label, window_cutoff_ts
from core.time_control import parse_time_control
from .common import _conn, _is_player_white


def _compute_avg_time(clocks_raw, evals_raw, player_is_white, time_control="60"):
    """Среднее время на ход (общее + по фазам)."""
    try:
        clocks = json.loads(clocks_raw) if clocks_raw else []
        evals = json.loads(evals_raw) if evals_raw else []
    except Exception:
        return None
    if not clocks or not evals:
        return None

    base_sec, _ = parse_time_control(time_control)
    times, times_op, times_mid, times_end = [], [], [], []

    for i in range(1, len(evals)):
        move_num = evals[i][0]
        ply = (move_num - 1) * 2 + (0 if player_is_white else 1)
        time_spent = None
        if ply == 0:
            time_spent = base_sec - clocks[0]
        elif ply == 1 and len(clocks) > 1:
            time_spent = clocks[0] - clocks[1]
        elif ply >= 2 and ply < len(clocks):
            time_spent = clocks[ply - 2] - clocks[ply]
        
        if time_spent is None or time_spent <= 0 or time_spent > 30:
            continue
        
        times.append(time_spent)
        if move_num <= 10:
            times_op.append(time_spent)
        elif move_num <= 30:
            times_mid.append(time_spent)
        else:
            times_end.append(time_spent)

    if not times:
        return None
    return {
        "avg": statistics.mean(times),
        "opening": statistics.mean(times_op) if times_op else 0,
        "middlegame": statistics.mean(times_mid) if times_mid else 0,
        "endgame": statistics.mean(times_end) if times_end else 0,
    }


def _calibrate(conn, days):
    """Bucket by avg_time → avg my_rating + avg acpl."""
    cur = conn.cursor()
    cutoff = window_cutoff_ts(days)
    cur.execute("""
        SELECT clocks, eval_history, white, my_rating, acpl, time_control
        FROM games
        WHERE is_lag=0 AND is_cheater=0 AND end_time >= ?
          AND my_rating > 0 AND acpl > 0
          AND clocks IS NOT NULL AND clocks != '[]'
          AND eval_history IS NOT NULL AND eval_history != '[]'
    """, (cutoff,))
    
    buckets = {
        "< 0.7":   {"times": [], "ratings": [], "acpls": []},
        "0.7-0.9": {"times": [], "ratings": [], "acpls": []},
        "0.9-1.1": {"times": [], "ratings": [], "acpls": []},
        "1.1-1.3": {"times": [], "ratings": [], "acpls": []},
        "1.3-1.6": {"times": [], "ratings": [], "acpls": []},
        "1.6-2.0": {"times": [], "ratings": [], "acpls": []},
        "> 2.0":   {"times": [], "ratings": [], "acpls": []},
    }
    
    for clocks_raw, evals_raw, white, my_rating, acpl, tc in cur.fetchall():
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
        
        buckets[k]["times"].append(avg)
        buckets[k]["ratings"].append(my_rating)
        buckets[k]["acpls"].append(acpl)
    
    result = []
    for label, d in buckets.items():
        if d["ratings"]:
            result.append({
                "label": label,
                "avg_time": statistics.mean(d["times"]),
                "avg_rating": statistics.mean(d["ratings"]),
                "avg_acpl": statistics.mean(d["acpls"]),
                "count": len(d["ratings"]),
            })
    return result


def _linear_fit(calib):
    """Линейная регрессия: rating = b + k × avg_time."""
    if len(calib) < 3:
        return None, None
    xs = [r["avg_time"] for r in calib]
    ys = [r["avg_rating"] for r in calib]
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
    den = sum((xs[i] - mean_x) ** 2 for i in range(n))
    if den <= 0:
        return None, None
    k = num / den
    b = mean_y - k * mean_x
    return k, b


def report_speed_rating():
    conn = _conn()
    
    with report_context("speed_rating") as w:
        w.w_separator(title="SPEED RATING (скорость хода → рейтинг)")
        w.w("Аналог GameR, но на основе avg_time.")
        w.w("GameR = 3200 - ACPL × 10")
        w.w("SpeedR = калиброванное соответствие avg_time → my_rating")
        w.w("⚠️ База времени из time_control (1+0 → 60 сек).")
        w.w()
        
        for days in WINDOWS:
            w.w_separator(title=f"ОКНО: {window_label(days)}")
            calib = _calibrate(conn, days)
            if not calib:
                w.w("⚠️ Нет данных.")
                w.w()
                continue
            
            w.w(f"  {'Время/ход':<10} {'Игр':<6} {'Ср. рейтинг':<13} {'Ср. ACPL':<10}")
            w.w("  " + "-" * 45)
            for row in calib:
                w.w(f"  {row['label']:<10} {row['count']:<6} "
                    f"{row['avg_rating']:<13.0f} {row['avg_acpl']:<10.1f}")
            w.w()
            
            k, b = _linear_fit(calib)
            if k is not None:
                w.w(f"  📈 Формула (линейная): SpeedR = {b:.0f} + ({k:.0f}) × avg_time")
                w.w(f"     avg_time=1.0 → SpeedR {b + k*1.0:.0f}")
                w.w(f"     avg_time=1.2 → SpeedR {b + k*1.2:.0f}")
                w.w(f"     avg_time=1.5 → SpeedR {b + k*1.5:.0f}")
                w.w(f"     avg_time=1.8 → SpeedR {b + k*1.8:.0f}")
            w.w()
        
        w.w_separator(title="КАК ИСПОЛЬЗОВАТЬ")
        w.w("1. Найди свой 'сладкий темп' — где SpeedR = 2700+.")
        w.w("2. Играй в этом темпе сознательно.")
        w.w("3. Если SpeedR > GameR — ты спешишь (автопилот).")
        w.w("4. Если SpeedR < GameR — ты медлишь (цейтнот).")
        w.w("5. Цель: SpeedR ≈ GameR, оба растут.")
    
    conn.close()