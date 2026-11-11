# ============================================================
# 04_export_csv.py — v19.5 (avg_time через clocks, win_rate числом)
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


# ---------- ОСТАЛЬНЫЕ ЭКСПОРТЁРЫ (без изменений) ----------
def export_portrait(conn, days, out_dir):
    path = os.path.join(out_dir, "portrait_summary.csv")
    cur = conn.cursor()
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["metric", "value", "detail"])
        cur.execute("""
            SELECT COUNT(*), SUM(won), SUM(draw), ROUND(AVG(opp_rating)), ROUND(AVG(my_rating)),
                   ROUND(AVG(acpl), 1), ROUND(AVG(accuracy), 1),
                   ROUND(AVG(acpl_opponent_total), 1), ROUND(AVG(accuracy_opponent), 1),
                   SUM(opp_blunders_total)
            FROM games WHERE end_time >= ? AND is_lag=0 AND is_cheater=0
        """, (cutoff(days),))
        row = cur.fetchone()
        n = row[0] or 1
        w.writerow(["total_games", row[0], ""])
        w.writerow(["wins", row[1] or 0, f"{(row[1] or 0)/n*100:.1f}%"])
        w.writerow(["draws", row[2] or 0, f"{(row[2] or 0)/n*100:.1f}%"])
        w.writerow(["avg_opp_rating", row[3], ""])
        w.writerow(["avg_my_rating", row[4], ""])
        w.writerow(["avg_acpl", row[5], ""])
        w.writerow(["avg_accuracy", row[6], ""])
        wins, draws, avg_opp = row[1] or 0, row[2] or 0, row[3] or 0
        score = (wins + 0.5 * draws) / n
        perf = avg_opp + (score - 0.5) * 800
        w.writerow(["performance_rating", round(perf), ""])
        
        cur.execute("""
            SELECT COUNT(*) FROM games
            WHERE end_time >= ? AND is_lag=0 AND is_cheater=0
              AND max_eval_advantage >= 300 AND won=0 AND draw=0
        """, (cutoff(days),))
        lost_won = cur.fetchone()[0] or 0
        w.writerow(["lost_from_winning", lost_won, f"{lost_won/n*100:.1f}%"])
        
        cur.execute("""
            SELECT SUM(CASE WHEN won=1 AND reason='просрочка' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN won=0 AND reason='просрочка' THEN 1 ELSE 0 END)
            FROM games WHERE end_time >= ? AND is_lag=0 AND is_cheater=0
        """, (cutoff(days),))
        cw, cl = cur.fetchone()
        w.writerow(["flags_won_by_time", cw or 0, ""])
        w.writerow(["flags_lost_by_time", cl or 0, ""])
        
        cur.execute("""
            SELECT ROUND(AVG(momentum_after_blunder), 1)
            FROM games WHERE end_time >= ? AND is_lag=0 AND is_cheater=0
              AND momentum_after_blunder > 0
        """, (cutoff(days),))
        mom = cur.fetchone()[0]
        w.writerow(["avg_momentum_after_blunder", mom or 0, "средний ACPL на 5 ходах после зевка"])
    print(f"  {path}")


def export_coach_insights(conn, days, out_dir):
    path = os.path.join(out_dir, "coach_insights.txt")
    cur = conn.cursor()
    with open(path, "w", encoding="utf-8") as f:
        f.write("🏆 ПЛАН ТРЕНЕРА НА СЕГОДНЯ\n" + "=" * 40 + "\n\n")
        cur.execute("""
            SELECT ROUND(AVG(acpl_opening), 1), ROUND(AVG(acpl_middlegame), 1),
                   ROUND(AVG(acpl_endgame), 1)
            FROM games WHERE end_time >= ? AND is_lag=0 AND is_cheater=0
        """, (cutoff(days),))
        op, mid, end = cur.fetchone()
        f.write("📊 ТВОЙ ACPL ПО ФАЗАМ:\n")
        f.write(f"   Дебют: {op or 0} CP\n")
        f.write(f"   Миттельшпиль: {mid or 0} CP\n")
        f.write(f"   Эндшпиль: {end or 0} CP\n\n")
    print(f"  {path}")


