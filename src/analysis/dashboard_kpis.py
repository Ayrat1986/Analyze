# ============================================================
# analysis/dashboard_kpis.py — v27.5
# Ключевые метрики 90 дней (4-факторный CombR v2), топ-3 слабости и действия.
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
    aggression_rating,
    combined_rating_v2,
    game_rating,
    perf_rating,
    speed_rating,
    state_rating,
)


def key_numbers() -> dict:
    conn = get_conn()
    cur = conn.cursor()
    ts = window_cutoff_ts(90)
    result = {}

    try:
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
        p50_acpl = percentile(acpl_vals, 0.50)
        p10_acpl = percentile(acpl_vals, 0.10)
        p90_acpl = percentile(acpl_vals, 0.90)
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

        aggr_score = calc_aggr_score_from_pgn(cur, ts)

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