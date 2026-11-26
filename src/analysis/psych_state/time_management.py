# ============================================================
# analysis/psych_state/time_management.py (v26.2)
# FIX: Объединены time_profile, lag_report, clock_checkpoints.
# ============================================================
import os
import sqlite3
import json
import statistics
from datetime import datetime, timedelta, timezone

import _common
from _chess_utils import parse_time_spent, rating_cat
from analysis.common import report_context
from .common import _conn, REPORTS_DIR, _is_player_white, _load_clocks_evals
from core.метрики import game_rating as calc_gr

DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")


def report_clock_checkpoints(conn, w, days=90):
    """
    Выводит медианное время игрока, соперника и дельту
    на 10, 20, 30, 40, 50, 60 ходах.
    """
    cutoff = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
    cur = conn.cursor()
    cur.execute("""
        SELECT white, clocks FROM games
        WHERE is_lag=0 AND is_cheater=0 AND end_time >= ?
          AND clocks IS NOT NULL AND clocks != '[]'
    """, (cutoff,))

    checkpoints = [10, 20, 30, 40, 50, 60]
    data = {cp: {"my": [], "opp": [], "delta": []} for cp in checkpoints}
    player = _common.CONFIG.get("player", "")

    for white, clocks_raw in cur.fetchall():
        try:
            clocks = json.loads(clocks_raw)
        except Exception:
            continue

        is_white = (white == player)

        for cp in checkpoints:
            idx_white = (cp * 2) - 2
            idx_black = (cp * 2) - 1

            if len(clocks) > max(idx_white, idx_black):
                my_time = clocks[idx_white] if is_white else clocks[idx_black]
                opp_time = clocks[idx_black] if is_white else clocks[idx_white]

                if my_time is not None and opp_time is not None:
                    data[cp]["my"].append(my_time)
                    data[cp]["opp"].append(opp_time)
                    data[cp]["delta"].append(my_time - opp_time)

    w.w_separator(title="⏱️ ВРЕМЯ ПО КОНТРОЛЬНЫМ ТОЧКАМ (Медиана)")
    w.w(f"  {'Ход':<6} {'Мое время':<12} {'Время сопер.':<12} {'Дельта':<10} {'N партий'}")
    w.w("  " + "-" * 55)

    for cp in checkpoints:
        my_vals = data[cp]["my"]
        if not my_vals:
            w.w(f"  {cp:<6} —            —            —          N=0")
            continue

        med_my = statistics.median(my_vals)
        med_opp = statistics.median(data[cp]["opp"])
        med_delta = statistics.median(data[cp]["delta"])

        w.w(f"  {cp:<6} {med_my:>6.1f} сек     {med_opp:>6.1f} сек     {med_delta:>+6.1f} сек   N={len(my_vals)}")

    w.w()
    w.w("  💡 Зеленая зона: к 20-му ходу >40 сек, к 30-му >30 сек.")
    w.w()


def report_time_profile(conn, w, days=90):
    """Профиль времени и просрочек."""
    cur = conn.cursor()
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


def report_lag_report(conn, w):
    cur = conn.cursor()
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

    w.w_separator(title="LAG REPORT — аномалии времени")
    w.w(f"Всего партий: {total_games}")
    w.w(f"Партий с лагом: {lag_games} ({lag_games/max(1,total_games)*100:.1f}%)")
    w.w(f"Аномальных ходов: {total_anomalies}")
    if anomaly_times:
        w.w(f"Среднее время аномалии: {statistics.mean(anomaly_times):.1f} сек")


def run_time_management():
    """Оркестратор отчетов по времени."""
    conn = _conn()
    try:
        with report_context("time_profile") as w:
            report_time_profile(conn, w)
            report_clock_checkpoints(conn, w)
        with report_context("lag_report") as w:
            report_lag_report(conn, w)
    finally:
        conn.close()


if __name__ == "__main__":
    run_time_management()