def export_acpl_by_phase(conn, days, out_dir):
    path = os.path.join(out_dir, "acpl_by_phase.csv")
    cur = conn.cursor()
    cur.execute("""
        SELECT ROUND(AVG(acpl_opening), 1), ROUND(AVG(acpl_middlegame), 1),
               ROUND(AVG(acpl_endgame), 1), COUNT(*)
        FROM games WHERE end_time >= ? AND is_lag=0 AND is_cheater=0
    """, (cutoff(days),))
    row = cur.fetchone()
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["phase", "acpl", "games"])
        w.writerow(["opening (1-10)", row[0] or 0, row[3] or 0])
        w.writerow(["middlegame (11-30)", row[1] or 0, row[3] or 0])
        w.writerow(["endgame (31+)", row[2] or 0, row[3] or 0])
    print(f"  {path}")


def export_acpl_phase_weekly(conn, days, out_dir):
    path = os.path.join(out_dir, "acpl_by_phase_weekly.csv")
    cur = conn.cursor()
    cur.execute("""
        SELECT strftime('%Y-%W', datetime(end_time, 'unixepoch')) AS week,
               COUNT(*),
               ROUND(AVG(acpl_opening), 1), ROUND(AVG(acpl_middlegame), 1),
               ROUND(AVG(acpl_endgame), 1)
        FROM games WHERE end_time >= ? AND is_lag=0 AND is_cheater=0
        GROUP BY week ORDER BY week
    """, (cutoff(days),))
    rows = cur.fetchall()
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["week", "games", "acpl_opening", "acpl_middlegame", "acpl_endgame"])
        for r in rows:
            w.writerow(r)
    print(f"  {path}")


def export_patterns(conn, days, out_dir):
    path = os.path.join(out_dir, "blunders_patterns.csv")
    cur = conn.cursor()
    cur.execute("""
        SELECT
            CASE WHEN b.move_num <= 10 THEN 'opening'
                 WHEN b.move_num <= 30 THEN 'middlegame'
                 ELSE 'endgame' END AS phase,
            CASE WHEN ABS(b.eval_before) < 100 THEN 'equal'
                 WHEN (b.eval_before > 0 AND b.player_is_white=1)
                   OR (b.eval_before < 0 AND b.player_is_white=0) THEN 'winning'
                 ELSE 'losing' END AS situation,
            b.pattern_tag, COUNT(*), ROUND(AVG(b.loss_cp)), ROUND(AVG(b.eval_swing), 1)
        FROM blunders b JOIN games g ON g.url = b.game_url
        WHERE g.end_time >= ? AND g.is_lag=0 AND g.is_cheater=0
          AND b.is_berserk=0 AND b.is_instant=0 AND b.is_my_blunder=1
        GROUP BY phase, situation, b.pattern_tag ORDER BY COUNT(*) DESC
    """, (cutoff(days),))
    rows = cur.fetchall()
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["phase", "situation", "pattern_tag", "count", "avg_loss_cp", "avg_eval_swing"])
        for r in rows:
            w.writerow(r)
    print(f"  {path}")


def export_openings(conn, days, out_dir):
    path = os.path.join(out_dir, "openings_stats.csv")
    cur = conn.cursor()
    cur.execute("""
        SELECT opening, eco, COUNT(*) AS games, SUM(won) AS wins,
               ROUND(AVG(acpl), 1) AS acpl, ROUND(AVG(accuracy), 1) AS accuracy,
               ROUND(AVG(acpl_opponent_total), 1) AS opp_acpl,
               ROUND(AVG(eval_after_opening), 2) AS eval_op
        FROM games WHERE end_time >= ? AND is_lag=0 AND is_cheater=0
        GROUP BY opening, eco HAVING games >= 2 ORDER BY games DESC
    """, (cutoff(days),))
    rows = cur.fetchall()
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["opening", "eco", "games", "wins", "win_rate", "acpl", "accuracy", "opp_acpl", "eval_after_opening"])
        for r in rows:
            games = r[2] or 1
            w.writerow([r[0], r[1], r[2], r[3] or 0, f"{(r[3] or 0)/games*100:.1f}%", r[4], r[5], r[6], r[7]])
    print(f"  {path}")


