# ============================================================
# analysis/psych_state/psych_tilt.py (v25.0)
# Фикс §30: каскадный тильт — % партий, не % зевков.
# Удалён report_tilt_timer (см. PROJECT_RULES §28).
# ============================================================
import os
import json
from collections import defaultdict
from analysis.common import report_context
from .common import _conn, REPORTS_DIR, _is_player_white


def _phase_of_move(move_num):
    if move_num <= 10:
        return "opening"
    if move_num <= 30:
        return "middlegame"
    return "endgame"


def report_panic_curve():
    conn = _conn(); cur = conn.cursor()

    time_labels = [" > 10 сек", "5-10 сек", "3-5 сек", "2-3 сек", "1-2 сек", "< 1 сек"]
    local_buckets = {k: {"n": 0, "loss_sum": 0} for k in time_labels}

    cur.execute("""
        SELECT b.move_num, b.loss_cp, g.white, g.clocks
        FROM blunders b JOIN games g ON g.url = b.game_url
        WHERE g.is_cheater=0 AND g.is_lag=0
          AND b.is_my_blunder=1 AND b.is_berserk=0 AND b.is_instant=0
    """)
    for move_num, loss_cp, white, clocks_raw in cur.fetchall():
        try:
            clocks = json.loads(clocks_raw) if clocks_raw else []
            if not clocks:
                continue
            player_is_white = _is_player_white(white)
            idx = (move_num - 1) * 2 + (0 if player_is_white else 1)
            if idx < len(clocks):
                t = clocks[idx]
                if t > 10:
                    k = " > 10 сек"
                elif t >= 5:
                    k = "5-10 сек"
                elif t >= 3:
                    k = "3-5 сек"
                elif t >= 2:
                    k = "2-3 сек"
                elif t >= 1:
                    k = "1-2 сек"
                else:
                    k = "< 1 сек"
                local_buckets[k]["n"] += 1
                local_buckets[k]["loss_sum"] += loss_cp
        except Exception:
            continue

    with report_context("panic_curve") as w:
        w.w_separator(title="КРИВАЯ ПАНИКИ (потеря vs остаток времени)")
        w.w("📊 ЛОКАЛЬНАЯ ЦЕНА ОШИБКИ:")
        w.w(f"  {'Остаток времени':<18} {'Ходов-зевков':<14} {'Ср. потеря (CP)'}")
        w.w("  " + "-" * 52)
        for k in time_labels:
            d = local_buckets[k]
            if d["n"] > 0:
                w.w(f"  {k:<18} {d['n']:<14} {d['loss_sum'] / d['n']:<.0f}")
        w.w()
        w.w("🎯 ВЕРДИКТ:")
        worst_k = max(
            time_labels,
            key=lambda k: (local_buckets[k]["loss_sum"] / local_buckets[k]["n"])
            if local_buckets[k]["n"] > 5 else -1,
        )
        if local_buckets[worst_k]["n"] > 5:
            worst_val = local_buckets[worst_k]["loss_sum"] / local_buckets[worst_k]["n"]
            if worst_k in ["< 1 сек", "1-2 сек", "2-3 сек"]:
                w.w(f"  ⚠️ Худшая зона — {worst_k} (ср. потеря {worst_val:.0f} CP). Цейтнот.")
            else:
                w.w(f"  ⚠️ Худшая зона — {worst_k} (ср. потеря {worst_val:.0f} CP). «Слепота».")
    conn.close()


