# ============================================================
# analysis/psych_state/psych_tilt.py (v19.1)
# ============================================================
import os
import json
from collections import defaultdict
from analysis.common import report_context
from .common import _conn, REPORTS_DIR, _is_player_white

def report_tilt_timer():
    conn = _conn(); cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM blunders WHERE is_my_blunder=1")
    total_blunders = cur.fetchone()[0] or 0
    cur.execute("SELECT COUNT(*) FROM blunders WHERE is_my_blunder=1 AND next_move_time IS NOT NULL")
    with_time = cur.fetchone()[0] or 0

    cur.execute("""
        SELECT b.next_move_time FROM blunders b JOIN games g ON g.url = b.game_url
        WHERE g.is_lag=0 AND g.is_cheater=0 AND b.is_my_blunder=1 AND b.loss_cp > 150 AND b.next_move_time IS NOT NULL
    """)
    rows = cur.fetchall()

    with report_context("tilt_timer") as w:
        w.w_separator(title="TILT TIMER (реакция на зевок)")
        w.w(f"Диагностика: total_blunders={total_blunders}, with_next_move_time={with_time}\n")

        if not rows:
            w.w("⚠️ Нет данных для Tilt-Timer.")
            conn.close(); return

        panic = fast = normal = slow = 0
        for (nt,) in rows:
            if nt < 0.5: panic += 1
            elif nt < 1.0: fast += 1
            elif nt < 2.0: normal += 1
            else: slow += 1
        total = len(rows)

        w.w(f"Всего зевков: {total}\n")
        w.w(f"  {'Время на след. ход':<22} {'Кол-во':<8} {'%':<8}")
        w.w("  " + "-" * 42)
        w.w(f"  {'< 0.5 сек (паника)':<22} {panic:<8} {panic/total*100:<8.1f}%")
        w.w(f"  {'0.5-1 сек (спешка)':<22} {fast:<8} {fast/total*100:<8.1f}%")
        w.w(f"  {'1-2 сек (норма)':<22} {normal:<8} {normal/total*100:<8.1f}%")
        w.w(f"  {'> 2 сек (просчет)':<22} {slow:<8} {slow/total*100:<8.1f}%")
        w.w()
        w.w("🎯 ВЕРДИКТ:")
        if panic / total > 0.3:
            w.w("  ⚠️ >30% следующих ходов после зевка — мгновенные (<0.5 сек). Это паника.")
            w.w("  💡 Правило: после зевка — пауза 2 сек.")
        else:
            w.w("  ✅ Ты не паникуешь после зевка.")
    conn.close()

def report_panic_curve():
    conn = _conn(); cur = conn.cursor()

    time_labels = [" > 10 сек", "5-10 сек", "3-5 сек", "2-3 сек", "1-2 сек", "< 1 сек"]
    local_buckets = {k: {"n": 0, "loss_sum": 0} for k in time_labels}

    cur.execute("""
        SELECT b.move_num, b.loss_cp, g.white, g.clocks
        FROM blunders b JOIN games g ON g.url = b.game_url
        WHERE g.is_cheater=0 AND g.is_lag=0 AND b.is_my_blunder=1 AND b.is_berserk=0 AND b.is_instant=0
    """)
    for move_num, loss_cp, white, clocks_raw in cur.fetchall():
        try:
            clocks = json.loads(clocks_raw) if clocks_raw else []
            if not clocks: continue
            player_is_white = _is_player_white(white)
            idx = (move_num - 1) * 2 + (0 if player_is_white else 1)
            if idx < len(clocks):
                t = clocks[idx]
                if t > 10: k = " > 10 сек"
                elif t >= 5: k = "5-10 сек"
                elif t >= 3: k = "3-5 сек"
                elif t >= 2: k = "2-3 сек"
                elif t >= 1: k = "1-2 сек"
                else: k = "< 1 сек"
                local_buckets[k]["n"] += 1; local_buckets[k]["loss_sum"] += loss_cp
        except Exception: continue

    with report_context("panic_curve") as w:
        w.w_separator(title="КРИВАЯ ПАНИКИ (потеря vs остаток времени)")
        w.w("📊 ЛОКАЛЬНАЯ ЦЕНА ОШИБКИ:")
        w.w(f"  {'Остаток времени':<18} {'Ходов-зевков':<14} {'Ср. потеря (CP)'}")
        w.w("  " + "-" * 52)
        for k in time_labels:
            d = local_buckets[k]
            if d["n"] > 0: w.w(f"  {k:<18} {d['n']:<14} {d['loss_sum'] / d['n']:<.0f}")
        w.w()
        w.w("🎯 ВЕРДИКТ:")
        worst_k = max(time_labels, key=lambda k: (local_buckets[k]["loss_sum"] / local_buckets[k]["n"]) if local_buckets[k]["n"] > 5 else -1)
        if local_buckets[worst_k]["n"] > 5:
            worst_val = local_buckets[worst_k]["loss_sum"] / local_buckets[worst_k]["n"]
            if worst_k in ["< 1 сек", "1-2 сек", "2-3 сек"]:
                w.w(f"  ⚠️ Худшая зона — {worst_k} (ср. потеря {worst_val:.0f} CP). Цейтнот.")
            else:
                w.w(f"  ⚠️ Худшая зона — {worst_k} (ср. потеря {worst_val:.0f} CP). «Слепота».")
    conn.close()