def export_opening_tree(conn, days, out_dir):
    path = os.path.join(out_dir, "opening_tree.csv")
    cur = conn.cursor()
    cur.execute("""
        SELECT opening_line, COUNT(*), SUM(won), ROUND(100.0*SUM(won)/COUNT(*), 1)
        FROM games WHERE end_time >= ? AND is_lag=0 AND is_cheater=0 AND opening_line != ''
        GROUP BY opening_line HAVING COUNT(*) >= 3 ORDER BY COUNT(*) DESC
    """, (cutoff(days),))
    rows = cur.fetchall()
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["opening_line_10_moves", "games", "wins", "win_rate"])
        for r in rows:
            w.writerow(r)
    print(f"  {path}")


def export_time_of_day(conn, days, out_dir):
    path = os.path.join(out_dir, "time_of_day_stats.csv")
    cur = conn.cursor()
    cur.execute("""
        SELECT strftime('%H', datetime(end_time, 'unixepoch', '+3 hours')) AS hour,
               COUNT(*), SUM(won), ROUND(100.0*SUM(won)/COUNT(*), 1),
               ROUND(AVG(acpl), 1), ROUND(AVG(accuracy), 1)
        FROM games WHERE end_time >= ? AND is_lag=0 AND is_cheater=0
        GROUP BY hour HAVING COUNT(*) >= 5 ORDER BY hour
    """, (cutoff(days),))
    rows = cur.fetchall()
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["hour", "games", "wins", "win_rate", "acpl", "accuracy"])
        for r in rows:
            w.writerow(r)
    print(f"  {path}")


