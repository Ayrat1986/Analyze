# ============================================================
# analysis/middlegame/transition.py (v19.0)
# ============================================================
from analysis.common import report_context
from .common import _conn, get_base_filter

def report_transition_errors():
    conn = _conn()
    cur = conn.cursor()
    base = get_base_filter()

    with report_context("transition_errors") as w:
        w.w_separator(title="TRANSITION ERRORS: переход дебют → миттельшпиль")
        w.w("Ошибки на ходах 10-15 — самый уязвимый момент после дебюта.")
        w.w()

        cur.execute(f"""
            SELECT substr(g.eco, 1, 3) AS eco3, COUNT(*), ROUND(AVG(b.loss_cp)),
                   SUM(CASE WHEN g.won=0 THEN 1 ELSE 0 END)
            FROM blunders b JOIN games g ON g.url=b.game_url
            WHERE {base} AND b.is_my_blunder=1 AND b.is_berserk=0 AND b.is_instant=0
              AND b.move_num BETWEEN 10 AND 15
            GROUP BY eco3 HAVING COUNT(*) >= 3
            ORDER BY COUNT(*) DESC LIMIT 15
        """)
        rows = cur.fetchall()

        if not rows:
            w.w("✅ Ошибок на переходе нет — отлично!")
        else:
            w.w("📊 ТОП-15 ДЕБЮТОВ, где теряешь нить при переходе:")
            w.w(f"  {'ECO':<6} {'Ошибок':<8} {'Ср. потеря':<12} {'Слито игр':<10}")
            for eco, cnt, avg_loss, lost in rows:
                w.w(f"  {eco:<6} {cnt:<8} {avg_loss:<12.0f} {lost:<10}")

            w.w()
            w.w("🎯 ВЕРДИКТ:")
            top3 = rows[:3]
            w.w(f"  Топ-3 проблемных перехода: {', '.join(r[0] for r in top3)}")
            w.w("  Это не «не знаю план», а «знаю план, но не удерживаю».")
            w.w("  Правило: перед ходом 10-15 — пауза 2 сек, проверь 3 вещи:")
            w.w("    1. Куда смотрит его последняя фигура (Вектор)?")
            w.w("    2. Где мой самый слабый пункт?")
            w.w("    3. Могу ли я упростить, не теряя перевеса?")

        w.w()
        w.w("📊 РАСПРЕДЕЛЕНИЕ ОШИБОК ПО ХОДАМ (10-25):")

        cur.execute(f"""
            SELECT
                CASE
                    WHEN b.move_num BETWEEN 10 AND 15 THEN '10-15 (переход)'
                    WHEN b.move_num BETWEEN 16 AND 20 THEN '16-20'
                    WHEN b.move_num BETWEEN 21 AND 25 THEN '21-25'
                END AS window,
                COUNT(*)
            FROM blunders b JOIN games g ON g.url=b.game_url
            WHERE {base} AND b.is_my_blunder=1 AND b.is_berserk=0 AND b.is_instant=0
              AND b.move_num BETWEEN 10 AND 25
            GROUP BY window ORDER BY window
        """)
        win_rows = cur.fetchall()
        total_w = sum(r[1] for r in win_rows) or 1
        for window, cnt in win_rows:
            bar = "█" * int(cnt / total_w * 40)
            w.w(f"  {window:<22} {cnt:>4} ({cnt/total_w*100:>4.1f}%) {bar}")

    conn.close()