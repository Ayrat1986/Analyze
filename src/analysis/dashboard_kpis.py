# ============================================================
# analysis/dashboard_kpis.py — v27.6
# Ключевые метрики за 90 дней и 1 день, расчёт 4 контуров CombR,
# топ-3 слабости и приоритетные действия.
# ============================================================
import json
import statistics
from _chess_utils import parse_time_spent
from analysis.common import PLAYER, window_cutoff_ts
from analysis.dashboard_db import (
    calc_aggr_score_from_pgn,
    get_blade_state,
    get_conn,
    percentile,
)
from core.метрики import (
    CASCADE_BASELINE,
    CONV_BASELINE,
    aggression_rating,
    combined_rating,
    game_rating,
    perf_rating,
    speed_rating,
    state_rating,
)


def calc_window_factors(cur, cutoff_ts: int) -> dict:
    """Единый расчёт всех метрик и 4 контуров CombR для заданного временного окна."""
    cur.execute(
        """
        SELECT COUNT(*), AVG(acpl), AVG(momentum_after_blunder),
               SUM(won), SUM(draw), AVG(opp_rating), AVG(my_rating),
               MAX(my_rating), MIN(my_rating)
        FROM games WHERE is_lag=0 AND is_cheater=0 AND end_time >= ?
        """,
        (cutoff_ts,),
    )
    n, acpl, mom, wins, draws, avg_opp, avg_my, peak_r, bottom_r = cur.fetchone()
    n = n or 0
    acpl = float(acpl) if acpl else 0.0
    wins, draws = wins or 0, draws or 0

    cur.execute(
        """
        SELECT acpl FROM games
        WHERE is_lag=0 AND is_cheater=0 AND end_time >= ? AND acpl > 0
        ORDER BY acpl ASC
        """,
        (cutoff_ts,),
    )
    acpl_vals = [float(r[0]) for r in cur.fetchall() if r[0] is not None]
    p10 = percentile(acpl_vals, 0.10) if acpl_vals else 0.0
    p50 = percentile(acpl_vals, 0.50) if acpl_vals else 0.0
    p90 = percentile(acpl_vals, 0.90) if acpl_vals else 0.0
    std_acpl = statistics.pstdev(acpl_vals) if len(acpl_vals) > 1 else 0.0

    cur.execute(
        """
        SELECT clocks, white FROM games
        WHERE is_lag=0 AND is_cheater=0 AND end_time >= ? AND clocks IS NOT NULL
        """,
        (cutoff_ts,),
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

    aggr_score = calc_aggr_score_from_pgn(cur, cutoff_ts)

    conv_pct = CONV_BASELINE
    try:
        cur.execute(
            """
            SELECT COUNT(*) FROM games
            WHERE is_lag=0 AND is_cheater=0 AND end_time >= ? AND max_eval_advantage >= 300
            """,
            (cutoff_ts,),
        )
        total_adv = cur.fetchone()[0] or 0
        if total_adv > 0:
            cur.execute(
                """
                SELECT COUNT(*) FROM games
                WHERE is_lag=0 AND is_cheater=0 AND end_time >= ?
                  AND max_eval_advantage >= 300 AND won=0 AND draw=0
                """,
                (cutoff_ts,),
            )
            sliv = cur.fetchone()[0] or 0
            conv_pct = ((total_adv - sliv) / total_adv) * 100.0
    except Exception:
        pass

    cascade_pct = CASCADE_BASELINE
    try:
        cur.execute(
            """
            SELECT COUNT(DISTINCT b.game_url)
            FROM blunders b JOIN games g ON g.url = b.game_url
            WHERE g.is_lag=0 AND g.is_cheater=0 AND g.end_time >= ?
              AND b.is_my_blunder=1 AND b.is_berserk=0
            """,
            (cutoff_ts,),
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
                (cutoff_ts,),
            )
            cascade_games = cur.fetchone()[0] or 0
            cascade_pct = (cascade_games / total_games_blunder) * 100.0
    except Exception:
        pass

    g_r = game_rating(acpl)
    s_r = speed_rating(avg_t)
    a_r = aggression_rating(aggr_score)
    st_r = state_rating(conv_pct, cascade_pct)
    combr = combined_rating(g_r, s_r, a_r, st_r)
    perf = perf_rating(avg_opp, wins, draws, n) if (n and avg_opp) else 0.0

    return {
        "games": n,
        "acpl": acpl,
        "acpl_vals": acpl_vals,
        "p10": p10,
        "p50": p50,
        "p90": p90,
        "std_acpl": std_acpl,
        "mom": mom,
        "wins": wins,
        "draws": draws,
        "avg_opp": avg_opp or 0.0,
        "avg_my": avg_my or 0.0,
        "peak": peak_r or 0,
        "bottom": bottom_r or 0,
        "avg_t": avg_t,
        "aggr_score": aggr_score,
        "conv_pct": conv_pct,
        "cascade_pct": cascade_pct,
        "gamr": g_r,
        "speedr": s_r,
        "aggr_r": a_r,
        "state_r": st_r,
        "combr": combr,
        "perf": perf,
    }


def key_numbers(days: int = 90) -> dict:
    """Ключевые цифры за выбранное окно (по умолчанию 90 дней; для сессии дня — days=1)."""
    conn = get_conn()
    cur = conn.cursor()
    ts = window_cutoff_ts(days)
    result = {}

    try:
        m = calc_window_factors(cur, ts)
        n = m["games"]
        result["Партий:"] = n

        cur.execute(
            """
            SELECT my_rating FROM games
            WHERE is_lag=0 AND is_cheater=0 AND my_rating > 0
            ORDER BY end_time DESC LIMIT 1
            """
        )
        last_row = cur.fetchone()
        last_rating = round(last_row[0]) if (last_row and last_row[0]) else None

        if n == 0:
            if last_rating:
                result["Последний рейтинг:"] = last_rating
            result["Статус:"] = f"нет партий за {days}д"
            return result

        acpl = m["acpl"]
        acpl_vals = m["acpl_vals"]

        result["ACPL:"] = f"{acpl:.0f} (мед: {m['p50']:.0f})" if acpl_vals else f"{acpl:.1f}"
        result["Моментум после зевка:"] = (
            f"{m['mom']:.0f} CP" if m["mom"] is not None else "нет данных (N=0)"
        )
        result["Winrate:"] = f"{(m['wins'] + 0.5 * m['draws']) / n * 100:.1f}%"
        if m["avg_opp"]:
            result[f"Perf ({days}д):"] = round(m["perf"])
        if m["avg_my"]:
            result[f"Средний рейтинг ({days}д):"] = round(m["avg_my"])
        if last_rating:
            result["Последний рейтинг:"] = last_rating

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
            result[f"Просрочки ({days}д):"] = f"{n_timeout} ({n_timeout / n * 100:.1f}%)"
        except Exception:
            pass

        if acpl_vals:
            result["ACPL P10 (лучшие 10%):"] = f"{m['p10']:.1f} (GameR {round(game_rating(m['p10']))})"
            result["ACPL P90 (худшие 10%):"] = f"{m['p90']:.1f} (GameR {round(game_rating(m['p90']))})"
            result["StdDev ACPL:"] = f"{m['std_acpl']:.1f}"

        combr = m["combr"]
        result["Состояние:"] = get_blade_state(combr)
        result["CombR:"] = round(combr)
        result["  (Точность/Мышление):"] = round(m["gamr"])
        result["  (Скорость/Интуиция):"] = round(m["speedr"])
        result["  (Агрессия/Ощущения):"] = round(m["aggr_r"])
        result["  (Тильт/Чувства):"] = round(m["state_r"])
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return result


def top3_weaknesses() -> list:
    """Динамический топ-3 зон потери очков за 90 дней: список (название, детали, файл)."""
    conn = get_conn()
    cur = conn.cursor()
    ts = window_cutoff_ts(90)
    weaknesses = []
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
            sliv_pct = sliv / total_adv * 100.0
            weaknesses.append((
                sliv_pct,
                "Слив перевеса (+3.0)",
                f"{sliv} из {total_adv} партий ({sliv_pct:.1f}%) проиграно после +3.0",
                "02_middlegame.txt",
            ))

        cur.execute(
            """
            SELECT COUNT(*) FROM games
            WHERE is_lag=0 AND is_cheater=0 AND end_time >= ?
            """,
            (ts,),
        )
        n_total = cur.fetchone()[0] or 0
        if n_total > 0:
            cur.execute(
                """
                SELECT COUNT(*) FROM games
                WHERE is_lag=0 AND is_cheater=0 AND end_time >= ?
                  AND won=0 AND draw=0 AND reason = 'просрочка'
                """,
                (ts,),
            )
            n_to = cur.fetchone()[0] or 0
            to_pct = n_to / n_total * 100.0
            weaknesses.append((
                to_pct,
                "Просрочки времени",
                f"{n_to} партий ({to_pct:.1f}%) отдано по флагу",
                "03_endgame.txt",
            ))

        cur.execute(
            """
            SELECT AVG(acpl_opening), AVG(acpl_middlegame), AVG(acpl_endgame)
            FROM games WHERE is_lag=0 AND is_cheater=0 AND end_time >= ? AND acpl > 0
            """,
            (ts,),
        )
        op_a, mid_a, end_a = cur.fetchone()
        phases = [
            (mid_a or 0.0, "Провалы в миттельшпиле", f"ACPL миттельшпиля = {(mid_a or 0):.1f}", "02_middlegame.txt"),
            (end_a or 0.0, "Техника эндшпиля", f"ACPL эндшпиля = {(end_a or 0):.1f}", "03_endgame.txt"),
            (op_a or 0.0, "Дебютная точность", f"ACPL дебюта = {(op_a or 0):.1f}", "01_openings.txt"),
        ]
        phases.sort(key=lambda x: x[0], reverse=True)
        if phases[0][0] > 0:
            weaknesses.append(phases[0])
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass

    weaknesses.sort(key=lambda x: x[0], reverse=True)
    result = [(w[1], w[2], w[3]) for w in weaknesses[:3]]
    while len(result) < 3:
        result.append((
            "Каскадные зевки",
            "Повторная ошибка в течение 5 ходов после первого зевка",
            "04_psych_focus.txt",
        ))
    return result


def top_actions() -> list:
    return [
        "При +3.0 — держи ритм, не ускоряйся, смотри на часы  → 02_middlegame.txt",
        "Пауза 3 сек после первого зевка                      → 04_psych_focus.txt",
        "На ходах 10-15 — замедлись в 2 раза, проверь угрозы  → 04_psych_focus.txt",
        "Против aggressive — сушить позицию (менять фигуры)   → 07_opponents.txt",
    ]