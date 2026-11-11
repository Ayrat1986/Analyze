# ============================================================
# analysis/psych_state/endurance.py (v19.1)
# ============================================================
import os
import statistics
from collections import defaultdict
from datetime import datetime
from core.пороги import get as get_threshold
from analysis.common import report_context
from .common import _conn, REPORTS_DIR

def report_endurance():
    conn = _conn(); cur = conn.cursor()

    cur.execute("""
        SELECT date(end_time, 'unixepoch', '+3 hours') AS day,
               end_time, acpl, accuracy, won, acpl_endgame
        FROM games
        WHERE is_lag=0 AND is_cheater=0 AND acpl > 0
        ORDER BY day, end_time
    """)
    rows = cur.fetchall()
    
    with report_context("endurance") as w:
        w.w_separator(title="ENDURANCE: выносливость по номеру партии в дне")
        w.w("Секция 1 — общая точность. Секция 2 — ACPL эндшпиля (усталость решений).\n")
        
        if not rows:
            w.w("⚠️ Нет данных для endurance.")
            conn.close(); return

        days = defaultdict(list)
        for day, end_time, acpl, acc, won, acpl_end in rows:
            days[day].append((end_time, acpl, acc or 0, won, acpl_end or 0))

        order = ["1-5", "6-10", "11-20", "21-30", "31-50", "51-100", "101+"]

        def bucket_name(i):
            if i <= 5: return "1-5"
            if i <= 10: return "6-10"
            if i <= 20: return "11-20"
            if i <= 30: return "21-30"
            if i <= 50: return "31-50"
            if i <= 100: return "51-100"
            return "101+"

        b_all = {k: {"n": 0, "acpl_sum": 0.0, "acc_sum": 0.0, "wins": 0} for k in order}
        b_end = {k: {"n": 0, "acpl_sum": 0.0, "wins": 0} for k in order}

        for day, games in days.items():
            for i, (end_time, acpl, acc, won, acpl_end) in enumerate(games, 1):
                k = bucket_name(i)
                b_all[k]["n"] += 1; b_all[k]["acpl_sum"] += acpl; b_all[k]["acc_sum"] += acc
                if won: b_all[k]["wins"] += 1
                if acpl_end > 0:
                    b_end[k]["n"] += 1; b_end[k]["acpl_sum"] += acpl_end
                    if won: b_end[k]["wins"] += 1

        w.w(f"  {'Партия №':<12} {'Игр':<8} {'ACPL':<8} {'Accuracy':<10} {'ACPL энд':<10} {'Win%':<8}")
        w.w("  " + "-" * 65)
        base_acpl = b_all["1-5"]["acpl_sum"] / b_all["1-5"]["n"] if b_all["1-5"]["n"] else 0

        for k in order:
            d = b_all[k]
            if d["n"] == 0: continue
            avg = d["acpl_sum"] / d["n"]
            acc = d["acc_sum"] / d["n"]
            wr = d["wins"] / d["n"] * 100
            de = b_end[k]
            end_avg = de["acpl_sum"] / de["n"] if de["n"] else 0
            delta = avg - base_acpl
            mark = ""
            if k == "1-5": mark = "  ← база"
            elif delta > 10: mark = f"  ⚠️ +{delta:.0f} CP — предел"
            elif delta > 5: mark = f"  ⚠️ +{delta:.0f} CP — просадка"
            w.w(f"  {k:<12} {d['n']:<8} {avg:<8.1f} {acc:<10.1f} {end_avg:<10.1f} {wr:<8.1f}{mark}")
        w.w()

        w.w("🎯 ВЕРДИКТ:")
        if base_acpl:
            limit = None
            for k in order[1:]:
                d = b_all[k]
                if d["n"] > 0 and (d["acpl_sum"] / d["n"] - base_acpl) > 5:
                    limit = k; break
            if limit:
                w.w(f"  ⚠️ Твой предел выносливости: ~{limit} партий подряд.")
                w.w("  💡 Правило: после каждой 10-й партии — перерыв 15 минут.")
            else:
                w.w("  ✅ Выносливость в норме. Можно играть длинные сессии.")
    conn.close()

