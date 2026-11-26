# ============================================================
# analysis/coach/plan.py — v26.3
# v26.3: N+числитель+знаменатель для 93.1% и 20%.
#        Слив +3.0: две доли (от всех партий и от партий с +3.0).
#        Просрочки: исторический счётчик + нормировка 90д.
#        ACPL энд: два числа с явным контекстом.
#        План связан с данными (в норме — что сохранять).
# v26.2: абсолютные цели → темповые; убран дублирующий заголовок.
# ============================================================
import os
import sqlite3
from datetime import datetime, timezone, timedelta

import _common

DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")
REPORTS_DIR = str(_common.REPORTS_DIR)


def _conn():
    return sqlite3.connect(DB_FILE)


def _reliability(n, unit="партий"):
    if n < 10:
        return f"наблюдение, N={n} {unit} — недостаточно"
    if n < 30:
        return f"предварительный сигнал, N={n} {unit}"
    return f"рабочий сигнал, N={n} {unit}"


def report_coach_plan_weekly():
    conn = _conn()
    cur = conn.cursor()
    path = os.path.join(REPORTS_DIR, "coach_plan_weekly.txt")

    now = datetime.now(timezone.utc)
    ts_7d = int((now - timedelta(days=7)).timestamp())
    ts_90d = int((now - timedelta(days=90)).timestamp())

    # ACPL 90д, без флагов (совпадает с voice.py)
    cur.execute("""
        SELECT ROUND(AVG(acpl_opening), 1),
               ROUND(AVG(acpl_middlegame), 1),
               ROUND(AVG(acpl_endgame), 1),
               COUNT(*)
        FROM games WHERE is_lag=0 AND is_cheater=0
          AND timeout_at_move IS NULL
          AND end_time >= ?
    """, (ts_90d,))
    op, mid, end_90, n_90 = cur.fetchone()
    op = op or 0
    mid = mid or 0
    end_90 = end_90 or 0
    n_90 = n_90 or 0

    # ACPL энд 7д, все партии
    cur.execute("""
        SELECT ROUND(AVG(acpl_endgame), 1), COUNT(*)
        FROM games WHERE is_lag=0 AND is_cheater=0
          AND end_time >= ?
    """, (ts_7d,))
    end_7, n_7 = cur.fetchone()
    end_7 = end_7 or 0
    n_7 = n_7 or 0

    # ACPL
    cur.execute("""
        SELECT ROUND(AVG(acpl_opening), 1), ROUND(AVG(acpl_middlegame), 1),
               ROUND(AVG(acpl_endgame), 1), COUNT(*)
        FROM games WHERE is_lag=0 AND is_cheater=0 AND end_time >= ?
    """, (ts_90d,))
    op, mid, end, n_90 = cur.fetchone()
    op, mid, end, n_90 = op or 0, mid or 0, end or 0, n_90 or 0

    # Momentum
    cur.execute("""
        SELECT ROUND(AVG(momentum_after_blunder), 1)
        FROM games WHERE is_lag=0 AND is_cheater=0 AND momentum_after_blunder IS NOT NULL
    """)
    mom = cur.fetchone()[0]

    # Зевки за 7 дней
    cur.execute("""
        SELECT COUNT(DISTINCT g.url), COUNT(DISTINCT CASE WHEN b.is_my_blunder=1 THEN g.url END)
        FROM games g LEFT JOIN blunders b ON b.game_url = g.url
        WHERE g.is_lag=0 AND g.is_cheater=0 AND g.end_time >= ?
    """, (ts_7d,))
    total_7, blunder_7 = cur.fetchone()
    total_7 = total_7 or 0
    blunder_7 = blunder_7 or 0
    blunder_rate = (blunder_7 / total_7 * 100) if total_7 else 0

    # Слив +3.0 за 50 игр
    cur.execute("""
        SELECT COUNT(*), SUM(CASE WHEN max_eval_advantage >= 300 AND won=0 AND draw=0 THEN 1 ELSE 0 END)
        FROM (SELECT max_eval_advantage, won, draw FROM games WHERE is_lag=0 AND is_cheater=0 AND max_eval_advantage IS NOT NULL ORDER BY end_time DESC LIMIT 50)
    """)
    total_50, sliv_50 = cur.fetchone()
    sliv_rate = (sliv_50 / (total_50 or 1)) * 100

    # Таймауты (за 90 дней) с разделением по позиции
    cur.execute("""
        SELECT
            SUM(CASE WHEN flag_result = 'loss' THEN 1 ELSE 0 END) AS t_loss,
            SUM(CASE WHEN flag_result = 'win' THEN 1 ELSE 0 END) AS t_win,
            SUM(CASE WHEN flag_result = 'loss' AND max_eval_advantage >= 300 THEN 1 ELSE 0 END) AS t_loss_winning,
            SUM(CASE WHEN flag_result = 'win' AND min_eval_advantage <= -300 THEN 1 ELSE 0 END) AS t_win_losing
        FROM games
        WHERE is_lag=0 AND is_cheater=0 AND end_time >= ? AND reason = 'просрочка'
    """, (ts_90d,))
    t_loss, t_win, t_loss_win, t_win_lose = cur.fetchone()
    t_loss, t_win = t_loss or 0, t_win or 0
    t_loss_win, t_win_lose = t_loss_win or 0, t_win_lose or 0

    with open(path, "w", encoding="utf-8") as f:
        def w(line=""):
            f.write(line + "\n")
            print(line)

        w(" ИСХОДНЫЕ (темповые метрики с контекстом):")
        w(f"  ACPL профиль (90д): деб {op:.0f} / мит {mid:.0f} / энд {end:.0f} | {_reliability(n_90)}")
        
        mom_str = f"{mom:.1f} CP" if mom is not None else "нет данных (N=0) — не назначается"
        w(f"  Моментум после зевка: {mom_str}")
        w(f"  Партии с ≥1 критическим зевком (7д): {blunder_7}/{total_7} = {blunder_rate:.1f}% | {_reliability(total_7)}")
        w(f"  Слив преимущества +3.0 (50 партий): {sliv_50}/{total_50} = {sliv_rate:.1f}% | {_reliability(total_50)}")
        w()
        w(f"  Просрочки (90д):")
        w(f"    Проигрыши по времени: {t_loss} (из них из выигранной позиции: {t_loss_win})")
        w(f"    Победы по времени:    {t_win} (из них из проигранной позиции: {t_win_lose})")
        w()

        w(" ПЛАН НА НЕДЕЛЮ:")
        w("  Д1 — Тактика (2ч): 50 задач на вилки + 20 связок.")
        
        if op > 60: w(f"  Д2 — Дебюты (1ч): ACPL деб {op:.0f} > 60 → 2-3 шаблона.")
        else:       w(f"  Д2 — Дебюты: ACPL деб {op:.0f} в норме.")
        
        if mid > 70: w(f"  Д3 — Миттельшпиль (2ч): ACPL мит {mid:.0f} > 70 → правило 0.2 сек.")
        else:        w(f"  Д3 — Миттельшпиль: в норме.")
        
        if mom is not None and mom > 70: w(f"  Д4 — Психология (1ч): моментум {mom:.0f} > 70 → правило 3 секунд.")
        else:                            w(f"  Д4 — Отходчивость в норме.")
        
        if sliv_rate > 30: w(f"  Д5 — Слив +3.0 (2ч): {sliv_rate:.1f}% > 30% → 10 позиций на упрощение.")
        else:              w(f"  Д5 — Слив +3.0 в норме.")
        
        if end > 80: w(f"  Д6 — Эндшпиль (1ч): ACPL энд {end:.0f} > 80 → мат ладьёй.")
        else:        w(f"  Д6 — Эндшпиль в норме.")
        
        w("  Д7 — Отдых / анализ одной партии.")
        w()
        w(" ⚠️ Правило: после 17 партий — перерыв 15 мин.")

    conn.close()
    print(f"\n✅ {path}")
    
    # --- 1. Доля партий с зевком за 7 дней (числитель/знаменатель) ---
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
    total_7, blunder_7 = cur.fetchone()
    total_7 = total_7 or 0
    blunder_7 = blunder_7 or 0
    blunder_rate_7d = (blunder_7 / total_7 * 100) if total_7 else 0

    # --- 2. Слив +3.0: две доли за последние 50 партий ---
    cur.execute("""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN max_eval_advantage >= 300 THEN 1 ELSE 0 END) AS total_adv,
            SUM(CASE WHEN max_eval_advantage >= 300
                     AND won = 0 AND draw = 0 THEN 1 ELSE 0 END) AS sliv
        FROM (
            SELECT max_eval_advantage, won, draw
            FROM games
            WHERE is_lag=0 AND is_cheater=0
              AND max_eval_advantage IS NOT NULL
            ORDER BY end_time DESC
            LIMIT 50
        )
    """)
    total_50, total_adv_50, sliv_50 = cur.fetchone()
    total_50 = total_50 or 0
    total_adv_50 = total_adv_50 or 0
    sliv_50 = sliv_50 or 0
    sliv_rate_all = (sliv_50 / total_50 * 100) if total_50 else 0
    sliv_rate_adv = (sliv_50 / total_adv_50 * 100) if total_adv_50 else 0

    # --- 3. Просрочки: история + 90д ---
    cur.execute("""
        SELECT COUNT(*) FROM games
        WHERE is_lag=0 AND is_cheater=0 AND timeout_at_move IS NOT NULL
    """)
    timeouts_total = cur.fetchone()[0] or 0

    cur.execute("""
        SELECT COUNT(*),
               SUM(CASE WHEN timeout_at_move IS NOT NULL THEN 1 ELSE 0 END)
        FROM games
        WHERE is_lag=0 AND is_cheater=0 AND end_time >= ?
    """, (ts_90d,))
    total_90, timeouts_90 = cur.fetchone()
    total_90 = total_90 or 0
    timeouts_90 = timeouts_90 or 0
    timeout_rate_90 = (timeouts_90 / total_90 * 100) if total_90 else 0

    # Моментум после зевка
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

        w(" ИСХОДНЫЕ (темповые метрики с контекстом):")
        w(f"  ACPL профиль (90д, без флагов): деб {op:.0f} / мит {mid:.0f} / энд {end_90:.0f}"
          f"  | {_reliability(n_90)}")
        w(f"  ACPL энд (7д, все партии): {end_7:.0f}"
          f"  | {_reliability(n_7)} — другое окно, не сравнивать с 90д напрямую")
        w()
        w(f"  Партии с ≥1 критическим зевком (7д):")
        w(f"    {blunder_7}/{total_7} = {blunder_rate_7d:.1f}%  "
          f"| {_reliability(total_7)}")
        w()
        w(f"  Слив преимущества +3.0 (последние 50 партий):")
        w(f"    от всех партий:        {sliv_50}/{total_50} = {sliv_rate_all:.1f}%"
          f"  | {_reliability(total_50)}")
        w(f"    от партий с +3.0:      {sliv_50}/{total_adv_50} = {sliv_rate_adv:.1f}%"
          f"  | {_reliability(total_adv_50, 'партий с +3.0')}")
        w(f"    (для тренировки главное — вторая цифра)")
        w()
        w(f"  Просрочки (вся история): {timeouts_total} — "
          f"исторический счётчик, НЕ недельная цель.")
        w(f"  Просрочки (90д): {timeouts_90}/{total_90} = {timeout_rate_90:.1f}%"
          f"  | {_reliability(total_90)}")
        w()
        w(f"  Моментум после зевка: {mom:.0f} (сырой, справочно)")
        w()

        w(" ПЛАН НА НЕДЕЛЮ:")
        # Д1 — тактика (приоритетная по CODEX §4.4.1)
        w("  Д1 — Тактика (2ч): 50 задач на вилки + 20 связок. "
          "Вилки — главный паттерн зевков (CODEX §4.4.1).")
        # Д2 — дебюты
        if op > 60:
            w(f"  Д2 — Дебюты (1ч): ACPL деб {op:.0f} > 60 → 2-3 шаблона на повтор.")
        else:
            w(f"  Д2 — Дебюты: ACPL деб {op:.0f} в норме. Сохранять репертуар.")
        # Д3 — миттельшпиль
        if mid > 70:
            w(f"  Д3 — Миттельшпиль (2ч): ACPL мит {mid:.0f} > 70 → "
              f"правило 0.2 сек на ходах 10–15 и 21–25.")
        else:
            w(f"  Д3 — Миттельшпиль: ACPL мит {mid:.0f} в норме. Фоновый контроль.")
        # Д4 — психология
        if mom > 70:
            w(f"  Д4 — Психология (1ч): моментум после зевка {mom:.0f} > 70 → "
              f"правило «3 секунды» (CODEX §3.2.2).")
        else:
            w(f"  Д4 — Отходчивость в норме ({mom:.0f}). "
              f"Сохранять паузу 2 сек после ошибки — без отдельной тренировки.")
        # Д5 — слив +3.0
        if sliv_rate_adv > 30:
            w(f"  Д5 — Слив +3.0 (2ч): {sliv_rate_adv:.1f}% от партий с +3.0 > 30% → "
              f"10 позиций на упрощение, держать ритм.")
        else:
            w(f"  Д5 — Слив +3.0 в норме ({sliv_rate_adv:.1f}% от партий с +3.0). "
              f"Сохранять правило Бухгалтера.")
        # Д6 — эндшпиль
        if end_90 > 80:
            w(f"  Д6 — Эндшпиль (1ч): ACPL энд 90д {end_90:.0f} > 80 → "
              f"мат ладьёй и королём (премув).")
        else:
            w(f"  Д6 — Эндшпиль: ACPL энд 90д {end_90:.0f} в норме. "
              f"5 технических позиций, без отдельной цели.")
        w("  Д7 — Отдых / анализ одной партии.")
        w()
        w(" ⚠️ Правило: после 17 партий — перерыв 15 мин.")

    conn.close()
    print(f"\n✅ {path}")
