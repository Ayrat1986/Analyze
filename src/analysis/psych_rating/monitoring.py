# ============================================================
# analysis/psych_rating/monitoring.py (v25.1)
# FIX: §17 - game_rating импортируется из core.метрики, 
#      а не пишется руками. Защита от avg_time=0.
# ============================================================
import os
import sqlite3
import json
import statistics
import argparse
from datetime import datetime, timezone, timedelta

import _common
from core.метрики import game_rating, speed_rating, combined_rating

DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")
PLAYER = _common.CONFIG.get("player", "")


def _conn():
    return sqlite3.connect(DB_FILE)


def _compute_avg_time(clocks, evals, player_is_white, time_control="60"):
    try:
        clocks = json.loads(clocks) if clocks else []
        evals = json.loads(evals) if evals else []
    except Exception:
        return 1.17
    if not clocks or not evals:
        return 1.17
    base_sec = 60
    if "+" in time_control:
        try:
            base_sec = int(time_control.split("+")[0])
        except Exception:
            pass
    else:
        try:
            base_sec = int(time_control)
        except Exception:
            pass
    times = []
    for i in range(1, len(evals)):
        move_num = evals[i][0]
        ply = (move_num - 1) * 2 + (0 if player_is_white else 1)
        t = None
        if ply == 0:
            t = base_sec - clocks[0]
        elif ply == 1 and len(clocks) > 1:
            t = clocks[0] - clocks[1]
        elif ply >= 2 and ply < len(clocks):
            t = clocks[ply - 2] - clocks[ply]
        if t is not None and 0 < t < 30:
            times.append(t)
    return statistics.mean(times) if times else 1.17


def _get_aggression(evals_raw):
    try:
        hist = json.loads(evals_raw) if evals_raw else []
        if not hist:
            return 0
        agg = 0
        prev = None
        for move, ev in hist:
            if prev is not None and ev - prev >= 50:
                agg += 1
            prev = ev
        return agg
    except Exception:
        return 0


def calc_metrics_for_window(conn, end_date_str, window_days=7):
    """Считает метрики за окно (window_days) ДО конкретной даты (end_date_str)."""
    end_dt = datetime.strptime(end_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end_ts = int(end_dt.timestamp()) + 86400  # Конец дня
    start_ts = end_ts - (window_days * 86400)

    cur = conn.cursor()
    cur.execute("""
        SELECT my_rating, opp_rating, won, draw, acpl,
               white, clocks, eval_history, time_control
        FROM games
        WHERE is_lag=0 AND is_cheater=0
          AND end_time >= ? AND end_time < ?
          AND acpl > 0
    """, (start_ts, end_ts))
    rows = cur.fetchall()
    n = len(rows)
    if n == 0:
        return None

    ratings = [r[0] for r in rows if r[0] > 0]
    opps = [r[1] for r in rows if r[1] > 0]
    acpls = [r[4] for r in rows if r[4] > 0]
    wins = sum(1 for r in rows if r[2])
    draws = sum(1 for r in rows if r[3])

    avg_my = statistics.mean(ratings) if ratings else 0
    avg_opp = statistics.mean(opps) if opps else 0
    avg_acpl = statistics.mean(acpls) if acpls else 0
    score = (wins + 0.5 * draws) / n

    perf = avg_opp + (score - 0.5) * 800 if avg_opp else 0
    
    # §17: Формула из ядра
    gamr = game_rating(avg_acpl)

    all_times, aggs = [], []
    hunter_games = 0

    for r in rows:
        piw = (r[5] or "").lower() == PLAYER.lower()
        t = _compute_avg_time(r[6], r[7], piw, r[8])
        if t:
            all_times.append(t)

        agg = _get_aggression(r[7])
        aggs.append(agg)
        if agg > 8.0:
            hunter_games += 1

    avg_time = statistics.mean(all_times) if all_times else 1.17
    
    # §17: Формулы из ядра + защита от нулевого времени
    speedr = speed_rating(avg_time)
    combr = combined_rating(gamr, speedr)
    delta = gamr - speedr if speedr > 0 else gamr

    stddev = statistics.stdev(acpls) if len(acpls) > 1 else 0
    avg_agg = statistics.mean(aggs) if aggs else 0
    hunter_pct = (hunter_games / n) * 100

    return {
        "games": n, "avg_my": round(avg_my), "avg_opp": round(avg_opp),
        "perf": round(perf), "acpl": round(avg_acpl, 1),
        "gamr": round(gamr), "speedr": round(speedr), "combr": round(combr),
        "delta": round(delta), "stddev": round(stddev, 1),
        "aggression": round(avg_agg, 1), "hunter_pct": round(hunter_pct),
    }


def save_snapshot(conn, date_str, m, notes=""):
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO monitoring_log
        (date, games, avg_my_rating, avg_opp_rating, perf_rating, acpl,
         game_r, speed_r, combined_r, delta, stddev_acpl, aggression, hunter_pct, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        date_str, m["games"], m["avg_my"], m["avg_opp"], m["perf"], m["acpl"],
        m["gamr"], m["speedr"], m["combr"], m["delta"], m["stddev"],
        m["aggression"], m["hunter_pct"], notes
    ))
    conn.commit()


def save_daily_snapshot(notes=""):
    """Вызывается из 10_psych_rating.py. Делает снапшот за сегодня (1 день)."""
    conn = _conn()
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    m = calc_metrics_for_window(conn, today_str, window_days=1)
    if m:
        save_snapshot(conn, today_str, m, notes=notes)
        print(f"✅ Снапшот за {today_str}: {m['games']} игр, CombR {m['combr']}, Δ {m['delta']:+d}")
    else:
        print(f"⚠️ Нет партий за {today_str} — снапшот не создан.")
    conn.close()


def backfill_data(conn, days=90):
    """Система проходит по каждому дню за последние N дней и делает снапшот 7-дневного окна."""
    print(f"🔄 Запуск Backfill за {days} дней (7-дневное скользящее окно)...")
    today = datetime.now(timezone.utc)

    for i in range(days, -1, -1):
        target_dt = today - timedelta(days=i)
        date_str = target_dt.strftime("%Y-%m-%d")

        m = calc_metrics_for_window(conn, date_str, window_days=7)
        if m:
            save_snapshot(conn, date_str, m, notes="Backfill (авто)")
            if i % 10 == 0:
                print(f"  ✅ {date_str}: {m['games']} игр, CombR {m['combr']}, Δ {m['delta']:+d}")
    print("✅ Backfill завершен.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backfill", type=int, default=0, help="Заполнить историю за N дней")
    parser.add_argument("--note", type=str, default="", help="Заметка к сегодняшнему дню")
    args = parser.parse_args()

    conn = _conn()
    if args.backfill > 0:
        backfill_data(conn, args.backfill)
    save_daily_snapshot(notes=args.note)
    conn.close()