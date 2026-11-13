# ============================================================
# analysis/psych_state/time_management.py (v25.0)
# §28: удалён run_time_management (time_report_windows).
# Оставлены: report_time_profile, report_lag_report.
# ============================================================
import os
import json
import statistics
from datetime import datetime, timedelta, timezone

import _common
from _chess_utils import parse_time_spent, rating_cat
from analysis.common import report_context
from .common import _conn, REPORTS_DIR, _is_player_white, _load_clocks_evals
from core.метрики import game_rating as calc_gr


def report_time_profile():
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
        else:
            w.w("  ⚠️ Нет данных о просрочках.")
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


def report_lag_report():
    conn = _conn(); cur = conn.cursor()
    cur.execute("SELECT url, white, clocks FROM games WHERE is_cheater=0 AND clocks IS NOT NULL AND clocks != '[]'")
    rows = cur.fetchall()
    lag_games = total_games = total_anomalies = 0
    anomaly_times = []
    for url, white, clocks_raw in rows:
        clocks, _ = _load_clocks_evals(clocks_raw, None)
        if not clocks:
            continue
        player_is_white = _is_player_white(white)
        times = parse_time_spent(clocks, player_is_white)
        if len(times) < 5:
            continue
        total_games += 1
        median_time = statistics.median(times)
        anomalies = [t for t in times if t > max(5.0, median_time * 3)]
        if anomalies:
            lag_games += 1
            total_anomalies += len(anomalies)
            anomaly_times.extend(anomalies)

    with report_context("lag_report") as w:
        w.w_separator(title="LAG REPORT — аномалии времени")
        w.w(f"Всего партий: {total_games}")
        w.w(f"Партий с лагом: {lag_games} ({lag_games/max(1,total_games)*100:.1f}%)")
        w.w(f"Аномальных ходов: {total_anomalies}")
        if anomaly_times:
            w.w(f"Среднее время аномалии: {statistics.mean(anomaly_times):.1f} сек")
    conn.close()