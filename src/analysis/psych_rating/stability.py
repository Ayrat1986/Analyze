# ============================================================
# analysis/psych_rating/stability.py
# ============================================================
import os, statistics
from analysis.common import _conn, REPORTS_DIR

def report_stability():
    conn = _conn(); cur = conn.cursor(); path = os.path.join(REPORTS_DIR, "stability.txt")
    with open(path, "w", encoding="utf-8") as f:
        def w(line=""): print(line); f.write(line + "\n")
        w("=" * 60); w(" STABILITY (разброс ACPL и индекс хаоса)"); w("=" * 60); w()

        w("📊 СЕКЦИЯ 1: РАЗБРОС ACPL")
        cur.execute("SELECT acpl FROM games WHERE is_lag=0 AND is_cheater=0 AND acpl > 0")
        vals = [r[0] for r in cur.fetchall()]
        if not vals: w("  ⚠️ Нет данных.")
        else:
            mean = statistics.mean(vals); median = statistics.median(vals)
            stdev = statistics.stdev(vals) if len(vals) > 1 else 0
            p10 = sorted(vals)[int(len(vals) * 0.1)]; p90 = sorted(vals)[int(len(vals) * 0.9)]
            w(f"  Средний:         {mean:.1f}"); w(f"  Медиана:         {median:.1f}"); w(f"  StdDev (разброс): {stdev:.1f}")
            w(f"  P10:             {p10:.1f}"); w(f"  P90:             {p90:.1f}"); w(f"  Размах P10–P90:  {p90 - p10:.1f}"); w()
            w("  ✅ Отлично. Ты стабилен." if stdev < 15 else ("  ➡️ Средне. Небольшие колебания." if stdev < 25 else "  ⚠️ Нестабильно. ACPL скачет. Нужна пауза после зевков."))
        w()

        w("📊 СЕКЦИЯ 2: ИНДЕКС ХАОСА (скачки eval >= 200 CP)")
        cur.execute("SELECT critical_moments FROM games WHERE is_lag=0 AND is_cheater=0 AND critical_moments IS NOT NULL AND acpl > 0")
        chaos_vals = [r[0] for r in cur.fetchall()]
        if not chaos_vals: w("  ⚠️ Нет данных.")
        else:
            avg_chaos = sum(chaos_vals) / len(chaos_vals)
            w(f"  Средний индекс хаоса: {avg_chaos:.1f}"); w(f"  Всего партий: {len(chaos_vals)}"); w()
            w(f"  ⚠️ Хаос {avg_chaos:.1f} — высокий. Партии 'рубилово'." if avg_chaos > 12 else (f"  ➡️ Хаос {avg_chaos:.1f} — средний." if avg_chaos > 7 else f"  ✅ Хаос {avg_chaos:.1f} — низкий. Позиционная игра."))
        w()

        w("📊 СЕКЦИЯ 3: РАСПРЕДЕЛЕНИЕ ПАРТИЙ ПО ТИПУ (по индексу хаоса)")
        cur.execute("SELECT url, white, black, won, draw, critical_moments, acpl, opp_rating FROM games WHERE is_lag=0 AND is_cheater=0 AND critical_moments IS NOT NULL AND acpl > 0")
        rows = cur.fetchall()
        if rows:
            groups = {"Спокойные (<4)": [], "Средние (4-8)": [], "Хаотичные (9-15)": [], "Американские горки (>15)": []}
            for r in rows:
                cm = r[5]
                if cm < 4: groups["Спокойные (<4)"].append(r)
                elif cm <= 8: groups["Средние (4-8)"].append(r)
                elif cm <= 15: groups["Хаотичные (9-15)"].append(r)
                else: groups["Американские горки (>15)"].append(r)
            w(f"  {'Тип':<25} {'Партий':<8} {'Win%':<7} {'ACPL':<7}")
            w("  " + "-" * 50)
            for name, g in groups.items():
                if not g: continue
                cnt = len(g); wins = sum(1 for r in g if r[3]); wr = wins / cnt * 100; acpl = sum(r[6] for r in g) / cnt
                w(f"  {name:<25} {cnt:<8} {wr:<7.1f} {acpl:<7.1f}")
        else: w("  ⚠️ Нет данных.")
    conn.close(); print(f"\n✅ {path}")