def report_behavior_tracker():
    conn = _conn(); cur = conn.cursor()
    SESSION_GAP_SEC = get_threshold("session_gap_minutes", 30) * 60

    cur.execute("SELECT url, end_time, won, draw, acpl, opp_rating, my_rating FROM games WHERE is_lag=0 AND is_cheater=0 AND acpl > 0 ORDER BY end_time ASC")
    rows = cur.fetchall()
    
    with report_context("behavior_tracker") as w:
        w.w_separator(title="ПОВЕДЕНИЕ ПО СЕССИЯМ (gap ≥ 30 мин)")
        
        if not rows:
            w.w("⚠️ Нет данных.")
            conn.close(); return

        sessions = []
        current = []
        prev_ts = None
        for url, end_time, won, draw, acpl, opp, my_r in rows:
            if prev_ts is not None and (end_time - prev_ts) > SESSION_GAP_SEC:
                if current: sessions.append(current)
                current = []
            current.append({"url": url, "end_time": end_time, "won": won or 0, "draw": draw or 0, "acpl": acpl or 0, "opp": opp or 0})
            prev_ts = end_time
        if current: sessions.append(current)

        n_sessions = len(sessions)
        n_games_total = sum(len(s) for s in sessions)

        len_dist = defaultdict(int)
        for s in sessions:
            L = len(s)
            if L == 1: len_dist["1"] += 1
            elif L <= 3: len_dist["2–3"] += 1
            elif L <= 5: len_dist["4–5"] += 1
            elif L <= 10: len_dist["6–10"] += 1
            elif L <= 20: len_dist["11–20"] += 1
            elif L <= 50: len_dist["21–50"] += 1
            else: len_dist["50+"] += 1

        by_pos = defaultdict(lambda: {"n": 0, "acpl_sum": 0, "wins": 0, "draws": 0})
        for s in sessions:
            for i, g in enumerate(s, 1):
                if i > 30: break
                p = by_pos[i]
                p["n"] += 1; p["acpl_sum"] += g["acpl"]
                if g["won"]: p["wins"] += 1
                if g["draw"]: p["draws"] += 1

        base_acpl = by_pos[1]["acpl_sum"] / by_pos[1]["n"] if by_pos[1]["n"] else 0
        limit_pos = None; limit_acpl = None
        for i in range(2, 31):
            p = by_pos[i]
            if p["n"] < 5: continue
            avg = p["acpl_sum"] / p["n"]
            if avg > base_acpl + 5:
                limit_pos = i; limit_acpl = avg; break

        tilt_sessions = []
        for s in sessions:
            if len(s) < 3: continue
            max_streak = cur_streak = 0
            for g in s:
                if not g["won"] and not g["draw"]:
                    cur_streak += 1; max_streak = max(max_streak, cur_streak)
                else: cur_streak = 0
            if max_streak >= 2:
                tilt_sessions.append({"len": len(s), "max_streak": max_streak, "acpl": sum(g["acpl"] for g in s) / len(s), "start": s[0]["end_time"]})

        w.w(f"Всего партий: {n_games_total}")
        w.w(f"Всего сессий: {n_sessions}")
        if n_sessions: w.w(f"Средняя длина: {n_games_total/n_sessions:.1f} партий")
        w.w()

        w.w("📊 РАСПРЕДЕЛЕНИЕ ПО ДЛИНЕ:")
        for k in ["1", "2–3", "4–5", "6–10", "11–20", "21–50", "50+"]:
            if k in len_dist: w.w(f"  {k:<10} {len_dist[k]:<8} {len_dist[k]/n_sessions*100:<7.1f}%")
        w.w()

        w.w("📊 ACPL ПО НОМЕРУ ПАРТИИ:")
        w.w(f"  {'№':<5} {'Партий':<8} {'ACPL':<7} {'ΔACPL':<8}")
        w.w("  " + "-" * 30)
        for i in range(1, 16):
            p = by_pos.get(i)
            if not p or p["n"] == 0: continue
            avg = p["acpl_sum"] / p["n"]
            delta = avg - base_acpl
            mark = " ⚠️" if i > 1 and delta > 10 else (" ⚠" if i > 1 and delta > 5 else "")
            w.w(f"  {i:<5} {p['n']:<8} {avg:<7.1f} {delta:+8.1f}{mark}")
        w.w()

        w.w("🎯 ПРЕДЕЛ ВЫНОСЛИВОСТИ:")
        if limit_pos:
            w.w(f"  ⚠️ С {limit_pos}-й партии в сессии ACPL стабильно растёт.")
            w.w(f"     База: {base_acpl:.0f} CP → На {limit_pos}-й: {limit_acpl:.0f} CP (+{limit_acpl - base_acpl:.0f})")
            w.w(f"  💡 Правило: после {limit_pos - 1} партий — перерыв 15 мин.")
        else:
            w.w("  ✅ Предел не найден — ACPL стабилен до 30-й партии.")
        w.w()

        w.w("📊 ТИЛЬТ-СЕССИИ (2+ поражения подряд):")
        if tilt_sessions:
            w.w(f"  Всего: {len(tilt_sessions)} из {n_sessions} ({len(tilt_sessions)/n_sessions*100:.0f}%)")
            for ts in sorted(tilt_sessions, key=lambda x: -x["max_streak"])[:5]:
                date = datetime.fromtimestamp(ts["start"]).strftime("%d.%m.%y")
                w.w(f"  Длина: {ts['len']:<4} Макс.серия: {ts['max_streak']:<4} Ср.ACPL: {ts['acpl']:<5.0f} {date}")
            w.w("\n  💡 Правило: после 2 поражений подряд — пауза 5 минут.")
        else:
            w.w("  ✅ Нет сессий с 2+ поражениями подряд.")

    conn.close()

def run_endurance():
    print("  1/2. Endurance")
    report_endurance()
    print("  2/2. Behavior Tracker")
    report_behavior_tracker()