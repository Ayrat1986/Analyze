# ============================================================
# analysis/dashboard_dynamics.py — v27.5
# Таблицы динамики по окнам, снапшоты мониторинга и темп vs рейтинг.
# ============================================================
import json
import statistics
from datetime import datetime
from _chess_utils import parse_time_spent
from analysis.common import (
    PLAYER,
    WINDOW_LABELS,
    WINDOWS,
    window_cutoff_ts,
    window_label,
)
from analysis.dashboard_db import game_aggr_scores, get_conn, percentile
from core.метрики import combined_rating, game_rating, speed_rating


def last_session_vs_windows() -> list:
    """Сравнение последней игровой сессии (разрыв <= 30 мин) с окнами 2/7/30/90/365 дней."""
    conn = get_conn()
    cur = conn.cursor()
    rows = []
    try:
        cur.execute(
            """
            SELECT end_time, won, draw, acpl, my_rating
            FROM games
            WHERE is_lag=0 AND is_cheater=0 AND end_time > 0
            ORDER BY end_time DESC
            LIMIT 100
            """
        )
        recent = cur.fetchall()
        session_games = []
        prev_ts = None
        for end_ts, won, draw, acpl, my_r in recent:
            if prev_ts is not None and (prev_ts - end_ts) > 1800:
                break
            session_games.append((won or 0, draw or 0, acpl or 0.0, my_r or 0))
            prev_ts = end_ts

        if session_games:
            n = len(session_games)
            wins = sum(g[0] for g in session_games)
            draws = sum(g[1] for g in session_games)
            acpls = [g[2] for g in session_games if g[2] > 0]
            ratings = [g[3] for g in session_games if g[3] > 0]
            avg_acpl = statistics.mean(acpls) if acpls else 0.0
            acpls_sorted = sorted(acpls)
            rows.append({
                "label": "Последняя сессия",
                "games": n,
                "win_rate": f"{(wins + 0.5 * draws) / n * 100:.1f}%",
                "acpl": round(avg_acpl, 1),
                "gamr": round(game_rating(avg_acpl)),
                "my_rating": round(statistics.mean(ratings)) if ratings else 0,
                "p90": round(percentile(acpls_sorted, 0.90)) if acpls_sorted else 0,
            })
        else:
            rows.append({
                "label": "Последняя сессия",
                "games": 0,
                "win_rate": "—",
                "acpl": 0,
                "gamr": 0,
                "my_rating": 0,
                "p90": 0,
            })

        for days in (2, 7, 30, 90, 365):
            cutoff = window_cutoff_ts(days)
            cur.execute(
                """
                SELECT COUNT(*), SUM(won), SUM(draw), AVG(acpl), AVG(my_rating)
                FROM games WHERE is_lag=0 AND is_cheater=0 AND end_time >= ?
                """,
                (cutoff,),
            )
            n, wins, draws, avg_acpl, avg_my = cur.fetchone()
            n = n or 0
            if not n:
                rows.append({
                    "label": window_label(days),
                    "games": 0,
                    "win_rate": "—",
                    "acpl": 0,
                    "gamr": 0,
                    "my_rating": 0,
                    "p90": 0,
                })
                continue

            cur.execute(
                """
                SELECT acpl FROM games
                WHERE is_lag=0 AND is_cheater=0 AND end_time >= ? AND acpl > 0
                ORDER BY acpl ASC
                """,
                (cutoff,),
            )
            acpls_sorted = [float(r[0]) for r in cur.fetchall() if r[0] is not None]
            wins, draws = wins or 0, draws or 0
            avg_acpl = avg_acpl or 0.0
            rows.append({
                "label": window_label(days),
                "games": n,
                "win_rate": f"{(wins + 0.5 * draws) / n * 100:.1f}%",
                "acpl": round(avg_acpl, 1),
                "gamr": round(game_rating(avg_acpl)),
                "my_rating": round(avg_my) if avg_my else 0,
                "p90": round(percentile(acpls_sorted, 0.90)) if acpls_sorted else 0,
            })
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return rows


def full_dynamics() -> list:
    conn = get_conn()
    cur = conn.cursor()
    result = []
    try:
        for days in WINDOWS:
            cutoff = window_cutoff_ts(days)
            cur.execute(
                """
                SELECT MAX(my_rating), AVG(my_rating), MIN(my_rating), COUNT(*),
                       AVG(acpl), AVG(opp_rating), SUM(won), SUM(draw)
                FROM games WHERE is_lag=0 AND is_cheater=0 AND my_rating > 0 AND end_time >= ?
                """,
                (cutoff,),
            )
            peak, home, bottom, n, avg_acpl, avg_opp, wins, draws = cur.fetchone()
            n, avg_acpl = n or 0, avg_acpl or 0.0
            wins, draws = wins or 0, draws or 0
            if not n:
                continue

            cur.execute(
                """
                SELECT acpl FROM games
                WHERE is_lag=0 AND is_cheater=0 AND end_time >= ? AND acpl > 0
                ORDER BY acpl ASC
                """,
                (cutoff,),
            )
            acpl_vals = [float(r[0]) for r in cur.fetchall() if r[0] is not None]
            p10 = round(percentile(acpl_vals, 0.10)) if acpl_vals else 0
            p50 = round(percentile(acpl_vals, 0.50)) if acpl_vals else 0
            p90 = round(percentile(acpl_vals, 0.90)) if acpl_vals else 0

            score = (wins + 0.5 * draws) / n
            perf = (avg_opp + (score - 0.5) * 800) if avg_opp else 0.0

            cur.execute(
                """
                SELECT clocks, white FROM games
                WHERE is_lag=0 AND is_cheater=0 AND end_time >= ? AND clocks IS NOT NULL
                """,
                (cutoff,),
            )
            times = []
            for c_raw, w in cur.fetchall():
                try:
                    c = json.loads(c_raw)
                    t = parse_time_spent(c, w == PLAYER)
                    if t:
                        times.extend(t)
                except Exception:
                    pass
            avg_t = statistics.mean(times) if times else 0.0

            g_r = game_rating(avg_acpl)
            s_r = speed_rating(avg_t)
            c_r = combined_rating(g_r, s_r)

            result.append({
                "window": WINDOW_LABELS[days],
                "games": n,
                "peak": peak or 0,
                "home": round(home) if home else 0,
                "bottom": bottom or 0,
                "win_rate": round(score * 100, 1),
                "avg_opp": round(avg_opp) if avg_opp else 0,
                "gamr": round(g_r),
                "speedr": round(s_r),
                "combined_r": round(c_r),
                "avg_time": round(avg_t, 2),
                "perf": round(perf),
                "p10": p10,
                "p50": p50,
                "p90": p90,
                "acpl": round(avg_acpl, 1),
            })
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return result


