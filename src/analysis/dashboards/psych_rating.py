# ============================================================
# analysis/dashboards/psych_rating.py (v26.3)
# FIX: Объединены дублирующиеся функции. Добавлен вывод Клинков и чтение REPORTS.
# ============================================================
import os
import sqlite3
import json
from datetime import datetime, timezone, timedelta
import _common
from analysis.common import report_context, window_cutoff_ts, read_report_file
from core.метрики import game_rating, speed_rating, combined_rating

REPORTS = [
    ("bullet_stats_report.txt", "📊 BULLET STATS"),
    ("progress_curve.txt", "📈 PROGRESS CURVE"),
    ("stability.txt", "🎖️ СТАБИЛЬНОСТЬ"),
    ("game_rating_vs_perf.txt", "🚀 GAME RATING vs PERF"),
    ("potential_tracker.txt", "🚀 АНАЛИЗ ПОТЕНЦИАЛА"),
    ("micro_sessions.txt", "⚡ МИКРО-СЕССИИ"),
]

DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")


def get_blade_state(combr):
    if combr >= 2650: return "🗡️ Острый Клинок"
    if combr >= 2550: return "⚔️ Боевой Клинок"
    if combr >= 2450: return "🪵 Тупеющий Клинок"
    if combr >= 2300: return "🧱 Тупой Клинок"
    return "💀 Сломанный Клинок"


def build_psych_rating(w):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    
    w.w_separator(title="🧠 РЕЙТИНГ И ПРОГРЕСС")
    w.w("Файл: 06_psych_rating.txt")
    w.w("Источник: 10_psych_rating.py")
    w.w()

    w.w_separator(title="РЕЙТИНГОВЫЕ МЕТРИКИ И СОСТОЯНИЕ")
    
    # 1. Текущий CombR (за последние 30 дней)
    cutoff_30 = window_cutoff_ts(30)
    cur.execute("""
        SELECT ROUND(AVG(acpl), 1), ROUND(AVG(acpl_middlegame), 1), 
               COUNT(*), ROUND(AVG(momentum_after_blunder), 1)
        FROM games
        WHERE is_lag=0 AND is_cheater=0 AND end_time >= ? AND acpl > 0
    """, (cutoff_30,))
    acpl_30, acpl_mid_30, n_30, mom = cur.fetchone()
    acpl_30 = acpl_30 or 0
    n_30 = n_30 or 0
    
    # Расчет скорости
    cur.execute("""
        SELECT clocks, white FROM games 
        WHERE is_lag=0 AND is_cheater=0 AND end_time >= ? AND clocks IS NOT NULL AND clocks != '[]'
    """, (cutoff_30,))
    from _chess_utils import parse_time_spent
    times = []
    player = _common.CONFIG.get("player", "")
    for clocks_raw, white in cur.fetchall():
        try:
            clocks = json.loads(clocks_raw)
            is_white = (white == player)
            t = parse_time_spent(clocks, is_white)
            if t: times.extend(t)
        except Exception: 
            pass
        
    avg_time = sum(times) / len(times) if times else 0
    g_r = game_rating(acpl_30)
    s_r = speed_rating(avg_time)
    combr = combined_rating(g_r, s_r)
    
    blade = get_blade_state(combr)

    w.w(f" 🗡️ ТЕКУЩЕЕ СОСТОЯНИЕ (30 дней): {blade}")
    w.w(f"    CombR: {combr:.0f}  (GameR {g_r:.0f} + SpeedR {s_r:.0f})")
    w.w()
    
    w.w(" 📊 БАЗОВЫЕ МЕТРИКИ:")
    w.w(f"    ACPL: {acpl_30:.1f} CP (мит: {acpl_mid_30:.1f})")
    w.w(f"    Скорость: {avg_time:.2f} сек/ход")
    
    if mom is not None:
        w.w(f"    Моментум после зевка: {mom:.1f} CP")
    else:
        w.w(f"    Моментум после зевка: нет данных (N=0)")
    w.w()

    w.w(" 💡 РАСШИФРОВКА КЛИНКОВ:")
    w.w("    Острый (≥2650): Все процессы на пике.")
    w.w("    Боевой (2550-2649): Рабочий оптимум. Твоя цель.")
    w.w("    Тупеющий (2450-2549): Появление спешки или залипания.")
    w.w("    Тупой (2300-2449): Мысль 'надо играть' вместо 'хочу бить'.")
    w.w("    Сломанный (<2300): Истощение. Рейтинг-партии запрещены.")
    w.w()

    conn.close()

    # Вывод остальных отчетов
    for filename, title in REPORTS:
        w.w_separator(title=f"{title} (из {filename})")
        lines = read_report_file(filename)
        if lines is None:
            w.w(f"⚠️ Файл {filename} не найден")
        elif not lines or (len(lines) == 1 and not lines[0].strip()):
            w.w(f"⚠️ Файл {filename} пуст")
        else:
            for line in lines:
                w.w(line)
        w.w()
