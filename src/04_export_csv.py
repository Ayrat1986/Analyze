# ============================================================
# 04_export_csv.py — v25.0
# §28: удалены 11 мёртвых CSV-экспортов (portrait, coach_insights,
#      acpl_by_phase, acpl_phase_weekly, patterns, openings,
#      opening_tree, time_of_day, timeouts, timeout_by_move,
#      timing_patterns). Оставлены: export_opponent_style,
#      write_index_row (архив).
# ============================================================
import sqlite3
import csv
import argparse
import os
import shutil
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import _common
from core.стили import get_style
from analysis.psych_state.speed_rating import _compute_avg_time
from analysis.psych_state.common import _is_player_white

DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")
OUT_ROOT = os.path.join(str(_common.REPORTS_DIR), "ai_export")
LATEST_DIR = "latest"
PLAYER = _common.CONFIG.get("player", "")


def cutoff(days: int) -> int:
    return int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())


def ensure_export_dirs(date_str: str) -> tuple[str, str]:
    dated_dir = os.path.join(OUT_ROOT, date_str)
    latest_dir = os.path.join(OUT_ROOT, LATEST_DIR)
    os.makedirs(dated_dir, exist_ok=True)
    os.makedirs(latest_dir, exist_ok=True)
    return dated_dir, latest_dir


def export_opponent_style(conn, days, out_dir):
    """Пишет opponent_style.csv — читается в opponents/weakness.py."""
    path = os.path.join(out_dir, "opponent_style.csv")
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(games)")
    cols = {row[1] for row in cur.fetchall()}
    if "pgn" not in cols:
        print(f"  {path} — пропущено (нет pgn в базе)")
        return
    try:
        import chess.pgn, io  # noqa: F401
    except ImportError:
        print(f"  {path} — пропущено (нет python-chess)")
        return
    if not PLAYER:
        print(f"  {path} — пропущено (в config.json нет 'player')")
        return

    cur.execute("""
        SELECT white, black, pgn, won, acpl FROM games
        WHERE end_time >= ? AND is_lag=0 AND is_cheater=0
          AND pgn IS NOT NULL AND pgn != ''
    """, (cutoff(days),))
    rows = cur.fetchall()
    stats = defaultdict(lambda: {"games": 0, "wins": 0, "acpl_sum": 0, "acpl_count": 0})
    for white, black, pgn, won, acpl in rows:
        player_is_white = (white.lower() == PLAYER.lower())
        style = get_style(pgn, player_is_white)
        s = stats[style]
        s["games"] += 1
        if won:
            s["wins"] += 1
        if acpl and acpl > 0:
            s["acpl_sum"] += acpl
            s["acpl_count"] += 1
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["opponent_style", "games", "wins", "win_rate", "my_avg_acpl"])
        for style, s in sorted(stats.items(), key=lambda x: -x[1]["games"]):
            wr = s["wins"] / s["games"] * 100 if s["games"] else 0
            acpl_avg = s["acpl_sum"] / s["acpl_count"] if s["acpl_count"] else 0
            w.writerow([style, s["games"], s["wins"], f"{wr:.1f}%", f"{acpl_avg:.0f}"])
    print(f"  {path}")


