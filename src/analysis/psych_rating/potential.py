# ============================================================
# analysis/psych_rating/potential.py
# ============================================================
import os
import statistics
from datetime import datetime
from analysis.common import _conn, REPORTS_DIR
from core.метрики import game_rating

def get_percentile(data, percentile):
    if not data: return 0
    k = (len(data) - 1) * (percentile / 100)
    f = int(k); c = int(k) + 1
    if f == c: return data[f]
    d0 = data[f] * (c - k); d1 = data[c] * (k - f)
    return d0 + d1

def cutoff_ts(days: int) -> int:
    from datetime import timezone, timedelta
    return int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())

def report_potential_tracker():
    conn = _conn(); cur = conn.cursor()
    windows = [1, 2, 7, 30, 90]
    path = os.path.join(REPORTS_DIR, "potential_tracker.txt")

    with open(path, "w", encoding="utf-8") as f:
        def w(line=""):
            print(line); f.write(line + "\n")

        w("=" * 60); w(" 🚀 АНАЛИЗ ПОТЕНЦИАЛА И СГОРАНИЯ"); w("=" * 60)
        w(f"Сформирован: {datetime.now().strftime('%Y-%m-%d %H:%M')}"); w()

        for w_days in windows:
            ts = cutoff_ts(w_days)
            cur.execute("SELECT acpl FROM games WHERE is_lag=0 AND is_cheater=0 AND acpl > 0 AND end_time >= ?", (ts,))
            acpls = sorted([row[0] for row in cur.fetchall()])
            
            w("=" * 60); w(f" ОКНО: {w_days} ДНЕЙ (Партий: {len(acpls)})"); w("=" * 60)
            if not acpls:
                w("  ⚠️ Недостаточно данных."); w(); continue

            p10 = get_percentile(acpls, 10); p50 = get_percentile(acpls, 50); p90 = get_percentile(acpls, 90)
            avg_acpl = statistics.mean(acpls)
            gamr_avg = game_rating(avg_acpl); gamr_p10 = game_rating(p10)

            w("📊 1. ТВОЙ ПОТЕНЦИАЛ (GameR)")
            w(f"  Средний ACPL:     {avg_acpl:.1f} -> GameR {gamr_avg:.0f}")
            w(f"  Лучшие 10% (P10): {p10:.1f} -> GameR {gamr_p10:.0f}  <-- ПОТОЛОК")
            w(f"  Худшие 10% (P90): {p90:.1f} -> GameR {game_rating(p90):.0f}  <-- ТИЛЬТ")
            w(f"  Медиана (P50):    {p50:.1f} -> GameR {game_rating(p50):.0f}")
            w(f"  🎯 РАЗРЫВ: +{gamr_p10 - gamr_avg:.0f} пунктов"); w()

            cur.execute("""
                WITH ranked AS (SELECT url, end_time, acpl, LAG(end_time) OVER (ORDER BY end_time) as prev_time FROM games WHERE is_lag=0 AND is_cheater=0 AND acpl > 0 AND end_time >= ?),
                sessions AS (SELECT *, SUM(CASE WHEN prev_time IS NULL OR (end_time - prev_time) > 1800 THEN 1 ELSE 0 END) OVER (ORDER BY end_time) as session_id FROM ranked),
                game_nums AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY session_id ORDER BY end_time) as game_num FROM sessions)
                SELECT CASE WHEN game_num <= 5 THEN '1-5' WHEN game_num <= 10 THEN '6-10' WHEN game_num <= 20 THEN '11-20' WHEN game_num <= 30 THEN '21-30' WHEN game_num <= 50 THEN '31-50' ELSE '50+' END AS bucket, AVG(acpl) AS avg_acpl, COUNT(*) AS cnt FROM game_nums GROUP BY bucket
            """, (ts,))
            session_data = sorted(cur.fetchall(), key=lambda x: ["1-5", "6-10", "11-20", "21-30", "31-50", "50+"].index(x[0]))
            
            w("🔥 2. СГОРАНИЕ В СЕССИИ (Burnout)")
            w("  Номер партии   Ср. ACPL   GameR   Партий")
            w("  ------------------------------------------")
            base_gamr = 0
            for bucket, avg_a, cnt in session_data:
                gr = game_rating(avg_a)
                if bucket == '1-5':
                    base_gamr = gr
                    w(f"  {bucket:<14} {avg_a:<10.1f} {gr:<7.0f} {cnt}")
                else:
                    drop = base_gamr - gr
                    mark = " ⚠️" if drop > 50 else ""
                    w(f"  {bucket:<14} {avg_a:<10.1f} {gr:<7.0f} {cnt}{mark}")
            w(); w("  💡 Если GameR падает на 50+ — делай перерыв 15 минут."); w()

    conn.close()
    print(f"\n✅ {path}")