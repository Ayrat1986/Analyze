# ============================================================
# analysis/dashboard_helpers.py — v27.2
# FIX: Поддержка Turso для главной страницы Streamlit Cloud.
# FIX: Динамический расчёт 4-факторного CombR v2 без хардкода.
# FIX: Сохранены все метрики 00_INDEX.txt и функции трендов.
# ============================================================
import json
import re
import sqlite3
import statistics
import _common
from _chess_utils import parse_time_spent
from analysis.common import (
    PLAYER,
    REPORTS_DIR,
    WINDOW_LABELS,
    WINDOWS,
    window_cutoff_ts,
    window_label,
)
from core.метрики import (
    aggression_rating,
    combined_rating,
    combined_rating_v2,
    game_rating,
    perf_rating,
    speed_rating,
    state_rating,
)

# Реэкспорт функций для 13_dashboard_final.py и web_dashboard/app.py
from analysis.dashboard_aggression import (  # noqa: F401
    aggression_by_moves,
    aggression_by_opening,
    aggression_by_phase,
    aggression_by_rating,
)
from analysis.dashboard_trends import (  # noqa: F401
    get_blunder_map_data,
    get_cascade_trend,
    get_daily_metrics_trend,
    get_hourly_rhythm,
)

try:
    from web_dashboard.utils.db import get_connection
    HAS_TURSO = True
except ImportError:
    HAS_TURSO = False

DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")

_SAN_TOKEN_RE = re.compile(
    r"^(?:O-O-O|O-O|[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?[+#]?)$"
)


def _get_conn():
    """Универсальное подключение: Turso (в облаке/при наличии secrets) или локальный SQLite."""
    if HAS_TURSO:
        try:
            return get_connection()
        except Exception:
            pass
    return sqlite3.connect(DB_FILE)


def get_blade_state(combr: float) -> str:
    if combr >= 2650:
        return "🗡️ Острый Клинок"
    if combr >= 2550:
        return "⚔️ Боевой Клинок"
    if combr >= 2450:
        return "🪵 Тупеющий Клинок"
    if combr >= 2300:
        return "🧱 Тупой Клинок"
    return "💀 Сломанный Клинок"


