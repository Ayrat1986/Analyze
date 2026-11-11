# ============================================================
# analysis/psych_rating/progress.py
# ============================================================
import os
from datetime import datetime
from analysis.common import _conn, REPORTS_DIR

def report_progress_curve():
    conn = _conn(); cur = conn.cursor(); path = os.path.join(REPORTS_DIR, "progress_curve.txt")
    with open(path, "w", encoding="utf-8") as f:
        def w(line=""): print(line); f.write(line + "\n")
        w("=" * 60); w(" PROGRESS CURVE (рейтинг, форма, тренд)"); w("=" * 60); w()

        w("📊 СЕКЦИЯ 1: РЕЙТИНГ КАЖДЫЕ 100 ПАРТИЙ")
        cur.execute("SELECT end_time, my_rating FROM games WHERE is_lag=0 AND is_cheater=0 AND my_rating > 0 ORDER BY end_time")
        rows = cur.fetchall()
        if len(rows) < 100: w("  ⚠️ Мало данных.")
        else:
            w(f"  {'Партия':<10} {'Дата':<12} {'Рейтинг':<10} {'Δ к пред.'}")
            prev_r = None
            for i in range(99, len(rows), 100):
                ts, r = rows[i]
                date = datetime.fromtimestamp(ts).strftime("%d.%m.%y")
                delta = f"{r - prev_r:+d}" if prev_r is not None else "—"
                w(f"  {i+1:<10} {date:<12} {r:<10} {delta}"); prev_r = r
            ts_last, r_last = rows[-1]
            date_last = datetime.fromtimestamp(ts_last).strftime("%d.%m.%y")
            delta_last = f"{r_last - prev_r:+d}" if prev_r is not None else "—"
            w(f"  {len(rows):<10} {date_last:<12} {r_last:<10} {delta_last}"); w()
            recent = rows[-500:] if len(rows) >= 500 else rows
            if len(recent) >= 50:
                r_start, r_end = recent[0][1], recent[-1][1]
                speed = (r_end - r_start) / len(recent) * 100
                w(f"  📊 Скорость (за {len(recent)} партий): {r_start} → {r_end} ({r_end-r_start:+d}), {speed:+.1f} п./100")
                if speed > 0:
                    need = 2800 - r_end
                    games_need = int(need / speed * 100) if speed > 0 else 0
                    w(f"  🎯 До 2800: {need} п. (~{games_need} партий)")
        w()

        w("📊 СЕКЦИЯ 2: КРИВАЯ ФОРМЫ (7 / 30 / 90 дней)")
        now_ts = int(datetime.now().timestamp())
        w(f"  {'Окно':<10} {'Партий':<8} {'Win%':<7} {'ACPL':<7} {'Форма'}")
        for label, days in [("7 дней", 7), ("30 дней", 30), ("90 дней", 90)]:
            cutoff_ts = now_ts - days * 86400
            cur.execute("SELECT COUNT(*), SUM(won), ROUND(AVG(acpl), 1) FROM games WHERE is_lag=0 AND is_cheater=0 AND end_time >= ?", (cutoff_ts,))
            cnt, wins, acpl = cur.fetchone()
            cnt = cnt or 0; wins = wins or 0; acpl = acpl or 0
            wr = wins / cnt * 100 if cnt else 0
            form = "🔥 ОТЛИЧНО" if (acpl <= 60 and wr >= 55) else ("✅ ХОРОШО" if (acpl <= 65 and wr >= 50) else ("❄️ ЯМА" if (acpl > 70 or wr < 45) else "➡️ НОРМА"))
            w(f"  {label:<10} {cnt:<8} {wr:<7.0f} {acpl:<7.1f} {form}")
        w()

        w("📊 СЕКЦИЯ 3: ТРЕНД ПО БЛОКАМ 50 ПАРТИЙ")
        cur.execute("SELECT end_time, acpl, acpl_middlegame, my_rating, opp_rating, won, draw FROM games WHERE is_lag=0 AND is_cheater=0 AND acpl > 0 ORDER BY end_time ASC")
        rows = cur.fetchall()
        if len(rows) < 50: w("  ⚠️ Мало данных.")
        else:
            w(f"  {'Блок':<12} {'Дата':<12} {'ACPL':<8} {'ACPL мит':<10} {'Ср. рейтинг':<12} {'Win%':<8}")
            blocks = [rows[i:i+50] for i in range(0, len(rows), 50)]
            prev_acpl = None; prev_rating = None
            for i, block in enumerate(blocks):
                if len(block) < 10: continue
                start_idx = i * 50 + 1; end_idx = start_idx + len(block) - 1
                date_str = datetime.fromtimestamp(block[-1][0]).strftime("%d.%m.%y")
                avg_acpl = sum(r[1] for r in block) / len(block)
                avg_mid = (sum(r[2] for r in block if r[2] > 0) / max(1, sum(1 for r in block if r[2] > 0)))
                avg_rating = (sum(r[3] for r in block if r[3] > 0) / max(1, sum(1 for r in block if r[3] > 0)))
                wins = sum(1 for r in block if r[5]); draws = sum(1 for r in block if r[6])
                wr = (wins + 0.5 * draws) / len(block) * 100
                acpl_trend = " ↓" if (prev_acpl is not None and avg_acpl < prev_acpl - 2) else (" ↑" if (prev_acpl is not None and avg_acpl > prev_acpl + 2) else "")
                rating_trend = " ↑" if (prev_rating is not None and avg_rating > prev_rating + 5) else (" ↓" if (prev_rating is not None and avg_rating < prev_rating - 5) else "")
                w(f"  {start_idx:>3}-{end_idx:<6} {date_str:<12} {avg_acpl:<7.1f}{acpl_trend:<2} {avg_mid:<9.1f} {avg_rating:<11.0f}{rating_trend:<2} {wr:<7.1f}")
                prev_acpl = avg_acpl; prev_rating = avg_rating
            if len(blocks) >= 2:
                first = blocks[0]; last = blocks[-1]
                first_acpl = sum(r[1] for r in first) / len(first); last_acpl = sum(r[1] for r in last) / len(last)
                w("  ✅ Точность РАСТЁТ." if last_acpl < first_acpl - 5 else ("  ⚠️ Точность ПАДАЕТ." if last_acpl > first_acpl + 5 else "  ➡️ Точность СТАБИЛЬНА."))
        w()

        w("📊 СЕКЦИЯ 4: НЕДЕЛЬНЫЙ ПРОГРЕСС (последние 8)")
        cur.execute("SELECT strftime('%Y-%W', datetime(end_time, 'unixepoch')) AS week, COUNT(*), ROUND(AVG(acpl_opening), 1), ROUND(AVG(acpl_middlegame), 1), ROUND(AVG(acpl_endgame), 1), SUM(won), SUM(draw) FROM games WHERE is_lag=0 AND is_cheater=0 GROUP BY week ORDER BY week DESC LIMIT 8")
        weeks = list(reversed(cur.fetchall()))
        w(f"  {'Неделя':<10} {'Игр':<6} {'Win%':<7} {'Деб':<7} {'Мит':<7} {'Энд':<7}")
        prev_mid = None
        for week, cnt, op, mid, end, wins, draws in weeks:
            wr = ((wins or 0) + 0.5 * (draws or 0)) / cnt * 100 if cnt else 0
            mark = ""
            if prev_mid is not None:
                d = (mid or 0) - prev_mid
                mark = " ↓" if d < -2 else (" ↑" if d > 2 else "")
            w(f"  {week:<10} {cnt:<6} {wr:<7.1f} {op or 0:<7.1f} {mid or 0:<7.1f}{mark} {end or 0:<7.1f}")
            prev_mid = mid or 0
        w()

        w("📊 СЕКЦИЯ 5: СРАВНЕНИЕ ПОСЛЕДНИХ 2 НЕДЕЛЬ")
        cur.execute("SELECT strftime('%Y-%W', datetime(end_time, 'unixepoch')) AS week, COUNT(*) FROM games WHERE is_lag=0 AND is_cheater=0 GROUP BY week HAVING COUNT(*) >= 10 ORDER BY week DESC LIMIT 2")
        last_weeks = cur.fetchall()
        if len(last_weeks) < 2: w("  ⚠️ Мало данных.")
        else:
            cur_week, prev_week = last_weeks[0][0], last_weeks[1][0]
            def week_stats(wk):
                cur.execute("SELECT COUNT(*), SUM(won), SUM(draw), ROUND(AVG(acpl), 1), ROUND(AVG(acpl_middlegame), 1), ROUND(AVG(accuracy), 1) FROM games WHERE is_lag=0 AND is_cheater=0 AND strftime('%Y-%W', datetime(end_time, 'unixepoch')) = ?", (wk,))
                row = cur.fetchone(); cnt = row[0] or 1
                return {"games": row[0] or 0, "wins": row[1] or 0, "draws": row[2] or 0, "win_rate": ((row[1] or 0) + 0.5 * (row[2] or 0)) / cnt * 100, "acpl": row[3] or 0, "mid": row[4] or 0, "acc": row[5] or 0}
            c = week_stats(cur_week); p = week_stats(prev_week)
            def delta_line(label, cv, pv, invert=False, fmt="{:.1f}"):
                d = cv - pv
                mark = "✅" if ((invert and d < 0) or (not invert and d > 0)) else ("⚠️" if ((invert and d > 0) or (not invert and d < 0)) else "➡️")
                w(f"  {label:<28} {fmt.format(cv):<10} {fmt.format(pv):<10} {d:+.1f} {mark}")
            w(f"  {'Метрика':<28} {cur_week:<10} {prev_week:<10} {'Δ'}")
            delta_line("Игр", c["games"], p["games"], fmt="{:.0f}"); delta_line("Win rate %", c["win_rate"], p["win_rate"])
            delta_line("ACPL общий", c["acpl"], p["acpl"], invert=True, fmt="{:.0f}"); delta_line("ACPL миттельшпиль", c["mid"], p["mid"], invert=True, fmt="{:.0f}")
            delta_line("Accuracy %", c["acc"], p["acc"])
            w("  📈 Миттельшпиль улучшился." if c["mid"] < p["mid"] - 3 else ("  📉 Миттельшпиль ухудшился." if c["mid"] > p["mid"] + 3 else "  ➡️ Миттельшпиль стабилен."))
    conn.close(); print(f"\n✅ {path}")