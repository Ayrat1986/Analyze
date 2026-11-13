# ============================================================
# analysis/dashboard_helpers.py — v25.1
# FIX: top3_weaknesses парсит новый формат cascade_tilt.txt (% партий).
# FIX: убрана ссылка на удалённые отчеты в DASHBOARD_FILES.
# ============================================================
import os
import json
import statistics
import re
import sqlite3
from datetime import datetime, timezone, timedelta

from analysis.common import _conn, PLAYER, REPORTS_DIR, WINDOWS, WINDOW_LABELS, window_cutoff_ts
from core.метрики import game_rating, speed_rating, combined_rating

from analysis.dashboard_aggression import (
    aggression_by_rating, aggression_by_opening, aggression_by_phase, aggression_by_moves
)
from analysis.dashboard_trends import (
    get_daily_metrics_trend, get_hourly_rhythm, get_cascade_trend, get_blunder_map_data
)

DB_FILE = str(os.path.join(os.path.dirname(__file__), "..", "..", "data", "chess.db"))


def key_numbers():
    conn = _conn(); cur = conn.cursor(); ts = window_cutoff_ts(90); result = {}
    cur.execute(
        "SELECT COUNT(*), ROUND(AVG(acpl), 1), ROUND(AVG(acpl_middlegame), 1), "
        "ROUND(AVG(momentum_after_blunder), 1) "
        "FROM games WHERE is_lag=0 AND is_cheater=0 AND end_time >= ?", (ts,))
    n, acpl, acpl_mid, mom = cur.fetchone()
    n = n or 0; acpl = acpl or 0; acpl_mid = acpl_mid or 0; mom = mom or 0
    result["Партий:"] = n
    result["ACPL:"] = f"{acpl:.0f} (мит: {acpl_mid:.0f})"
    result["Моментум после зевка:"] = f"{mom:.0f} CP"

    cur.execute(
        "SELECT SUM(won), SUM(draw), ROUND(AVG(opp_rating)), ROUND(AVG(my_rating)) "
        "FROM games WHERE is_lag=0 AND is_cheater=0 AND end_time >= ?", (ts,))
    wins, draws, avg_opp, avg_my = cur.fetchone()
    wins = wins or 0; draws = draws or 0; avg_opp = avg_opp or 0; avg_my = avg_my or 0
    if n:
        result["Winrate:"] = f"{(wins + 0.5 * draws) / n * 100:.1f}%"
    if avg_my:
        result["Средний рейтинг (90д):"] = round(avg_my)

    cur.execute(
        "SELECT my_rating FROM games WHERE is_lag=0 AND is_cheater=0 AND end_time >= ? "
        "AND my_rating > 0 ORDER BY end_time DESC LIMIT 1", (ts,))
    last = cur.fetchone()
    if last:
        result["Последний рейтинг:"] = last[0]

    cur.execute(
        "SELECT SUM(CASE WHEN reason='просрочка' AND won=0 THEN 1 ELSE 0 END), COUNT(*) "
        "FROM games WHERE is_lag=0 AND is_cheater=0 AND end_time >= ?", (ts,))
    lost_to, total_g = cur.fetchone()
    lost_to = lost_to or 0; total_g = total_g or 1
    result["Просрочки (90д):"] = f"{lost_to} ({lost_to/total_g*100:.1f}%)"

    if avg_opp and n:
        result["Perf (90д):"] = round(avg_opp + ((wins + 0.5 * draws) / n - 0.5) * 800)

    cur.execute(
        "SELECT acpl FROM games WHERE is_lag=0 AND is_cheater=0 AND end_time >= ? AND acpl > 0",
        (ts,))
    vals = sorted([r[0] for r in cur.fetchall()])
    if len(vals) >= 10:
        p10 = vals[int(len(vals) * 0.1)]
        p90 = vals[int(len(vals) * 0.9)]
        stddev = statistics.stdev(vals)
        result["ACPL P10 (потолок):"] = f"{p10:.1f} (GameR {game_rating(p10):.0f})"
        result["ACPL P90 (дно):"] = f"{p90:.1f} (GameR {game_rating(p90):.0f})"
        result["StdDev ACPL:"] = f"{stddev:.1f}"
    else:
        result["ACPL P10 (потолок):"] = "—"
        result["ACPL P90 (дно):"] = "—"
        result["StdDev ACPL:"] = "—"

    conn.close()
    return result