def report_cascade_tilt():
    """
    v25.0: считаем % ПАРТИЙ с каскадом, а не % зевков.
    Определение каскада: ≥2 моих зевка (без берсерка) с разницей ≤5 ходов.
    """
    conn = _conn(); cur = conn.cursor()

    cur.execute("""
        SELECT b.game_url, b.move_num
        FROM blunders b JOIN games g ON g.url = b.game_url
        WHERE g.is_lag=0 AND g.is_cheater=0
          AND b.is_my_blunder=1
          AND b.is_berserk=0 AND b.is_instant=0
        ORDER BY b.game_url, b.move_num
    """)
    rows = cur.fetchall()

    by_game = defaultdict(list)
    for url, mn in rows:
        by_game[url].append(mn)

    total_games = len(by_game)
    cascade_games = 0

    phases = {
        "opening":    {"games": 0, "cascade_games": 0},
        "middlegame": {"games": 0, "cascade_games": 0},
        "endgame":    {"games": 0, "cascade_games": 0},
    }

    for url, moves in by_game.items():
        moves.sort()
        game_phases = set()
        cascade_phases = set()

        for mn in moves:
            game_phases.add(_phase_of_move(mn))

        for i in range(len(moves) - 1):
            if moves[i + 1] - moves[i] <= 5:
                cascade_phases.add(_phase_of_move(moves[i]))
                cascade_phases.add(_phase_of_move(moves[i + 1]))

        for ph in game_phases:
            phases[ph]["games"] += 1
        for ph in cascade_phases:
            phases[ph]["cascade_games"] += 1

        if cascade_phases:
            cascade_games += 1

    with report_context("cascade_tilt") as w:
        w.w_separator(title="КАСКАДНЫЙ ТИЛЬТ (зевок после зевка)")
        w.w(f"📊 Всего партий с зевками (без берсерка): {total_games}")
        if total_games > 0:
            pct_all = cascade_games / total_games * 100
            w.w(f"📊 Партий с каскадом (≥2 зевка ≤5 ходов): {cascade_games} ({pct_all:.1f}%)")
        w.w()
        w.w("📊 РАЗБИВКА ПО ФАЗАМ (считаем ПАРТИИ, не зевки):")
        w.w(f"  {'Фаза':<15} {'Партий':<10} {'С каскадом':<12} {'% партий'}")
        w.w("  " + "-" * 50)
        for p_name, p_label in [
            ("opening", "Дебют"),
            ("middlegame", "Миттельшпиль"),
            ("endgame", "Эндшпиль"),
        ]:
            d = phases[p_name]
            if d["games"] > 0:
                pct = d["cascade_games"] / d["games"] * 100
                w.w(f"  {p_label:<15} {d['games']:<10} {d['cascade_games']:<12} {pct:.1f}%")
        w.w()
        if phases["middlegame"]["games"] > 0:
            mid_pct = phases["middlegame"]["cascade_games"] / phases["middlegame"]["games"] * 100
            if mid_pct > 50:
                w.w(f"  💡 {mid_pct:.0f}% партий имеют каскад в миттельшпиле.")
                w.w("  💡 Правило: если зевнул — СТОП. Смотри на часы, не паникуй.")
    conn.close()


def report_aggression_profile():
    conn = _conn(); cur = conn.cursor()

    cur.execute("""
        SELECT url, white, won, my_rating, eval_history, opp_rating
        FROM games
        WHERE is_lag=0 AND is_cheater=0
          AND eval_history IS NOT NULL AND eval_history != '[]'
    """)
    rows = cur.fetchall()

    rating_stats = {k: {"n": 0, "agg_sum": 0, "wins": 0}
                    for k in ["2400-2499", "2500-2599", "2600-2699", "2700+"]}

    for url, white, won, my_rating, evals_raw, opp_rating in rows:
        try:
            hist = json.loads(evals_raw)
            if not hist:
                continue
        except Exception:
            continue

        agg = 0
        prev = None
        for move, ev in hist:
            if prev is not None and ev - prev >= 50:
                agg += 1
            prev = ev

        r = opp_rating or 0
        if r < 2500:
            k = "2400-2499"
        elif r < 2600:
            k = "2500-2599"
        elif r < 2700:
            k = "2600-2699"
        else:
            k = "2700+"
        rating_stats[k]["n"] += 1
        rating_stats[k]["agg_sum"] += agg
        if won:
            rating_stats[k]["wins"] += 1

    with report_context("aggression_profile") as w:
        w.w_separator(title="AGGRESSION PROFILE (агрессия и инверсия)")
        w.w("📊 АГРЕССИЯ ПО РЕЙТИНГУ СОПЕРНИКА")
        w.w(f"  {'Рейтинг':<15} {'Партий':<8} {'Агрессия':<12} {'Винрейт'}")
        w.w("  " + "-" * 45)
        for k in ["2400-2499", "2500-2599", "2600-2699", "2700+"]:
            d = rating_stats[k]
            if d["n"] > 0:
                w.w(f"  {k:<15} {d['n']:<8} {d['agg_sum']/d['n']:<12.1f} {d['wins']/d['n']*100:<.1f}%")
        w.w()
        agg_2400 = (rating_stats["2400-2499"]["agg_sum"] / rating_stats["2400-2499"]["n"]
                    if rating_stats["2400-2499"]["n"] else 0)
        agg_2700 = (rating_stats["2700+"]["agg_sum"] / rating_stats["2700+"]["n"]
                    if rating_stats["2700+"]["n"] else 0)
        if agg_2400 > 0 and agg_2700 > 0:
            drop = agg_2400 - agg_2700
            if drop > 1:
                w.w(f"  ⚠️ ИНВЕРСИЯ АГРЕССИИ: с 2400 ({agg_2400:.1f}) к 2700+ ({agg_2700:.1f}) падает на {drop:.1f}.")
                w.w("  💡 Правило: против 2600+ играй так, как будто он 2400. Атакуй.")
            else:
                w.w(f"  ✅ Агрессия стабильна ({agg_2400:.1f} → {agg_2700:.1f}). Не инвертируется.")
    conn.close()


def run_psych_tilt():
    print("  1/3. Panic Curve")
    report_panic_curve()
    print("  2/3. Cascade Tilt (v25.0: % партий)")
    report_cascade_tilt()
    print("  3/3. Aggression Profile")
    report_aggression_profile()