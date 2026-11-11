# ============================================================
# analysis/middlegame/summary.py (v19.0)
# ============================================================
from analysis.common import report_context
from .common import _conn, get_base_filter, get_threshold

def report_summary():
    conn = _conn()
    cur = conn.cursor()
    base = get_base_filter()

    with report_context("middlegame_summary") as w:
        w.w_separator(title="СВОДКА ПО МИТТЕЛЬШПИЛЮ")
        w.w()

        cur.execute(f"""
            SELECT COUNT(*), ROUND(AVG(acpl_middlegame), 1),
                   ROUND(AVG(CASE WHEN won=1 THEN acpl_middlegame END), 1),
                   ROUND(AVG(CASE WHEN won=0 THEN acpl_middlegame END), 1)
            FROM games WHERE {base} AND acpl_middlegame > 0
        """)
        n, acpl_mid, acpl_win, acpl_loss = cur.fetchone()
        n = n or 0; acpl_mid = acpl_mid or 0; acpl_win = acpl_win or 0; acpl_loss = acpl_loss or 0
        THRESHOLD = get_threshold("acpl_mid_red", 75)

        w.w("📊 ACPL МИТТЕЛЬШПИЛЯ:")
        w.w(f"  Всего партий: {n}")
        w.w(f"  Средний ACPL: {acpl_mid:.0f} CP  ({'⚠️ выше нормы' if acpl_mid > THRESHOLD else '✅ в норме'})")
        w.w(f"  В победах:    {acpl_win:.0f} CP")
        w.w(f"  В поражениях: {acpl_loss:.0f} CP")
        w.w(f"  Разница:      {acpl_loss - acpl_win:+.0f} CP")
        w.w()

        cur.execute(f"""
            SELECT COUNT(*), ROUND(AVG(loss_cp))
            FROM blunders b JOIN games g ON g.url=b.game_url
            WHERE {base} AND b.is_my_blunder=1 AND b.is_berserk=0 AND b.is_instant=0 AND b.move_num BETWEEN 11 AND 30
        """)
        total_blunders, avg_loss = cur.fetchone()
        total_blunders = total_blunders or 0; avg_loss = avg_loss or 0

        w.w("📊 ЗЕВКИ В МИТТЕЛЬШПИЛЕ (11-30 ход):")
        w.w(f"  Всего зевков: {total_blunders}")
        if n > 0: w.w(f"  Зевков/партию: {total_blunders/n:.1f}")
        w.w(f"  Средняя потеря: {avg_loss:.0f} CP")
        w.w()

        cur.execute(f"""
            SELECT b.pattern_tag, COUNT(*)
            FROM blunders b JOIN games g ON g.url=b.game_url
            WHERE {base} AND b.is_my_blunder=1 AND b.is_berserk=0 AND b.is_instant=0 AND b.move_num BETWEEN 11 AND 30
            GROUP BY b.pattern_tag ORDER BY COUNT(*) DESC LIMIT 3
        """)
        pats = cur.fetchall()
        if pats:
            w.w("📊 ТОП-3 ПАТТЕРНА ЗЕВКОВ:")
            for tag, cnt in pats:
                w.w(f"  {tag:<25} {cnt:>4} ({cnt/total_blunders*100 if total_blunders else 0:.1f}%)")
            w.w()

        cur.execute(f"""
            SELECT COUNT(*), SUM(CASE WHEN won=0 AND draw=0 THEN 1 ELSE 0 END)
            FROM games WHERE {base} AND max_eval_advantage >= 300
        """)
        total_adv, lost_adv = cur.fetchone()
        total_adv = total_adv or 0; lost_adv = lost_adv or 0

        w.w("📊 СЛИВ ПЕРЕВЕСА (+3.0):")
        w.w(f"  Партий с перевесом: {total_adv}")
        if total_adv: w.w(f"  Слито (поражение):  {lost_adv} ({lost_adv/total_adv*100:.1f}%)")
        w.w()

        w.w("🎯 ГЛАВНЫЕ ВЫВОДЫ:")
        if acpl_mid > THRESHOLD:
            w.w(f"  1. ACPL миттельшпиля {acpl_mid:.0f} — главная дыра.")
        else:
            w.w(f"  1. ACPL миттельшпиля {acpl_mid:.0f} — в норме.")
        if total_adv and lost_adv/total_adv > 0.3:
            w.w(f"  2. Сливаешь {lost_adv/total_adv*100:.0f}% перевесов. Правило Бухгалтера!")
        if pats:
            top_pat, top_cnt = pats[0]
            w.w(f"  3. Самый частый паттерн зевков: {top_pat} ({top_cnt} раз).")
    conn.close()