def full_dynamics():
    """
    v25.0 (§17): SpeedR и CombR — только из core.метрики.
    """
    conn = _conn(); cur = conn.cursor()
    result = []
    for days in WINDOWS:
        cutoff = window_cutoff_ts(days)
        cur.execute(
            "SELECT MAX(my_rating), AVG(my_rating), MIN(my_rating), COUNT(*), "
            "AVG(acpl), AVG(opp_rating), SUM(won), SUM(draw) "
            "FROM games WHERE is_lag=0 AND is_cheater=0 AND my_rating > 0 AND end_time >= ?",
            (cutoff,))
        peak, home, bottom, n, avg_acpl, avg_opp, wins, draws = cur.fetchone()
        peak = peak or 0
        home = round(home) if home else 0
        bottom = bottom or 0
        n = n or 0
        avg_acpl = avg_acpl or 0
        avg_opp = round(avg_opp) if avg_opp else 0
        wins = wins or 0
        draws = draws or 0
        score = (wins + 0.5 * draws) / n if n else 0
        perf = avg_opp + (score - 0.5) * 800 if avg_opp else 0

        cur.execute(
            "SELECT acpl FROM games WHERE is_lag=0 AND is_cheater=0 AND my_rating > 0 "
            "AND end_time >= ? AND acpl > 0", (cutoff,))
        acpl_vals = sorted([r[0] for r in cur.fetchall()])
        if len(acpl_vals) >= 10:
            n_v = len(acpl_vals)
            p10 = acpl_vals[int(n_v * 0.1)]
            p50 = acpl_vals[int(n_v * 0.5)]
            p90 = acpl_vals[int(n_v * 0.9)]
        else:
            p10 = p50 = p90 = 0

        gamr = game_rating(avg_acpl) if avg_acpl else 0

        cur.execute(
            "SELECT clocks, white FROM games WHERE is_lag=0 AND is_cheater=0 "
            "AND my_rating > 0 AND end_time >= ? AND acpl > 0 "
            "AND clocks IS NOT NULL AND clocks != '[]'", (cutoff,))
        all_avg_times = []
        from _chess_utils import parse_time_spent
        for clocks_raw, white in cur.fetchall():
            try:
                clocks = json.loads(clocks_raw)
                if not clocks:
                    continue
            except Exception:
                continue
            player_is_white = (white or "").lower() == PLAYER.lower()
            times = parse_time_spent(clocks, player_is_white)
            if times:
                all_avg_times.append(sum(times) / len(times))
        avg_time = statistics.mean(all_avg_times) if all_avg_times else 0

        speed_r = speed_rating(avg_time)
        comb_r = combined_rating(gamr, speed_r)

        result.append({
            "window": WINDOW_LABELS[days],
            "games": n,
            "peak": peak,
            "home": home,
            "bottom": bottom,
            "win_rate": round(score * 100, 1),
            "avg_opp": avg_opp,
            "gamr": round(gamr),
            "speedr": round(speed_r),
            "combined_r": round(comb_r),
            "avg_time": float(round(avg_time, 2)),
            "perf": round(perf),
            "p10": round(p10),
            "p50": round(p50),
            "p90": round(p90),
            "acpl": round(avg_acpl, 1),
        })
    conn.close()
    return result


def monitoring_snapshot():
    """Достает данные из monitoring_log для отображения тренда."""
    if not os.path.exists(DB_FILE):
        return []
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='monitoring_log'")
    if not cur.fetchone():
        conn.close()
        return []
    cur.execute("SELECT * FROM monitoring_log ORDER BY date DESC LIMIT 90")
    cols = [d[0] for d in cur.description]
    history = [dict(zip(cols, row)) for row in cur.fetchall()]
    conn.close()
    if not history:
        return []
    now = datetime.now(timezone.utc)
    result = []
    for days in [0, 7, 30, 90]:
        target = (now - timedelta(days=days)).strftime("%Y-%m-%d")
        closest = min(history, key=lambda x: abs(
            (datetime.strptime(x['date'], "%Y-%m-%d").replace(tzinfo=timezone.utc)
             - datetime.strptime(target, "%Y-%m-%d").replace(tzinfo=timezone.utc)).days))
        label = "Сегодня" if days == 0 else f"{days} дн."
        result.append({"window": label, "date": closest['date'], **closest})
    return result


