# ============================================================
# analysis/coach/plan.py — v26.2
# §1: «17 партий → 15 мин» (без изменений).
# Абсолютные цели заменены на темповые метрики.
# Убрано дублирование заголовка (его добавляет dashboards/coach.py).
# ============================================================
import os
import sqlite3
from datetime import datetime, timezone, timedelta

import _common

DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")
REPORTS_DIR = str(_common.REPORTS_DIR)


def _conn():
    return sqlite3.connect(DB_FILE)


def report_coach_plan_weekly():
    conn = _conn()
    cur = conn.cursor()
    path = os.path.join(REPORTS_DIR, "coach_plan_weekly.txt")

    now = datetime.now(timezone.utc)
    ts_7d = int((now - timedelta(days=7)).timestamp())

    # ACPL по фазам — как было
    cur.execute("""
        SELECT ROUND(AVG(acpl_opening), 1),
               ROUND(AVG(acpl_middlegame), 1),
               ROUND(AVG(acpl_endgame), 1)
        FROM games WHERE is_lag=0 AND is_cheater=0
    """)
    op, mid, end = cur.fetchone()
    op = op or 0
    mid = mid or 0
    end = end or 0

    # --- ТЕМПОВЫЕ МЕТРИКИ ВМЕСТО АБСОЛЮТНЫХ ---

    # 1. Доля партий с зевком за последние 7 дней (в %)
    cur.execute("""
        SELECT
            COUNT(DISTINCT g.url) AS total_games,
            COUNT(DISTINCT CASE WHEN b.is_my_blunder = 1
                                AND b.is_berserk = 0
                                AND b.is_instant = 0
                           THEN g.url END) AS games_with_blunder
        FROM games g
        LEFT JOIN blunders b ON b.game_url = g.url
        WHERE g.is_lag=0 AND g.is_cheater=0
          AND g.end_time >= ?
    """, (ts_7d,))
    total_g, games_blunder = cur.fetchone()
    total_g = total_g or 1
    blunder_rate_7d = (games_blunder / total_g * 100) if total_g else 0

    # 2. Доля партий со сливом перевеса +3.0 за последние 50 игр (в %)
    cur.execute("""
        SELECT COUNT(*),
               SUM(CASE WHEN max_eval_advantage >= 300 AND won=0 AND draw=0
                        THEN 1 ELSE 0 END)
        FROM (
            SELECT max_eval_advantage, won, draw
            FROM games
            WHERE is_lag=0 AND is_cheater=0
              AND max_eval_advantage IS NOT NULL
            ORDER BY end_time DESC
            LIMIT 50
        )
    """)
    total_50, sliv_50 = cur.fetchone()
    total_50 = total_50 or 1
    sliv_rate_50 = (sliv_50 / total_50 * 100) if total_50 else 0

    # Просрочки — справочно
    cur.execute("""
        SELECT COUNT(*), ROUND(AVG(timeout_at_move), 0)
        FROM games
        WHERE is_lag=0 AND is_cheater=0 AND timeout_at_move IS NOT NULL
    """)
    tcnt, tmove = cur.fetchone()
    tcnt = tcnt or 0
    tmove = tmove or 0

    cur.execute("""
        SELECT ROUND(AVG(momentum_after_blunder), 1)
        FROM games
        WHERE is_lag=0 AND is_cheater=0 AND momentum_after_blunder > 0
    """)
    mom = cur.fetchone()[0] or 0

    with open(path, "w", encoding="utf-8") as f:
        def w(line=""):
            print(line)
            f.write(line + "\n")

        # Заголовок НЕ пишем — его добавляет dashboards/coach.py
        w(" ИСХОДНЫЕ (темповые метрики):")
        w(f"  ACPL: деб {op:.0f}, мит {mid:.0f}, энд {end:.0f}")
        w(f"  Партий с зевком за 7 дней: {blunder_rate_7d:.1f}% (цель: ↓)")
        w(f"  Партий со сливом +3.0 за 50 игр: {sliv_rate_50:.1f}% (цель: ↓)")
        w(f"  Просрочек всего: {tcnt} (пик на {tmove:.0f} ходу), моментум: {mom:.0f}")
        w()

        w(" ПЛАН НА НЕДЕЛЮ:")
        w("  Д1 — Тактика (2ч): 50 задач на вилки + 20 связок")
        w("  Д2 — Дебюты (1ч): повтор репертуара, если ACPL деб > 60 → 2-3 шаблона")
        w("  Д3 — Миттельшпиль (2ч): правило 0.2 сек + Вектор атаки" if mid > 70 else "  Д3 — Миттельшпиль в норме")
        w("  Д4 — Психология (1ч): пауза 2 сек после зевка" if mom > 70 else "  Д4 — Отходчивость в норме")
        w("  Д5 — Слив перевеса (2ч): +3.0 → Бухгалтер (менять ферзей)" if sliv_rate_50 > 30 else "  Д5 — Слив перевеса в норме")
        w("  Д6 — Эндшпиль (1ч): мат ладьёй и королём (премув)" if end > 80 else "  Д6 — Эндшпиль в норме")
        w("  Д7 — Отдых / анализ одной партии")
        w()
        w(" ⚠️ Правило: после 17 партий — перерыв 15 мин.")

    conn.close()
    print(f"\n✅ {path}")