def monitoring_snapshot() -> list:
    """Снапшоты динамики по окнам 1 / 7 / 30 / 90 дней для 00_INDEX.txt."""
    conn = get_conn()
    cur = conn.cursor()
    snapshots = []
    today_str = datetime.now().strftime("%Y-%m-%d")
    windows_spec = [(1, "Сегодня"), (7, "7 дней"), (30, "30 дней"), (90, "90 дней")]

    try:
        for days, label in windows_spec:
            cutoff = window_cutoff_ts(days)
            cur.execute(
                """
                SELECT acpl, clocks, white FROM games
                WHERE is_lag=0 AND is_cheater=0 AND end_time >= ?
                """,
                (cutoff,),
            )
            rows = cur.fetchall()
            if not rows:
                continue

            acpl_vals = [float(r[0]) for r in rows if r[0] is not None and r[0] > 0]
            avg_acpl = statistics.mean(acpl_vals) if acpl_vals else 0.0
            stddev_acpl = statistics.pstdev(acpl_vals) if len(acpl_vals) > 1 else 0.0

            times = []
            for c_raw, w in ((r[1], r[2]) for r in rows if r[1]):
                try:
                    c = json.loads(c_raw)
                    t = parse_time_spent(c, w == PLAYER)
                    if t:
                        times.extend(t)
                except Exception:
                    pass
            avg_t = statistics.mean(times) if times else 0.0

            g_r = game_rating(avg_acpl)
            s_r = speed_rating(avg_t)
            c_r = combined_rating(g_r, s_r)
            delta = round(g_r - s_r) if (g_r and s_r) else 0

            aggr_scores = game_aggr_scores(cur, cutoff)
            avg_aggr = statistics.mean(aggr_scores) if aggr_scores else 7.8
            hunter_pct = (
                sum(1 for a in aggr_scores if a > 8.0) / len(aggr_scores) * 100.0
                if aggr_scores else 0.0
            )

            snapshots.append({
                "window": label,
                "date": today_str,
                "combined_r": round(c_r),
                "delta": delta,
                "stddev_acpl": round(stddev_acpl, 1),
                "aggression": round(avg_aggr, 1),
                "hunter_pct": round(hunter_pct),
            })
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return snapshots


def time_vs_rating() -> list:
    """Группировка партий за 90 дней по темпу (AvgT) против GameR и Win%."""
    conn = get_conn()
    cur = conn.cursor()
    cutoff = window_cutoff_ts(90)
    buckets = {
        "< 0.8с": [],
        "0.8-1.1с": [],
        "1.1-1.4с": [],
        "> 1.4с": [],
    }
    try:
        cur.execute(
            """
            SELECT clocks, white, acpl, won, draw FROM games
            WHERE is_lag=0 AND is_cheater=0 AND end_time >= ? AND clocks IS NOT NULL
            """,
            (cutoff,),
        )
        for c_raw, w, acpl, won, draw in cur.fetchall():
            try:
                c = json.loads(c_raw)
                t = parse_time_spent(c, w == PLAYER)
                if not t:
                    continue
                avg_t = statistics.mean(t)
                if avg_t < 0.8:
                    key = "< 0.8с"
                elif avg_t < 1.1:
                    key = "0.8-1.1с"
                elif avg_t < 1.4:
                    key = "1.1-1.4с"
                else:
                    key = "> 1.4с"
                buckets[key].append((acpl or 0.0, (won or 0) + 0.5 * (draw or 0)))
            except Exception:
                pass
    finally:
        try:
            conn.close()
        except Exception:
            pass

    out = []
    for label, items in buckets.items():
        if not items:
            continue
        valid_acpl = [x[0] for x in items if x[0] > 0]
        avg_a = statistics.mean(valid_acpl) if valid_acpl else 0.0
        win_p = sum(x[1] for x in items) / len(items) * 100.0
        out.append({
            "bucket": label,
            "games": len(items),
            "win_rate": round(win_p, 1),
            "acpl": round(avg_a, 1),
            "gamr": round(game_rating(avg_a)),
        })
    return out


def combined_vs_perf() -> list:
    """Сравнение расчётного CombR и фактического Perf по окнам."""
    return [
        {
            "window": d["window"],
            "combined_r": d["combined_r"],
            "perf": d["perf"],
            "gap": d["perf"] - d["combined_r"],
        }
        for d in full_dynamics()
    ]