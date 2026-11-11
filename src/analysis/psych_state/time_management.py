# ============================================================
# analysis/psych_state/time_management.py (v19.1)
# ============================================================
import os
import json
import statistics
from datetime import datetime, timedelta, timezone
from importlib import import_module

import _common
from _chess_utils import parse_time_spent, rating_cat
from analysis.common import report_context
from .common import _conn, REPORTS_DIR, PLAYER, _is_player_white, _load_clocks_evals

fetch_api = import_module("01_fetch_chess_api")

def _analyze_game_for_time(game_data, player):
    import chess.pgn, io
    from _chess_utils import parse_clock
    pgn = game_data.get("pgn", "")
    if not pgn: return None
    game = chess.pgn.read_game(io.StringIO(pgn))
    if not game: return None
    clocks = parse_clock(pgn)
    if len(clocks) < 10: return None

    player_is_white = game.headers.get("White", "") == player
    tc = game_data.get("time_control", "60")
    try: base_time = float(tc.split("+")[0]) if "+" in tc else float(tc)
    except ValueError: base_time = 60.0

    result = game.headers.get("Result", "?")
    won = (result == "1-0") if player_is_white else (result == "0-1")
    lost = (result == "0-1") if player_is_white else (result == "1-0")
    draw = (result == "1/2-1/2")

    our_idx = (list(range(0, len(clocks), 2)) if player_is_white else list(range(1, len(clocks), 2)))
    if len(our_idx) < 5: return None

    times = parse_time_spent(clocks, player_is_white, max_diff_sec=base_time * 2, first_base=base_time)
    if len(times) < 5: return None

    def get_clock_local(move_num):
        if move_num - 1 < len(our_idx): return clocks[our_idx[move_num - 1]]
        return None

    game_length = len(list(game.mainline()))
    return {
        "won": won, "lost": lost, "draw": draw,
        "opponent_rating": game_data.get("black", {}).get("rating") if player_is_white else game_data.get("white", {}).get("rating"),
        "my_rating": game_data.get("white", {}).get("rating") if player_is_white else game_data.get("black", {}).get("rating"),
        "end_time": game_data.get("end_time", 0),
        "avg_speed": sum(times) / len(times),
        "opening_avg": sum(times[:10]) / len(times[:10]) if times[:10] else 0,
        "middlegame_avg": (sum(times[10:30]) / len(times[10:30]) if len(times) > 10 else 0),
        "endgame_avg": (sum(times[30:]) / len(times[30:]) if len(times) > 30 else 0),
        "clock_at_10": get_clock_local(10), "clock_at_20": get_clock_local(20),
        "clock_at_30": get_clock_local(30), "clock_at_40": get_clock_local(40),
        "slow_moves": sum(1 for t in times if t > 3), "very_slow_moves": sum(1 for t in times if t > 5),
        "total_our_moves": len(times), "game_length": game_length,
    }