def write_index_row(conn, days, date_str):
    """Пишет index.csv — архив истории. Не читается, но полезен."""
    index_path = os.path.join(OUT_ROOT, "index.csv")
    cur = conn.cursor()

    cur.execute("""
        SELECT COUNT(*), SUM(won), SUM(draw), ROUND(AVG(opp_rating)), ROUND(AVG(my_rating)),
               ROUND(AVG(acpl), 1), ROUND(AVG(accuracy), 1), ROUND(AVG(acpl_berserk), 1),
               SUM(opp_blunders_total)
        FROM games WHERE end_time >= ? AND is_lag=0 AND is_cheater=0
    """, (cutoff(days),))
    row = cur.fetchone()
    n = row[0] or 1
    wins = row[1] or 0
    draws = row[2] or 0
    avg_opp = row[3] or 0
    score = (wins + 0.5 * draws) / n
    perf = avg_opp + (score - 0.5) * 800

    cur.execute("""
        SELECT acpl FROM games
        WHERE end_time >= ? AND is_lag=0 AND is_cheater=0 AND acpl > 0
    """, (cutoff(days),))
    vals = sorted([r[0] for r in cur.fetchall()])
    if len(vals) >= 10:
        p10 = vals[int(len(vals) * 0.1)]
        p50 = vals[int(len(vals) * 0.5)]
        p90 = vals[int(len(vals) * 0.9)]
    else:
        p10 = p50 = p90 = 0

    cur.execute("""
        SELECT 
            SUM(CASE WHEN reason='просрочка' AND won=0 THEN 1 ELSE 0 END) as lost_timeouts,
            SUM(CASE WHEN reason='просрочка' AND won=1 THEN 1 ELSE 0 END) as won_flags,
            COUNT(*) as total
        FROM games WHERE end_time >= ? AND is_lag=0 AND is_cheater=0
    """, (cutoff(days),))
    t_row = cur.fetchone()
    lost_timeouts = t_row[0] or 0
    won_flags = t_row[1] or 0
    total_games = t_row[2] or 1
    timeout_rate = lost_timeouts / total_games * 100
    flag_won_rate = (won_flags / wins * 100) if wins else 0

    cur.execute("""
        SELECT clocks, eval_history, white, time_control
        FROM games
        WHERE end_time >= ? AND is_lag=0 AND is_cheater=0
          AND acpl > 0
          AND clocks IS NOT NULL AND clocks != '[]'
          AND eval_history IS NOT NULL AND eval_history != '[]'
    """, (cutoff(days),))
    times = []
    for clocks_raw, evals_raw, white, tc in cur.fetchall():
        player_is_white = _is_player_white(white)
        t = _compute_avg_time(clocks_raw, evals_raw, player_is_white, tc)
        if t:
            times.append(t["avg"])
    avg_time = sum(times) / len(times) if times else 0

    header = [
        "date", "days", "games", "wins", "win_rate", "draws", "avg_opp", "avg_my",
        "acpl", "accuracy", "acpl_berserk", "acpl_p10", "acpl_p50", "acpl_p90",
        "avg_time", "timeout_rate", "flag_won_rate",
        "performance_rating", "opp_blunders_total",
    ]
    new_row = [
        date_str, days, n, wins, round(wins/n*100, 1), draws, row[3], row[4], row[5],
        row[6], row[7], round(p10, 1), round(p50, 1), round(p90, 1),
        round(avg_time, 2), round(timeout_rate, 1), round(flag_won_rate, 1),
        round(perf), row[8] or 0,
    ]

    rows = []
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            rows = list(csv.reader(f))
    if not rows:
        rows = [header]
    else:
        rows = [r for r in rows if not (len(r) > 0 and r[0] == date_str)]

    rows.append(new_row)

    with open(index_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerows(rows)
    print(f"  {index_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--date", type=str, default=None)
    args = parser.parse_args()

    print("=" * 60)
    print(" 04_export_csv.py — v25.0 (только нужное)")
    print("=" * 60)

    if not os.path.exists(DB_FILE):
        print(f"❌ Не найдена {DB_FILE}.")
        return

    date_str = args.date or datetime.now().strftime("%Y-%m-%d")
    dated_dir, latest_dir = ensure_export_dirs(date_str)
    conn = sqlite3.connect(DB_FILE)
    print(f"📤 Экспорт за {args.days} дней → {dated_dir}/\n")

    export_opponent_style(conn, args.days, dated_dir)

    for fname in os.listdir(dated_dir):
        if fname.endswith(".csv") or fname.endswith(".txt"):
            shutil.copy2(os.path.join(dated_dir, fname), os.path.join(latest_dir, fname))

    write_index_row(conn, args.days, date_str)
    conn.close()
    print(f"\n✅ Готово. Срез сохранён в {dated_dir}/")


if __name__ == "__main__":
    main()