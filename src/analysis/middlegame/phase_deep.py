# ============================================================
# analysis/middlegame/phase_deep.py (v19.0)
# ============================================================
from collections import defaultdict
from analysis.common import report_context
from .common import _conn, get_base_filter, get_threshold

def report_phase_deep_dive():
    conn = _conn()
    cur = conn.cursor()
    base = get_base_filter()
    THRESHOLD = get_threshold("acpl_mid_red", 75)

    cur.execute(f"""
        SELECT white, black, won, draw, opening, eco, acpl_middlegame, max_eval_advantage
        FROM games WHERE {base} AND acpl_middlegame > ?
    """, (THRESHOLD,))
    bad = cur.fetchall()

    cur.execute(f"SELECT COUNT(*) FROM games WHERE {base}")
    n_all = cur.fetchone()[0] or 1
    n_bad = len(bad)

    with report_context("phase_deep_dive") as w:
        w.w_separator(title=f"PHASE DEEP DIVE: миттельшпиль > {THRESHOLD} CP")
        w.w(f"Всего: {n_all}, провалов: {n_bad} ({n_bad/n_all*100:.1f}%)")
        w.w()

        # --- 1. Дебюты с провалом ---
        by_open = defaultdict(lambda: {"n": 0, "w": 0})
        for g in bad:
            by_open[g[4] or "?"]["n"] += 1
            if g[2]:
                by_open[g[4] or "?"]["w"] += 1

        w.w("📊 ТОП-15 ДЕБЮТОВ (где провал):")
        for op, d in sorted(by_open.items(), key=lambda x: -x[1]["n"])[:15]:
            if d["n"] >= 3:
                w.w(f"  {op[:50]:<52} {d['n']:>3}п / {d['w']}поб")
        w.w()

        # --- 2. Типы зевков в миттельшпиле ---
        cur.execute(f"""
            SELECT b.pattern_tag, COUNT(*) FROM blunders b JOIN games g ON g.url=b.game_url
            WHERE {base} AND b.is_berserk=0 AND b.is_instant=0
              AND b.is_my_blunder=1 AND b.move_num BETWEEN 11 AND 30
            GROUP BY b.pattern_tag ORDER BY COUNT(*) DESC
        """)
        pats = cur.fetchall()
        tot_p = sum(p[1] for p in pats) or 1

        w.w("📊 ТИПЫ ЗЕВКОВ В МИТТЕЛЬШПИЛЕ:")
        for tag, cnt in pats[:10]:
            w.w(f"  {tag:<25} {cnt:>4} ({cnt/tot_p*100:.1f}%)")
        w.w()

        # --- 3. Слив перевеса ---
        sliv = sum(1 for g in bad if g[7] and g[7] >= 300 and not g[2] and not g[3])
        win_pos = sum(1 for g in bad if g[7] and g[7] >= 300)
        if win_pos:
            w.w(f"📊 СЛИВ ПЕРЕВЕСА: {sliv}/{win_pos} ({sliv/win_pos*100:.1f}%)")
            w.w("  (учитываются только поражения — ничьи с перевесом = «недобрал», не «слил»)")

    conn.close()