def _stats_for_time_window(stats_list, window_name, w):
    if not stats_list:
        w.w(f"  Нет данных.")
        return
    n = len(stats_list)
    wins = sum(1 for s in stats_list if s["won"])
    losses = sum(1 for s in stats_list if s["lost"])
    draws = sum(1 for s in stats_list if s["draw"])
    win_rate = wins / n * 100

    ratings = [s["opponent_rating"] for s in stats_list if s["opponent_rating"] > 0]
    avg_opponent = sum(ratings) / len(ratings) if ratings else 0
    
    my_ratings_with_time = sorted([(s.get("end_time", 0), s["my_rating"]) for s in stats_list if s.get("my_rating", 0) > 0], key=lambda x: x[0])
    my_vals = [r for _, r in my_ratings_with_time]
    avg_my = sum(my_vals) / len(my_vals) if my_vals else 0
    first_my = my_ratings_with_time[0][1] if my_ratings_with_time else 0
    last_my = my_ratings_with_time[-1][1] if my_ratings_with_time else 0

    avg_opening = sum(s["opening_avg"] for s in stats_list) / n
    avg_mid = sum(s["middlegame_avg"] for s in stats_list) / n
    avg_end = sum(s["endgame_avg"] for s in stats_list) / n

    w.w(f"Партий: {n}")
    w.w(f"Побед: {wins} | Поражений: {losses} | Ничьих: {draws}")
    w.w(f"% побед: {win_rate:.1f}%")
    w.w()
    w.w("--- РЕЙТИНГИ ---")
    w.w(f"  Мой рейтинг на начало окна:  {first_my}")
    w.w(f"  Мой средний рейтинг в окне:  {avg_my:.0f}")
    w.w(f"  Мой последний рейтинг:       {last_my}")
    w.w(f"  Средний рейтинг соперников:  {avg_opponent:.0f}")
    w.w()
    w.w("--- ВРЕМЯ НА ХОД ---")
    w.w(f"  Дебют (1-10):         {avg_opening:.2f} сек")
    w.w(f"  Миттельшпиль (11-30): {avg_mid:.2f} сек")
    w.w(f"  Эндшпиль (31+):       {avg_end:.2f} сек")
    w.w()

