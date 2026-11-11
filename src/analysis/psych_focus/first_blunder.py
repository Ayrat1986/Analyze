# ============================================================
# analysis/psych_focus/first_blunder.py (v19.1)
# ============================================================
from collections import Counter
from core.пороги import get as get_threshold
from analysis.common import report_context
from .common import _conn

def report_first_blunder():
    conn = _conn(); cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM games WHERE is_lag=0 AND is_cheater=0")
    total_games = cur.fetchone()[0] or 0

    cur.execute("""
        SELECT g.url, g.won, g.draw, g.reason, b.move_num, b.loss_cp, b.pattern_tag
        FROM games g JOIN blunders b ON b.game_url = g.url
        WHERE g.is_lag=0 AND g.is_cheater=0 AND b.is_my_blunder=1 AND b.is_berserk=0 AND b.is_instant=0 AND b.loss_cp > ?
        ORDER BY g.url, b.move_num ASC
    """, (get_threshold("blunder_threshold_cp", 150),))
    
    first_by_url = {}
    for url, won, draw, reason, mn, loss, pat in cur.fetchall():
        if url not in first_by_url:
            first_by_url[url] = {
                "won": won or 0, "draw": draw or 0, "reason": reason or "",
                "move_num": mn, "loss": loss, "pattern": pat or "blunder",
            }

    with report_context("first_blunder_report") as w:
        w.w_separator(title="ПЕРВЫЙ ЗЕВОК В ПАРТИИ (водораздел)")
        
        if not first_by_url:
            w.w("⚠️ Нет партий с зевками >150 CP.")
            conn.close(); return

        games_with = len(first_by_url)
        games_without = total_games - games_with

        phases = {
            "Дебют (1–10)": {"n": 0, "w": 0, "d": 0, "loss_sum": 0, "moves_sum": 0},
            "Миттельшпиль (11–30)": {"n": 0, "w": 0, "d": 0, "loss_sum": 0, "moves_sum": 0},
            "Эндшпиль (31+)": {"n": 0, "w": 0, "d": 0, "loss_sum": 0, "moves_sum": 0},
        }
        by_move = Counter()

        for url, d in first_by_url.items():
            mn = d["move_num"] or 0
            if mn <= 10: k = "Дебют (1–10)"
            elif mn <= 30: k = "Миттельшпиль (11–30)"
            else: k = "Эндшпиль (31+)"
            
            p = phases[k]
            p["n"] += 1
            if d["won"]: p["w"] += 1
            if d["draw"]: p["d"] += 1
            p["loss_sum"] += d["loss"] or 0
            p["moves_sum"] += mn
            by_move[mn] += 1

        total_move = sum(d["move_num"] for d in first_by_url.values())
        avg_first_move = total_move / games_with
        sorted_moves = sorted(d["move_num"] for d in first_by_url.values())
        median_first_move = sorted_moves[len(sorted_moves) // 2]

        wins_with = sum(d["won"] for d in first_by_url.values())
        draws_with = sum(d["draw"] for d in first_by_url.values())
        score_with = (wins_with + 0.5 * draws_with) / games_with * 100

        score_without = 0
        if games_without > 0:
            cur.execute("""
                SELECT SUM(won), SUM(draw) FROM games g
                WHERE g.is_lag=0 AND g.is_cheater=0 AND g.url NOT IN (
                    SELECT DISTINCT b.game_url FROM blunders b
                    WHERE b.is_my_blunder=1 AND b.is_berserk=0 AND b.is_instant=0 AND b.loss_cp > 150
                )
            """)
            w_out, d_out = cur.fetchone()
            w_out = w_out or 0; d_out = d_out or 0
            score_without = (w_out + 0.5 * d_out) / games_without * 100

        w.w(f"Всего партий: {total_games}")
        w.w(f"  С зевками >150 CP:  {games_with}")
        w.w(f"  Без зевков:         {games_without}")
        w.w(f"  Средний ход 1-го зевка:   {avg_first_move:.1f}")
        w.w(f"  Медианный ход 1-го зевка: {median_first_move}")
        w.w()

        w.w("📊 ПО ФАЗЕ ПЕРВОГО ЗЕВКА:")
        w.w(f"  {'Фаза':<24} {'Партий':<8} {'Win%':<7} {'Ср.потеря':<12} {'Ср.ход'}")
        w.w("  " + "-" * 65)
        for k in ["Дебют (1–10)", "Миттельшпиль (11–30)", "Эндшпиль (31+)"]:
            p = phases[k]
            if p["n"] == 0: continue
            wr = (p["w"] + 0.5 * p["d"]) / p["n"] * 100
            avg_loss = p["loss_sum"] / p["n"]
            avg_mv = p["moves_sum"] / p["n"]
            w.w(f"  {k:<24} {p['n']:<8} {wr:<7.1f} {avg_loss:<12.0f} {avg_mv:<.1f}")
        w.w()

        w.w("📊 ТОП-10 ХОДОВ, ГДЕ ЧАЩЕ ВСЕГО ПЕРВЫЙ ЗЕВОК:")
        w.w(f"  {'Ход':<6} {'Партий':<8}")
        w.w("  " + "-" * 20)
        for mn, cnt in by_move.most_common(10):
            w.w(f"  {mn:<6} {cnt:<8}")
        w.w()

        w.w("📊 СРАВНЕНИЕ WINRATE:")
        w.w(f"  Партии БЕЗ зевков: {score_without:.1f}% ({games_without} партий)")
        w.w(f"  Партии С зевком:   {score_with:.1f}% ({games_with} партий)")
        w.w(f"  Δ:                 {score_without - score_with:+.1f}%")
        w.w()

        w.w("🎯 ВЕРДИКТ:")
        worst_phase = max(phases, key=lambda k: phases[k]["n"])
        w.w(f"  Больше всего первых зевков в фазе: {worst_phase}.")
        if score_without > score_with + 10:
            w.w("  📉 Первый зевок реально решает партию. Твой «час X» — 17-й ход.")
        else:
            w.w("  ➡️ Ты умеешь отыгрываться после первого зевка.")

    conn.close()

def run_first_blunder():
    report_first_blunder()