def _percentile(sorted_vals: list, q: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    pos = (len(sorted_vals) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = pos - lo
    return float(sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac)


def _calc_aggr_score_from_pgn(cur, cutoff_ts: int) -> float:
    """
    Динамически считает индекс агрессии (шкала ~0..10, база 7.8 ≈ 28% взятий и шахов)
    по ходам игрока в PGN за выбранное окно.
    """
    try:
        cur.execute(
            """
            SELECT pgn, white FROM games
            WHERE is_lag=0 AND is_cheater=0 AND end_time >= ?
              AND pgn IS NOT NULL AND pgn != ''
            """,
            (cutoff_ts,),
        )
        total_moves = 0
        aggr_moves = 0
        for pgn, white in cur.fetchall():
            is_white = (white == PLAYER)
            body = re.sub(r"\[[^\]]*\]", " ", pgn)
            body = re.sub(r"\{[^}]*\}", " ", body)
            tokens = [t for t in body.split() if _SAN_TOKEN_RE.match(t)]
            my_moves = tokens[0::2] if is_white else tokens[1::2]
            total_moves += len(my_moves)
            aggr_moves += sum(1 for m in my_moves if ("x" in m or "+" in m or "#" in m))

        if total_moves > 0:
            aggr_pct = (aggr_moves / total_moves) * 100.0
            return round(aggr_pct * (7.8 / 28.0), 2)
    except Exception:
        pass
    return 7.8


def key_numbers() -> dict:
    conn = _get_conn()
    cur = conn.cursor()
    ts = window_cutoff_ts(90)
    result = {}

    cur.execute(
        """
        SELECT COUNT(*), AVG(acpl), AVG(momentum_after_blunder)
        FROM games WHERE is_lag=0 AND is_cheater=0 AND end_time >= ?
        """,
        (ts,),
    )
    n, acpl, mom = cur.fetchone()
    n, acpl = n or 0, acpl or 0.0

    cur.execute(
        """
        SELECT acpl FROM games
        WHERE is_lag=0 AND is_cheater=0 AND end_time >= ? AND acpl > 0
        ORDER BY acpl ASC
        """,
        (ts,),
    )
    acpl_vals = [float(r[0]) for r in cur.fetchall() if r[0] is not None]
    p50_acpl = _percentile(acpl_vals, 0.50)
    p10_acpl = _percentile(acpl_vals, 0.10)
    p90_acpl = _percentile(acpl_vals, 0.90)
    std_acpl = statistics.pstdev(acpl_vals) if len(acpl_vals) > 1 else 0.0

    result["Партий:"] = n
    result["ACPL:"] = f"{acpl:.0f} (мед: {p50_acpl:.0f})" if acpl_vals else f"{acpl:.1f}"
    result["Моментум после зевка:"] = f"{mom:.0f} CP" if mom is not None else "нет данных (N=0)"

    cur.execute(
        """
        SELECT SUM(won), SUM(draw), AVG(opp_rating), AVG(my_rating)
        FROM games WHERE is_lag=0 AND is_cheater=0 AND end_time >= ?
        """,
        (ts,),
    )
    wins, draws, avg_opp, avg_my = cur.fetchone()
    wins, draws = wins or 0, draws or 0

    if n:
        result["Winrate:"] = f"{(wins + 0.5 * draws) / n * 100:.1f}%"
        if avg_opp:
            result["Perf (90д):"] = round(perf_rating(avg_opp, wins, draws, n))
    if avg_my:
        result["Средний рейтинг (90д):"] = round(avg_my)

    cur.execute(
        """
        SELECT my_rating FROM games
        WHERE is_lag=0 AND is_cheater=0 AND my_rating > 0
        ORDER BY end_time DESC LIMIT 1
        """
    )
    last_row = cur.fetchone()
    if last_row and last_row[0]:
        result["Последний рейтинг:"] = round(last_row[0])

    try:
        cur.execute(
            """
            SELECT COUNT(*) FROM games
            WHERE is_lag=0 AND is_cheater=0 AND end_time >= ?
              AND won=0 AND draw=0 AND reason = 'просрочка'
            """,
            (ts,),
        )
        n_timeout = cur.fetchone()[0] or 0
        if n:
            result["Просрочки (90д):"] = f"{n_timeout} ({n_timeout / n * 100:.1f}%)"
    except Exception:
        pass

    if acpl_vals:
        result["ACPL P10 (лучшие 10%):"] = f"{p10_acpl:.1f} (GameR {round(game_rating(p10_acpl))})"
        result["ACPL P90 (худшие 10%):"] = f"{p90_acpl:.1f} (GameR {round(game_rating(p90_acpl))})"
        result["StdDev ACPL:"] = f"{std_acpl:.1f}"

    cur.execute(
        """
        SELECT clocks, white FROM games
        WHERE is_lag=0 AND is_cheater=0 AND end_time >= ? AND clocks IS NOT NULL
        """,
        (ts,),
    )
    times = []
    for clocks_raw, white in cur.fetchall():
        try:
            clocks = json.loads(clocks_raw)
            t = parse_time_spent(clocks, white == PLAYER)
            if t:
                times.extend(t)
        except Exception:
            pass
    avg_t = statistics.mean(times) if times else 0.0

    aggr_score = _calc_aggr_score_from_pgn(cur, ts)

    conv_pct = 80.0
    try:
        cur.execute(
            """
            SELECT COUNT(*) FROM games
            WHERE is_lag=0 AND is_cheater=0 AND end_time >= ? AND max_eval_advantage >= 300
            """,
            (ts,),
        )
        total_adv = cur.fetchone()[0] or 0
        if total_adv > 0:
            cur.execute(
                """
                SELECT COUNT(*) FROM games
                WHERE is_lag=0 AND is_cheater=0 AND end_time >= ?
                  AND max_eval_advantage >= 300 AND won=0 AND draw=0
                """,
                (ts,),
            )
            sliv = cur.fetchone()[0] or 0
            conv_pct = ((total_adv - sliv) / total_adv) * 100.0
    except Exception:
        pass

    cascade_pct = 50.0
    try:
        cur.execute(
            """
            SELECT COUNT(DISTINCT b.game_url)
            FROM blunders b JOIN games g ON g.url = b.game_url
            WHERE g.is_lag=0 AND g.is_cheater=0 AND g.end_time >= ?
              AND b.is_my_blunder=1 AND b.is_berserk=0
            """,
            (ts,),
        )
        total_games_blunder = cur.fetchone()[0] or 0
        if total_games_blunder > 0:
            cur.execute(
                """
                SELECT COUNT(DISTINCT game_url) FROM (
                    SELECT b.game_url AS game_url, b.move_num AS move_num,
                           LAG(b.move_num) OVER(PARTITION BY b.game_url ORDER BY b.move_num) AS prev_move
                    FROM blunders b JOIN games g ON g.url = b.game_url
                    WHERE g.is_lag=0 AND g.is_cheater=0 AND g.end_time >= ?
                      AND b.is_my_blunder=1 AND b.is_berserk=0
                ) WHERE move_num - prev_move <= 5
                """,
                (ts,),
            )
            cascade_games = cur.fetchone()[0] or 0
            cascade_pct = (cascade_games / total_games_blunder) * 100.0
    except Exception:
        pass

    g_r = game_rating(acpl)
    s_r = speed_rating(avg_t)
    a_r = aggression_rating(aggr_score)
    st_r = state_rating(conv_pct, cascade_pct)

    combr_v2 = combined_rating_v2(g_r, s_r, a_r, st_r)
    blade = get_blade_state(combr_v2)

    result["Состояние:"] = blade
    result["CombR v2:"] = round(combr_v2)
    result["  (Мышление):"] = round(g_r)
    result["  (Интуиция):"] = round(s_r)
    result["  (Ощущения):"] = round(a_r)
    result["  (Чувства):"] = round(st_r)

    conn.close()
    return result


def full_dynamics() -> list:
    conn = _get_conn()
    cur = conn.cursor()
    result = []
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
            "acpl": round(avg_acpl, 1),
        })
    conn.close()
    return result


def top_actions() -> list:
    return [
        "При +3.0 — держи ритм, не ускоряйся, смотри на часы  → 02_middlegame.txt",
        "Пауза 3 сек после первого зевка                      → 04_psych_focus.txt",
        "На ходах 10-15 — замедлись в 2 раза, проверь угрозы  → 04_psych_focus.txt",
        "Против aggressive — сушить позицию (менять фигуры)   → 07_opponents.txt",
    ]


DASHBOARD_FILES = [
    ("01_openings.txt", "Дебюты: planner, репертуар, шпаргалки"),
    ("02_middlegame.txt", "Миттельшпиль: ACPL, план, тактика"),
    ("03_endgame.txt", "Эндшпиль: техника, флаги, берсерк"),
    ("04_psych_focus.txt", "Зевки: анатомия, первый, missed"),
    ("05_psych_state.txt", "Время, режим, тильт, выносливость"),
    ("06_psych_rating.txt", "Рейтинг, прогресс, потенциал"),
    ("07_opponents.txt", "Соперники: стиль, crushed_by, deep"),
    ("08_coach.txt", "Тренер: совет дня, план, колода"),
]