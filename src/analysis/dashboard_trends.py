# ============================================================
# analysis/dashboard_trends.py — Тренды (v20.2)
# ============================================================
import json, statistics
from collections import defaultdict
from analysis.common import _conn, PLAYER, window_cutoff_ts
from core.метрики import game_rating
from _chess_utils import parse_time_spent

def get_daily_metrics_trend(days=30):
    conn = _conn(); cur = conn.cursor(); cutoff = window_cutoff_ts(days)
    cur.execute("""
        SELECT date(end_time, 'unixepoch', '+3 hours') AS day, 
               COUNT(*) as n, AVG(acpl) as acpl, AVG(opp_rating) as avg_opp, 
               SUM(won) as wins, SUM(draw) as draws, AVG(my_rating) as avg_my_rating 
        FROM games WHERE is_lag=0 AND is_cheater=0 AND my_rating > 0 AND end_time >= ? AND acpl > 0 
        GROUP BY day ORDER BY day ASC
    """, (cutoff,))
    daily_stats = cur.fetchall()
    if not daily_stats: conn.close(); return []

    cur.execute("""
        SELECT date(end_time, 'unixepoch', '+3 hours') AS day, clocks, white, acpl 
        FROM games WHERE is_lag=0 AND is_cheater=0 AND my_rating > 0 AND end_time >= ? AND acpl > 0 
        AND clocks IS NOT NULL AND clocks != '[]'
    """, (cutoff,))
    time_rows = cur.fetchall()
    times_by_day = defaultdict(list)
    for day, clocks_raw, white, acpl in time_rows:
        try:
            clocks = json.loads(clocks_raw)
            if not clocks: continue
        except Exception: continue
        player_is_white = (white or "").lower() == PLAYER.lower()
        times = parse_time_spent(clocks, player_is_white)
        if times: times_by_day[day].append(sum(times) / len(times))

    result = []; speed_b = 3178; speed_k = -545; w1 = 0.5; w2 = 0.5
    for day, n, avg_acpl, avg_opp, wins, draws, avg_my_rating in daily_stats:
        if n < 3: continue
        win_rate = (wins + 0.5 * draws) / n * 100
        perf = avg_opp + (win_rate / 100 - 0.5) * 800
        gamr = game_rating(avg_acpl)
        times = times_by_day.get(day, [])
        avg_time = statistics.mean(times) if times else 1.20
        speed_r = speed_b + speed_k * avg_time
        result.append({
            "Дата": day, "Игр": n, 
            "Wins": wins, "Draws": draws, "AvgOpp": avg_opp,
            "Rating": round(avg_my_rating) if avg_my_rating else 0,
            "GameR": round(gamr), "SpeedR": round(speed_r),
            "CombR": round(w1 * gamr + w2 * speed_r), "Perf": round(perf),
            "Delta": round(gamr - speed_r), "AvgT": round(avg_time, 2), "ACPL": round(avg_acpl, 1)
        })
    conn.close()
    return result

def get_hourly_rhythm():
    conn = _conn(); cur = conn.cursor()
    cur.execute("SELECT strftime('%H', datetime(end_time, 'unixepoch', '+3 hours')) AS hour, COUNT(*) as n, SUM(won) as wins, SUM(draw) as draws, AVG(acpl) as acpl, AVG(opp_rating) as avg_opp FROM games WHERE is_lag=0 AND is_cheater=0 AND acpl > 0 GROUP BY hour HAVING n >= 10 ORDER BY hour")
    rows = cur.fetchall(); result = []
    for hour, n, wins, draws, acpl, avg_opp in rows:
        win_rate = (wins + 0.5 * draws) / n * 100
        gamr = game_rating(acpl)
        cur.execute("SELECT clocks, white FROM games WHERE is_lag=0 AND is_cheater=0 AND acpl > 0 AND strftime('%H', datetime(end_time, 'unixepoch', '+3 hours')) = ? AND clocks IS NOT NULL AND clocks != '[]'", (hour,))
        times = []
        for clocks_raw, white in cur.fetchall():
            try:
                clocks = json.loads(clocks_raw)
                if not clocks: continue
            except Exception: continue
            player_is_white = (white or "").lower() == PLAYER.lower()
            t = parse_time_spent(clocks, player_is_white)
            if t: times.append(sum(t) / len(t))
        avg_time = statistics.mean(times) if times else 0
        speed_r = 3178 - 545 * avg_time if avg_time else 0
        result.append({"hour": int(hour), "games": n, "win_rate": round(win_rate, 1), "acpl": round(acpl, 1), "avg_time": round(avg_time, 2), "gamr": round(gamr), "comb_r": round(0.5 * gamr + 0.5 * speed_r)})
    conn.close(); return result

def get_cascade_trend(days=30):
    conn = _conn(); cur = conn.cursor(); cutoff = window_cutoff_ts(days)
    cur.execute("""
        WITH ranked_blunders AS (
            SELECT g.url, date(g.end_time, 'unixepoch', '+3 hours') AS day, b.move_num,
                LAG(b.move_num) OVER (PARTITION BY g.url ORDER BY b.move_num) as prev_move
            FROM blunders b JOIN games g ON g.url = b.game_url
            WHERE g.is_lag=0 AND g.is_cheater=0 AND g.end_time >= ? AND b.is_my_blunder=1 AND b.is_berserk=0 AND b.is_instant=0
        )
        SELECT day, COUNT(DISTINCT url) as cascade_games FROM ranked_blunders WHERE move_num - prev_move <= 5 GROUP BY day ORDER BY day ASC
    """, (cutoff,))
    rows = cur.fetchall(); conn.close()
    return [{"Дата": day, "Каскады": cnt} for day, cnt in rows]

def get_blunder_map_data():
    conn = _conn(); cur = conn.cursor()
    cur.execute("SELECT b.move_num, COUNT(*), AVG(b.loss_cp), AVG(b.time_spent) FROM blunders b JOIN games g ON g.url = b.game_url WHERE g.is_lag=0 AND g.is_cheater=0 AND b.is_my_blunder=1 AND b.is_berserk=0 AND b.is_instant=0 AND b.move_num BETWEEN 11 AND 30 GROUP BY b.move_num ORDER BY b.move_num")
    rows = cur.fetchall(); conn.close()
    return [{"Ход": move, "Зевки": cnt, "Потеря (CP)": round(loss or 0), "Время (сек)": round(t or 0, 2)} for move, cnt, loss, t in rows]