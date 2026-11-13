# ============================================================
# analysis/coach/plan.py (v25.0)
# §1: убрано «5 партий подряд / стоп». Заменено на «17 партий → 15 мин»
#     (правило из PROJECT_RULES §1, не ограничение).
# ============================================================
import os
import sqlite3
from datetime import datetime
import _common

DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")
REPORTS_DIR = str(_common.REPORTS_DIR)


def _conn():
    return sqlite3.connect(DB_FILE)


def report_coach_plan_weekly():
    conn = _conn(); cur = conn.cursor()
    path = os.path.join(REPORTS_DIR, "coach_plan_weekly.txt")

    cur.execute("""
        SELECT ROUND(AVG(acpl_opening), 1), ROUND(AVG(acpl_middlegame), 1),
               ROUND(AVG(acpl_endgame), 1)
        FROM games WHERE is_lag=0 AND is_cheater=0
    """)
    op, mid, end = cur.fetchone()
    op = op or 0; mid = mid or 0; end = end or 0

    cur.execute("""
        SELECT COUNT(*) FROM games
        WHERE is_lag=0 AND is_cheater=0
          AND max_eval_advantage >= 300 AND won=0 AND draw=0
    """)
    sliv = cur.fetchone()[0] or 0

    cur.execute("""
        SELECT COUNT(*), ROUND(AVG(timeout_at_move), 0)
        FROM games WHERE is_lag=0 AND is_cheater=0 AND timeout_at_move IS NOT NULL
    """)
    tcnt, tmove = cur.fetchone()
    tcnt = tcnt or 0; tmove = tmove or 0

    cur.execute("""
        SELECT ROUND(AVG(momentum_after_blunder), 1)
        FROM games WHERE is_lag=0 AND is_cheater=0 AND momentum_after_blunder > 0
    """)
    mom = cur.fetchone()[0] or 0

    cur.execute("""
        SELECT COUNT(*) FROM blunders b JOIN games g ON g.url=b.game_url
        WHERE g.is_lag=0 AND g.is_cheater=0
          AND b.is_berserk=0 AND b.is_instant=0 AND b.is_my_blunder=1
    """)
    n_blunders = cur.fetchone()[0] or 0

    with open(path, "w", encoding="utf-8") as f:
        def w(line=""):
            print(line); f.write(line + "\n")
        w("=" * 60); w(" 🎯 ПЛАН НА НЕДЕЛЮ"); w("=" * 60); w()
        w("📊 ИСХОДНЫЕ:")
        w(f"  ACPL: деб {op:.0f}, мит {mid:.0f}, энд {end:.0f}")
        w(f"  Зевков: {n_blunders}, слив перевеса: {sliv}")
        w(f"  Просрочек: {tcnt} (пик на {tmove:.0f} ходу), моментум: {mom:.0f}")
        w()
        w("📋 ПЛАН:")
        w("  Д1 — Тактика (2ч): 50 задач на вилки + 20 связок")
        w("  Д2 — Дебюты (1ч): повтор репертуара, если ACPL деб > 60 → 2-3 шаблона")
        w("  Д3 — Миттельшпиль (2ч): правило 0.2 сек + Вектор атаки"
          if mid > 70 else "  Д3 — Миттельшпиль в норме")
        w("  Д4 — Психология (1ч): пауза 2 сек после зевка"
          if mom > 70 else "  Д4 — Отходчивость в норме")
        w("  Д5 — Слив перевеса (2ч): +3.0 → Бухгалтер (менять ферзей)"
          if sliv > 50 else "  Д5 — Слив перевеса не критичен")
        w("  Д6 — Часы (1ч): если <5 сек на 35-м — упрощай"
          if tcnt > 50 else "  Д6 — Часы в норме")
        w("  Д7 — Разбор: открыть dashboard_FINAL.txt, сравнить с прошлой неделей")
        w()
        w("🎯 ЦЕЛИ НА НЕДЕЛЮ:")
        if mid > 45:
            target_mid = max(40, mid - 5)
            w(f"  ACPL мит: {mid:.0f} → {target_mid:.0f}")
        else:
            w(f"  ACPL мит: {mid:.0f} (уже в норме)")
        w(f"  Зевки: {n_blunders} → {int(n_blunders*0.85)}")
        w(f"  Слив перевеса: {sliv} → {int(sliv*0.8)}")
        w()
        # §1: заменяем «5 партий / стоп» на правило выносливости
        w("ГЛАВНОЕ: После 17 партий подряд — перерыв 15 минут.")
        w("Играй в удовольствие. Рейтинг — тень.")

    conn.close(); print(f"\n✅ {path}")