def last_session_vs_windows():
    conn = _conn(); cur = conn.cursor()
    cur.execute(
        "SELECT url, end_time, won, draw, acpl, my_rating FROM games "
        "WHERE is_lag=0 AND is_cheater=0 ORDER BY end_time DESC LIMIT 200")
    rows = cur.fetchall()
    if not rows:
        conn.close()
        return []
    session = []
    prev_time = None
    for url, ts, won, draw, acpl, my_rating in rows:
        if prev_time is None:
            session.append({"ts": ts, "won": won, "draw": draw, "acpl": acpl, "my_rating": my_rating})
            prev_time = ts
        elif prev_time - ts <= 1800:
            session.append({"ts": ts, "won": won, "draw": draw, "acpl": acpl, "my_rating": my_rating})
            prev_time = ts
        else:
            break

    def _stats(data):
        if not data:
            return {"games": 0, "win_rate": 0, "acpl": 0, "gamr": 0, "my_rating": 0, "p90": 0}
        n = len(data)
        wins = sum(1 for d in data if d["won"])
        draws = sum(1 for d in data if d["draw"])
        win_rate = (wins + 0.5 * draws) / n * 100
        acpls = sorted([d["acpl"] for d in data if d["acpl"] and d["acpl"] > 0])
        ratings = [d["my_rating"] for d in data if d["my_rating"] and d["my_rating"] > 0]
        avg_acpl = statistics.mean(acpls) if acpls else 0
        avg_rating = statistics.mean(ratings) if ratings else 0
        gamr = game_rating(avg_acpl) if avg_acpl else 0
        p90 = acpls[int(len(acpls) * 0.9)] if len(acpls) >= 10 else 0
        return {"games": n, "win_rate": round(win_rate, 1), "acpl": round(avg_acpl, 1),
                "gamr": round(gamr), "my_rating": round(avg_rating), "p90": round(p90)}

    result = [{"label": "🔥 Последняя сессия", **_stats(session)}]
    for days in [2, 7, 30, 90, 365]:
        cutoff = window_cutoff_ts(days)
        cur.execute(
            "SELECT won, draw, acpl, my_rating FROM games "
            "WHERE is_lag=0 AND is_cheater=0 AND end_time >= ?", (cutoff,))
        data = [{"won": w, "draw": d, "acpl": a, "my_rating": m} for w, d, a, m in cur.fetchall()]
        result.append({"label": WINDOW_LABELS[days], **_stats(data)})
    conn.close()
    return result


# Заглушки для совместимости
def rating_trend():
    return full_dynamics()


def rating_buckets_summary():
    return full_dynamics()


def time_vs_rating():
    return []


def combined_vs_perf():
    return []


def top3_weaknesses():
    candidates = []
    try:
        path = os.path.join(REPORTS_DIR, "time_profile.txt")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            m = re.search(r"Всего просрочек:\s*(\d+)", text)
            if m:
                n_timeouts = int(m.group(1))
                if n_timeouts > 100:
                    candidates.append(("Цейтнот (просрочки)",
                                       f"{n_timeouts} партий ({n_timeouts/2409*100:.0f}%)",
                                       "05_psych_state.txt", n_timeouts))
    except Exception:
        pass
    try:
        path = os.path.join(REPORTS_DIR, "cascade_tilt.txt")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            # §30 FIX: новый формат cascade_tilt (% партий)
            # Ищем строку "Миттельшпиль    ...  ...  73.0%"
            m = re.search(r"Миттельшпиль\s+\d+\s+\d+\s+([\d.]+)%", text)
            if m:
                pct = float(m.group(1))
                if pct > 30:
                    candidates.append(("Каскадный тильт в миттельшпиле",
                                       f"{pct:.1f}% партий", "04_psych_focus.txt", int(pct * 10)))
    except Exception:
        pass
    try:
        path = os.path.join(REPORTS_DIR, "middlegame_summary.txt")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            m = re.search(r"Слито \(поражение\):\s+(\d+)\s+\(([\d.]+)%\)", text)
            if m:
                cnt = int(m.group(1)); pct = float(m.group(2))
                if pct > 30:
                    candidates.append(("Слив перевеса (+3.0)",
                                       f"{pct:.1f}% ({cnt} партий)",
                                       "02_middlegame.txt", cnt))
    except Exception:
        pass
    try:
        path = os.path.join(REPORTS_DIR, "opponent_weakness.txt")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            m = re.search(r"Хуже всего:\s*(\w+)\s*\((\d+)%\)", text)
            if m:
                wr = int(m.group(2))
                if wr < 40:
                    candidates.append((f"Слабость против {m.group(1)}",
                                       f"{wr}% winrate", "07_opponents.txt", (40 - wr) * 10))
    except Exception:
        pass
    try:
        path = os.path.join(REPORTS_DIR, "lag_report.txt")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            m = re.search(r"Партий с лагом:\s*(\d+)\s+\(([\d.]+)%\)", text)
            if m:
                cnt = int(m.group(1)); pct = float(m.group(2))
                if pct > 25:
                    candidates.append(("Лаги (аномалии времени)",
                                       f"{pct:.1f}% ({cnt} партий)",
                                       "05_psych_state.txt", int(pct * 10)))
    except Exception:
        pass
    try:
        path = os.path.join(REPORTS_DIR, "first_blunder_report.txt")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            m = re.search(r"Средний ход 1-го зевка:\s+([\d.]+)", text)
            if m:
                avg_move = float(m.group(1))
                if avg_move <= 20:
                    candidates.append(("Первый зевок на раннем ходу",
                                       f"в среднем на {avg_move:.0f}-м ходу",
                                       "04_psych_focus.txt", int(30 - avg_move) * 10))
    except Exception:
        pass
    candidates.sort(key=lambda x: -x[3])
    if not candidates:
        return [("Нет данных", "—", "00_INDEX.txt")]
    return [(c[0], c[1], c[2]) for c in candidates[:3]]