def export_timeouts(conn, days, out_dir):
    path = os.path.join(out_dir, "timeout_stats.csv")
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*), ROUND(AVG(timeout_at_move), 0), ROUND(AVG(timeout_with_clock), 1)
        FROM games WHERE end_time >= ? AND is_lag=0 AND is_cheater=0
          AND timeout_at_move IS NOT NULL
    """, (cutoff(days),))
    r = cur.fetchone()
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["metric", "value"])
        w.writerow(["total_timeouts", r[0] or 0])
        w.writerow(["avg_move_num", r[1] or 0])
        w.writerow(["avg_remaining_sec", r[2] or 0])
    print(f"  {path}")


def export_timeout_by_move(conn, days, out_dir):
    path = os.path.join(out_dir, "timeout_by_move.csv")
    cur = conn.cursor()
    cur.execute("""
        SELECT timeout_at_move AS move, COUNT(*) as cnt,
               ROUND(AVG(timeout_with_clock), 1) as avg_left
        FROM games
        WHERE end_time >= ? AND is_lag=0 AND is_cheater=0 AND timeout_at_move IS NOT NULL
        GROUP BY timeout_at_move ORDER BY timeout_at_move
    """, (cutoff(days),))
    rows = cur.fetchall()
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["move_num", "timeouts", "avg_remaining_sec"])
        for r in rows:
            w.writerow(r)
    print(f"  {path}")


def export_timing_patterns(conn, days, out_dir):
    path = os.path.join(out_dir, "timing_patterns.csv")
    cur = conn.cursor()
    cur.execute("""
        SELECT b.move_num, COUNT(*) as blunders,
               ROUND(AVG(b.loss_cp)) as avg_loss,
               ROUND(AVG(b.time_spent), 1) as avg_time_spent
        FROM blunders b JOIN games g ON g.url = b.game_url
        WHERE g.end_time >= ? AND g.is_lag=0 AND g.is_cheater=0
          AND b.is_berserk=0 AND b.is_instant=0 AND b.is_my_blunder=1
        GROUP BY b.move_num ORDER BY b.move_num
    """, (cutoff(days),))
    rows = cur.fetchall()
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["move_num", "blunders", "avg_loss_cp", "avg_time_spent_sec"])
        for r in rows:
            w.writerow(r)
    print(f"  {path}")


def export_opponent_style(conn, days, out_dir):
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


# ---------- ГЛАВНОЕ: write_index_row (v19.5) ----------
def _compute_avg_time_for_window(cur, days):
    """
    Среднее время на ход через clocks (все ходы), а не blunders.time_spent.
    Использует _compute_avg_time из speed_rating.
    """
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
    return sum(times) / len(times) if times else 0


def write_index_row(conn, days, date_str):
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

    # P10 / P50 / P90
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

    # Time-метрики
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

    # ИСПРАВЛЕНО: avg_time через clocks (все ходы), а не blunders.time_spent
    avg_time = _compute_avg_time_for_window(cur, days)

    # Топ-3 / худшие 3 дебюта
    cur.execute("""
        SELECT opening, COUNT(*) AS g, SUM(won) AS w
        FROM games WHERE end_time >= ? AND is_lag=0 AND is_cheater=0
          AND opening IS NOT NULL AND opening != ''
        GROUP BY opening HAVING g >= 5
        ORDER BY (CAST(w AS REAL) / g) DESC LIMIT 3
    """, (cutoff(days),))
    top_openings = cur.fetchall()

    cur.execute("""
        SELECT opening, COUNT(*) AS g, SUM(won) AS w
        FROM games WHERE end_time >= ? AND is_lag=0 AND is_cheater=0
          AND opening IS NOT NULL AND opening != ''
        GROUP BY opening HAVING g >= 5
        ORDER BY (CAST(w AS REAL) / g) ASC LIMIT 3
    """, (cutoff(days),))
    worst_openings = cur.fetchall()

    def fmt_openings(rows):
        return " | ".join(f"{r[0][:40]} ({r[1]}p, {r[2]/r[1]*100:.0f}%)" for r in rows)

    header = [
        "date", "days", "games", "wins", "win_rate", "draws", "avg_opp", "avg_my",
        "acpl", "accuracy", "acpl_berserk", "acpl_p10", "acpl_p50", "acpl_p90",
        "avg_time", "timeout_rate", "flag_won_rate",
        "performance_rating", "opp_blunders_total", "top_openings", "worst_openings",
    ]
    # ИСПРАВЛЕНО: win_rate числом (float), а не строкой "48.0%"
    new_row = [
        date_str, days, n, wins, round(wins/n*100, 1), draws, row[3], row[4], row[5],
        row[6], row[7], round(p10, 1), round(p50, 1), round(p90, 1),
        round(avg_time, 2), round(timeout_rate, 1), round(flag_won_rate, 1),
        round(perf), row[8] or 0,
        fmt_openings(top_openings), fmt_openings(worst_openings),
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
    print(" 04_export_csv.py — v19.5 (avg_time через clocks, win_rate числом)")
    print("=" * 60)

    if not os.path.exists(DB_FILE):
        print(f"❌ Не найдена {DB_FILE}.")
        return

    date_str = args.date or datetime.now().strftime("%Y-%m-%d")
    dated_dir, latest_dir = ensure_export_dirs(date_str)
    conn = sqlite3.connect(DB_FILE)
    print(f"📤 Экспорт за {args.days} дней → {dated_dir}/\n")

    export_portrait(conn, args.days, dated_dir)
    export_coach_insights(conn, args.days, dated_dir)
    export_acpl_by_phase(conn, args.days, dated_dir)
    export_acpl_phase_weekly(conn, args.days, dated_dir)
    export_patterns(conn, args.days, dated_dir)
    export_openings(conn, args.days, dated_dir)
    export_opening_tree(conn, args.days, dated_dir)
    export_time_of_day(conn, args.days, dated_dir)
    export_timeouts(conn, args.days, dated_dir)
    export_timeout_by_move(conn, args.days, dated_dir)
    export_timing_patterns(conn, args.days, dated_dir)
    export_opponent_style(conn, args.days, dated_dir)

    for fname in os.listdir(dated_dir):
        if fname.endswith(".csv") or fname.endswith(".txt"):
            shutil.copy2(os.path.join(dated_dir, fname), os.path.join(latest_dir, fname))

    write_index_row(conn, args.days, date_str)
    conn.close()
    print(f"\n✅ Готово. Срез сохранён в {dated_dir}/")


if __name__ == "__main__":
    main()