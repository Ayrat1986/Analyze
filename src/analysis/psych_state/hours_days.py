# ============================================================
# analysis/psych_state/hours_days.py (v19.1)
# ============================================================
from analysis.common import report_context
from .common import _conn

def run_hours_days():
    conn = _conn(); cur = conn.cursor()
    MIN_N = 20

    with report_context("hours_overview") as w:
        w.w_separator(title="HOURS OVERVIEW (часы, дни, против сильных)")
        w.w(f"Фильтр значимости: n ≥ {MIN_N} партий в категории.\n")

        w.w("📊 СЕКЦИЯ 1: БУДНИ vs ВЫХОДНЫЕ")
        w.w(f"  {'Тип дня':<12} {'Партий':<8} {'Win%':<8} {'ACPL':<8} {'Зев/парт':<10}")
        w.w("  " + "-" * 50)
        for label, cond in [
            ("Будни", "strftime('%w', datetime(end_time, 'unixepoch', '+3 hours')) IN ('1','2','3','4','5')"),
            ("Выходные", "strftime('%w', datetime(end_time, 'unixepoch', '+3 hours')) IN ('0','6')"),
        ]:
            cur.execute(f"SELECT COUNT(*), SUM(won), ROUND(AVG(acpl), 1) FROM games WHERE is_lag=0 AND is_cheater=0 AND {cond}")
            cnt, wins, acpl = cur.fetchone()
            cnt = cnt or 0; wins = wins or 0; acpl = acpl or 0
            cur.execute(f"SELECT COUNT(*) FROM blunders b JOIN games g ON g.url=b.game_url WHERE g.is_lag=0 AND g.is_cheater=0 AND {cond} AND b.is_berserk=0 AND b.is_instant=0 AND b.is_my_blunder=1")
            bl = cur.fetchone()[0] or 0
            wr = wins / cnt * 100 if cnt else 0
            w.w(f"  {label:<12} {cnt:<8} {wr:<8.1f} {acpl:<8.1f} {bl/cnt if cnt else 0:<10.1f}")
        w.w()

        w.w(f"📊 СЕКЦИЯ 2: ЧАСЫ (только n ≥ {MIN_N})")
        cur.execute("SELECT strftime('%H', datetime(end_time, 'unixepoch', '+3 hours')) AS hour, COUNT(*), SUM(won), ROUND(AVG(acpl), 1) FROM games WHERE is_lag=0 AND is_cheater=0 GROUP BY hour HAVING COUNT(*) >= ? ORDER BY hour", (MIN_N,))
        hour_rows = cur.fetchall()
        if not hour_rows:
            w.w(f"  ⚠️ Мало данных.")
        else:
            for hr, cnt, wins, acpl in hour_rows:
                w.w(f"  {hr}:00  {cnt:<8} {(wins or 0)/cnt*100:<8.1f} {acpl or 0:<8.1f}")
        w.w()

        w.w(f"📊 СЕКЦИЯ 3: ДНИ НЕДЕЛИ (n ≥ {MIN_N})")
        cur.execute("SELECT strftime('%w', datetime(end_time, 'unixepoch', '+3 hours')) AS dow, COUNT(*), SUM(won), ROUND(AVG(acpl), 1) FROM games WHERE is_lag=0 AND is_cheater=0 GROUP BY dow HAVING COUNT(*) >= ? ORDER BY dow", (MIN_N,))
        day_names = {"0": "Воскресенье", "1": "Понедельник", "2": "Вторник", "3": "Среда", "4": "Четверг", "5": "Пятница", "6": "Суббота"}
        for dow, cnt, wins, acpl in cur.fetchall():
            w.w(f"  {day_names.get(dow, '?'):<14} {cnt:<8} {(wins or 0)/cnt*100:<8.1f} {acpl or 0:<8.1f}")
        w.w()

        w.w("🎯 ИТОГОВЫЙ ВЕРДИКТ:")
        w.w("  Смотри на разброс ACPL по часам. Если разница < 3 CP — время суток не влияет.")

    conn.close()