def get_game_review(url: str):
    """Возвращает полный разбор партии для Streamlit."""
    import json as _json
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT white, black, won, draw, reason, eco, opening, my_rating, opp_rating,
               acpl, acpl_opening, acpl_middlegame, acpl_endgame, accuracy, accuracy_opponent,
               game_length, max_eval_advantage, eval_history, end_time, pgn
        FROM games WHERE url=?
    """, (url,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return None
    (white, black, won, draw, reason, eco, opening, my_rating, opp_rating,
     acpl, acpl_op, acpl_mid, acpl_end, accuracy, accuracy_opp, game_len,
     max_eval_adv, raw_hist, end_time, pgn) = row
    try:
        hist = _json.loads(raw_hist) if raw_hist else []
        hist = [(int(a), float(b)) for a, b in hist if a is not None and b is not None]
    except Exception:
        hist = []
    cur.execute("""
        SELECT move_num, move_uci, loss_cp, eval_before, eval_after, what,
               pattern_tag, time_spent, is_my_blunder
        FROM blunders WHERE game_url = ?
    """, (url,))
    blunders = []
    for b in cur.fetchall():
        blunders.append({
            "move_num": b[0], "move": b[1], "loss": b[2], "eval_before": b[3],
            "eval_after": b[4], "what": b[5], "pattern_tag": b[6],
            "time_spent": b[7], "is_my_blunder": bool(b[8]),
        })
    conn.close()
    return {
        "url": url, "white": white, "black": black, "won": won, "draw": draw,
        "reason": reason, "eco": eco, "opening": opening,
        "my_rating": my_rating, "opp_rating": opp_rating,
        "acpl": acpl, "acpl_op": acpl_op, "acpl_mid": acpl_mid, "acpl_end": acpl_end,
        "accuracy": accuracy, "accuracy_opp": accuracy_opp, "game_len": game_len,
        "max_eval_adv": max_eval_adv, "hist": hist, "blunders": blunders,
        "end_time": end_time, "pgn": pgn,
    }


def get_recent_games(limit=50):
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT url, white, black, won, draw, reason, end_time
        FROM games WHERE is_lag=0 AND is_cheater=0
        ORDER BY end_time DESC LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    conn.close()
    result = []
    for url, white, black, won, draw, reason, end_time in rows:
        res = "Победа" if won else ("Ничья" if draw else "Поражение")
        date = datetime.fromtimestamp(end_time).strftime("%d.%m.%y")
        result.append({"url": url, "label": f"{date} | {white} vs {black} | {res} ({reason})"})
    return result


def top_actions():
    return [
        "При +3.0 — держи ритм, не ускоряйся, смотри на часы  → 02_middlegame.txt",
        "Пауза 3 сек после первого зевка                      → 04_psych_focus.txt",
        "На ходах 10-15 — замедлись в 2 раза, проверь угрозы  → 04_psych_focus.txt",
        "Против aggressive — сушить позицию (менять фигуры)   → 07_opponents.txt",
    ]


# §28 FIX: убраны ссылки на удалённые файлы
DASHBOARD_FILES = [
    ("01_openings.txt", "~80 КБ", "Дебюты: planner, репертуар, шпаргалки"),
    ("02_middlegame.txt", "~35 КБ", "Миттельшпиль: ACPL, план, тактика"),
    ("03_endgame.txt", "~25 КБ", "Эндшпиль: техника, флаги, берсерк"),
    ("04_psych_focus.txt", "~60 КБ", "Зевки: анатомия, первый, missed"),
    ("05_psych_state.txt", "~40 КБ", "Время, режим, тильт, выносливость"),
    ("06_psych_rating.txt", "~20 КБ", "Рейтинг, прогресс, потенциал"),
    ("07_opponents.txt", "~25 КБ", "Соперники: стиль, crushed_by, deep"),
    ("08_coach.txt", "~15 КБ", "Тренер: совет дня, план, колода"),
]