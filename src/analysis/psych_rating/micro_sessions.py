# ============================================================
# analysis/psych_rating/micro_sessions.py
# ============================================================
import os, statistics
from datetime import datetime, timezone, timedelta
from analysis.common import _conn, REPORTS_DIR

def report_micro_sessions():
    conn = _conn(); cur = conn.cursor(); path = os.path.join(REPORTS_DIR, "micro_sessions.txt")
    cur.execute("""
        WITH ranked AS (SELECT url, end_time, acpl, won, draw, LAG(end_time) OVER (ORDER BY end_time) as prev_time FROM games WHERE is_lag=0 AND is_cheater=0 AND acpl > 0),
        sessions AS (SELECT *, SUM(CASE WHEN prev_time IS NULL OR (end_time - prev_time) > 1800 THEN 1 ELSE 0 END) OVER (ORDER BY end_time) as session_id FROM ranked)
        SELECT session_id, end_time, acpl, won, draw FROM sessions ORDER BY end_time ASC
    """)
    all_games = cur.fetchall()
    sessions = {}
    for sid, ts, acpl, won, draw in all_games:
        if sid not in sessions: sessions[sid] = []
        sessions[sid].append({"ts": ts, "acpl": acpl, "won": won, "draw": draw})
    last_sids = list(sessions.keys())[-10:]
    
    with open(path, "w", encoding="utf-8") as f:
        def w(line=""): print(line); f.write(line + "\n")
        w("=" * 60); w(" ⚡ МИКРО-СЕССИИ (Импульс и Вход в поток)"); w("=" * 60)
        
        ts_7d = int((datetime.now(timezone.utc) - timedelta(days=7)).timestamp())
        cur.execute("SELECT AVG(acpl) FROM games WHERE is_lag=0 AND is_cheater=0 AND acpl>0 AND end_time >= ?", (ts_7d,))
        avg_7d = cur.fetchone()[0] or 65

        for sid in reversed(last_sids):
            games = sessions[sid]; n = len(games)
            if n < 3: continue
            date_str = datetime.fromtimestamp(games[0]['ts']).strftime("%d.%m %H:%M")
            wins = sum(1 for g in games if g['won']); draws = sum(1 for g in games if g['draw']); win_rate = (wins + 0.5*draws) / n * 100
            mid = n // 2; first_half = games[:mid]; second_half = games[mid:]
            acpl_first = statistics.mean([g['acpl'] for g in first_half]); acpl_second = statistics.mean([g['acpl'] for g in second_half])
            wins_first = sum(1 for g in first_half if g['won']); wins_second = sum(1 for g in second_half if g['won'])
            acpl_improvement = acpl_first - acpl_second; win_improvement = wins_second - wins_first
            
            w(f"📅 Сессия: {date_str} | Партий: {n} | Win: {win_rate:.0f}%")
            w(f"   Первая половина: ACPL {acpl_first:.0f}, Побед {wins_first}")
            w(f"   Вторая половина: ACPL {acpl_second:.0f}, Побед {wins_second}")
            
            if acpl_improvement > 10 and win_improvement > 0: w("   🚀 ВЕРДИКТ: ВХОД В ПОТОК (Разогрелся и разнес)")
            elif acpl_improvement < -15 and win_improvement < 0: w("   📉 ВЕРДИКТ: ТИЛЬТ/УСТАЛОСТЬ (Сгорел к концу)")
            elif win_rate >= 70: w("   🔥 ВЕРДИКТ: ДОМИНАЦИЯ (Высокий винрейт всю сессию)")
            elif win_rate <= 30: w("   ❄️ ВЕРДИКТ: ХОЛОДНАЯ СЕССИЯ (Не пошло)")
            else: w("   ➡️ ВЕРДИКТ: СТАБИЛЬНАЯ ИГРА (Ровный пульс)")
            w(f"   ACPL сессии {statistics.mean([g['acpl'] for g in games]):.0f} (норма 7д: {avg_7d:.0f})"); w()

    conn.close(); print(f"\n✅ {path}")