def run_time_management():
    print("  1/4. Time report windows")
    games = fetch_api.get_games_from_cache(
        player=fetch_api.PLAYER, days=fetch_api.DAYS_TO_FETCH,
        time_class=fetch_api.TIME_CLASS, max_base=fetch_api.MAX_BULLET_BASE_TIME, require_pgn=True,
    )
    if games:
        now = datetime.now(timezone.utc)
        cutoffs = {d: int((now - timedelta(days=d)).timestamp()) for d in [1, 2, 7, 30, 90]}
        stats_by_window = {}
        for d in [1, 2, 7, 30, 90]:
            games_d = [g for g in games if g.get("end_time", 0) >= cutoffs[d]]
            stats_by_window[d] = [s for g in games_d if (s := _analyze_game_for_time(g, PLAYER))]

        with report_context("time_report_windows") as w:
            w.w_separator(title="TIME ANALYSIS — 1/2/7/30/90")
            for d in [1, 2, 7, 30, 90]:
                label = f"{d} ДЕНЬ" if d == 1 else (f"{d} ДНЯ" if d == 2 else f"{d} ДНЕЙ")
                w.w(f"\n{'=' * 40}\nОКНО: {label}\n{'=' * 40}")
                _stats_for_time_window(stats_by_window[d], label, w)

    print("  2/4. Time profile")
    conn = _conn(); cur = conn.cursor()
    with report_context("time_profile") as w:
        w.w_separator(title="TIME PROFILE: просрочки, менеджмент, тайминг")
        w.w("📊 СЕКЦИЯ 1: ПРОСРОЧКИ")
        cur.execute("""
            SELECT timeout_at_move, COUNT(*), ROUND(AVG(timeout_with_clock), 1)
            FROM games WHERE is_lag=0 AND is_cheater=0 AND timeout_at_move IS NOT NULL AND reason = 'просрочка'
            GROUP BY timeout_at_move ORDER BY timeout_at_move
        """)
        rows = cur.fetchall()
        if rows:
            total = sum(r[1] for r in rows)
            w.w(f"  Всего просрочек: {total}")
            for move, cnt, avg_rem in sorted(rows, key=lambda x: -x[1])[:10]:
                w.w(f"  {move:<6} {cnt:<12} {avg_rem or 0:.1f}")
        else: w.w("  ⚠️ Нет данных о просрочках.")
        w.w()
        w.w("📊 СЕКЦИЯ 2: ТАЙМИНГ ЗЕВКОВ")
        cur.execute("""
            SELECT b.move_num, COUNT(*), ROUND(AVG(b.loss_cp)), ROUND(AVG(b.time_spent), 1)
            FROM blunders b JOIN games g ON g.url = b.game_url
            WHERE g.is_lag=0 AND g.is_cheater=0 AND b.is_berserk=0 AND b.is_instant=0 AND b.is_my_blunder=1 AND b.time_spent IS NOT NULL
            GROUP BY b.move_num HAVING COUNT(*) >= 2 ORDER BY COUNT(*) DESC LIMIT 15
        """)
        for mn, cnt, avg_loss, avg_time in cur.fetchall():
            w.w(f"  {mn:<6} {cnt:<8} {avg_loss or 0:<12.0f} {avg_time or 0:.1f} сек")
    conn.close()

    print("  3/4. Lag report")
    conn = _conn(); cur = conn.cursor()
    cur.execute("SELECT url, white, clocks FROM games WHERE is_cheater=0 AND clocks IS NOT NULL AND clocks != '[]'")
    rows = cur.fetchall()
    lag_games = total_games = total_anomalies = 0
    anomaly_times = []
    for url, white, clocks_raw in rows:
        clocks, _ = _load_clocks_evals(clocks_raw, None)
        if not clocks: continue
        player_is_white = _is_player_white(white)
        times = parse_time_spent(clocks, player_is_white)
        if len(times) < 5: continue
        total_games += 1
        median_time = statistics.median(times)
        anomalies = [t for t in times if t > max(5.0, median_time * 3)]
        if anomalies:
            lag_games += 1; total_anomalies += len(anomalies); anomaly_times.extend(anomalies)
    with report_context("lag_report") as w:
        w.w_separator(title="LAG REPORT — аномалии времени")
        w.w(f"Всего партий: {total_games}")
        w.w(f"Партий с лагом: {lag_games} ({lag_games/max(1,total_games)*100:.1f}%)")
        w.w(f"Аномальных ходов: {total_anomalies}")
        if anomaly_times:
            w.w(f"Среднее время аномалии: {statistics.mean(anomaly_times):.1f} сек")
    conn.close()

    print("  4/4. Timeout vs Rating")
    from core.метрики import game_rating as calc_gr
    conn = _conn(); cur = conn.cursor()
    cur.execute("""
        SELECT opp_rating, clocks, won, draw, acpl, white FROM games
        WHERE is_lag=0 AND is_cheater=0 AND opp_rating > 0 AND clocks IS NOT NULL AND clocks != '[]' AND acpl > 0
    """)
    time_data = {r: {"slow_n": 0, "slow_gr": 0, "fast_n": 0, "fast_gr": 0} for r in ["< 2500", "2500-2599", "2600-2699", "2700+"]}
    for opp_rating, clocks_raw, won, draw, acpl, white in cur.fetchall():
        rng = rating_cat(opp_rating)
        if rng not in time_data: continue
        gr = calc_gr(acpl)
        try:
            clocks = json.loads(clocks_raw)
            if len(clocks) >= 60:
                player_is_white = _is_player_white(white)
                clock_at_30 = clocks[58 if player_is_white else 59]
                if clock_at_30 < 10.0:
                    time_data[rng]["fast_n"] += 1; time_data[rng]["fast_gr"] += gr
                else:
                    time_data[rng]["slow_n"] += 1; time_data[rng]["slow_gr"] += gr
        except Exception: pass
    with report_context("timeout_vs_rating") as w:
        w.w_separator(title="ЦЕНА ЦЕЙТНОТА")
        for rng in ["< 2500", "2500-2599", "2600-2699", "2700+"]:
            d = time_data[rng]
            if d["slow_n"] == 0 and d["fast_n"] == 0: continue
            w.w(f"🎯 {rng}:")
            if d["slow_n"]: w.w(f"  > 10 сек: {d['slow_n']:>3} | GameR: {d['slow_gr']/d['slow_n']:.0f}")
            if d["fast_n"]: w.w(f"  < 10 сек: {d['fast_n']:>3} | GameR: {d['fast_gr']/d['fast_n']:.0f}")
            w.w()
    conn.close()