def report_cascade_tilt():
    conn = _conn(); cur = conn.cursor()

    cur.execute("""
        SELECT b.game_url, b.move_num, b.loss_cp, b.is_next_move_blunder, b.is_berserk, b.is_instant
        FROM blunders b JOIN games g ON g.url = b.game_url
        WHERE g.is_lag=0 AND g.is_cheater=0 AND b.is_my_blunder=1
    """)
    blunders = cur.fetchall()

    phases = {"opening": {"total": 0, "cascades": 0}, "middlegame": {"total": 0, "cascades": 0}, "endgame": {"total": 0, "cascades": 0}}
    berserk_cascades = normal_cascades = 0

    for url, move_num, loss, is_next, is_berserk, is_instant in blunders:
        is_speed = is_berserk or is_instant
        if move_num <= 10: phase = "opening"
        elif move_num <= 30: phase = "middlegame"
        else: phase = "endgame"
        phases[phase]["total"] += 1

        if is_speed:
            if is_next: berserk_cascades += 1
        else:
            if is_next:
                normal_cascades += 1; phases[phase]["cascades"] += 1

    with report_context("cascade_tilt") as w:
        w.w_separator(title="КАСКАДНЫЙ ТИЛЬТ (зевок после зевка)")
        w.w(f"📊 [В БЕРСЕРКЕ] Каскадных: {berserk_cascades}.")
        w.w(f"📊 [В НОРМАЛЬНОМ ВРЕМЕНИ] Всего каскадов: {normal_cascades}\n")
        w.w("📊 РАЗБИВКА ПО ФАЗАМ:")
        for p_name, p_label in [("opening", "Дебют"), ("middlegame", "Миттельшпиль"), ("endgame", "Эндшпиль")]:
            d = phases[p_name]
            if d["total"] > 0:
                pct = d["cascades"] / d["total"] * 100
                w.w(f"  {p_label:<15} {d['total']:<15} {d['cascades']:<10} {pct:.1f}%")
        w.w()
        if phases["middlegame"]["total"] > 0:
            mid_pct = phases["middlegame"]["cascades"] / phases["middlegame"]["total"] * 100
            if mid_pct > 50:
                w.w(f"  💡 {mid_pct:.0f}% каскадов в миттельшпиле.")
                w.w("  💡 Правило: если зевнул — СТОП. Смотри на часы, не паникуй.")
    conn.close()

def report_aggression_profile():
    conn = _conn(); cur = conn.cursor()

    cur.execute("SELECT url, white, won, my_rating, eval_history, opp_rating FROM games WHERE is_lag=0 AND is_cheater=0 AND eval_history IS NOT NULL AND eval_history != '[]'")
    rows = cur.fetchall()

    rating_stats = {k: {"n": 0, "agg_sum": 0, "wins": 0} for k in ["2400-2499", "2500-2599", "2600-2699", "2700+"]}

    for url, white, won, my_rating, evals_raw, opp_rating in rows:
        try:
            hist = json.loads(evals_raw)
            if not hist: continue
        except Exception: continue

        agg = 0; prev = None
        for move, ev in hist:
            if prev is not None and ev - prev >= 50: agg += 1
            prev = ev

        r = opp_rating or 0
        if r < 2500: k = "2400-2499"
        elif r < 2600: k = "2500-2599"
        elif r < 2700: k = "2600-2699"
        else: k = "2700+"
        rating_stats[k]["n"] += 1; rating_stats[k]["agg_sum"] += agg
        if won: rating_stats[k]["wins"] += 1

    with report_context("aggression_profile") as w:
        w.w_separator(title="AGGRESSION PROFILE (агрессия и инверсия)")
        w.w("📊 АГРЕССИЯ ПО РЕЙТИНГУ СОПЕРНИКА")
        w.w(f"  {'Рейтинг':<15} {'Партий':<8} {'Агрессия':<12} {'Винрейт'}")
        w.w("  " + "-" * 45)
        for k in ["2400-2499", "2500-2599", "2600-2699", "2700+"]:
            d = rating_stats[k]
            if d["n"] > 0: w.w(f"  {k:<15} {d['n']:<8} {d['agg_sum']/d['n']:<12.1f} {d['wins']/d['n']*100:<.1f}%")
        w.w()
        agg_2400 = rating_stats["2400-2499"]["agg_sum"] / rating_stats["2400-2499"]["n"] if rating_stats["2400-2499"]["n"] else 0
        agg_2700 = rating_stats["2700+"]["agg_sum"] / rating_stats["2700+"]["n"] if rating_stats["2700+"]["n"] else 0
        if agg_2400 > 0 and agg_2700 > 0:
            drop = agg_2400 - agg_2700
            if drop > 1:
                w.w(f"  ⚠️ ИНВЕРСИЯ АГРЕССИИ: с 2400 ({agg_2400:.1f}) к 2700+ ({agg_2700:.1f}) падает на {drop:.1f}.")
                w.w("  💡 Правило: против 2600+ играй так, как будто он 2400. Атакуй.")
            else:
                w.w(f"  ✅ Агрессия стабильна ({agg_2400:.1f} → {agg_2700:.1f}). Не инвертируется.")
    conn.close()

def run_psych_tilt():
    print("  1/4. Tilt Timer")
    report_tilt_timer()
    print("  2/4. Panic Curve")
    report_panic_curve()
    print("  3/4. Cascade Tilt")
    report_cascade_tilt()
    print("  4/4. Aggression Profile")
    report_aggression_profile()