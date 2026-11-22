# ============================================================
# analysis/coach/voice.py — v26.3
# v26.3: ACPL энд с явным контекстом (98 профиль / 63 срез).
#        ДЕЛАТЬ СЕГОДНЯ делится на P1 / P2 / фон.
#        Помечаются малые выборки (N<10) в matched-правилах.
# v26.2: убран дублирующий заголовок, удалён пункт «не углубляйся в тактику».
# ============================================================
import os
import sqlite3
from datetime import datetime

import _common
from core.метрики import game_rating as calc_gr, perf_rating as calc_perf
from .codex import get_metrics, check_rules

DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")
REPORTS_DIR = str(_common.REPORTS_DIR)


def _conn():
    return sqlite3.connect(DB_FILE)


def _reliability(n, unit="партий"):
    """Статус надёжности по N. См. PROJECT_RULES §29 и рекомендации аудита."""
    if n < 10:
        return f"наблюдение, N={n} {unit} — недостаточно для вывода"
    if n < 30:
        return f"предварительный сигнал, N={n} {unit}"
    return f"рабочий сигнал, N={n} {unit}"


def report_coach_voice():
    if not os.path.exists(DB_FILE):
        print("⚠️ coach_voice пропущен.")
        return
    conn = _conn()
    metrics = get_metrics(conn)
    matched = check_rules(metrics)
    matched.sort(key=lambda r: -r.get("priority", 1))

    cur = conn.cursor()

    # Профиль 90 дней, без флагов — базовый ACPL
    cur.execute("""
        SELECT ROUND(AVG(acpl), 1), ROUND(AVG(acpl_middlegame), 1),
               ROUND(AVG(acpl_opening), 1), COUNT(*)
        FROM games WHERE is_lag=0 AND is_cheater=0 AND acpl > 0
          AND end_time >= strftime('%s', 'now', '-90 days')
    """)
    acpl_all, acpl_mid, acpl_op, n_games_90 = cur.fetchone()
    acpl_all = acpl_all or 0
    acpl_mid = acpl_mid or 0
    acpl_op = acpl_op or 0
    n_games_90 = n_games_90 or 0

    # ACPL энд: профиль 90 дней БЕЗ флагов
    cur.execute("""
        SELECT ROUND(AVG(acpl_endgame), 1), COUNT(*) FROM games
        WHERE is_lag=0 AND is_cheater=0 AND acpl_endgame > 0
          AND timeout_at_move IS NULL
          AND end_time >= strftime('%s', 'now', '-90 days')
    """)
    acpl_end_90, n_end_90 = cur.fetchone()
    acpl_end_90 = acpl_end_90 or 0
    n_end_90 = n_end_90 or 0

    # ACPL энд: недельный срез, ВСЕ партии (с флагами)
    cur.execute("""
        SELECT ROUND(AVG(acpl_endgame), 1), COUNT(*) FROM games
        WHERE is_lag=0 AND is_cheater=0 AND acpl_endgame > 0
          AND end_time >= strftime('%s', 'now', '-7 days')
    """)
    acpl_end_7, n_end_7 = cur.fetchone()
    acpl_end_7 = acpl_end_7 or 0
    n_end_7 = n_end_7 or 0

    # Perf и GameR
    cur.execute("""
        SELECT COUNT(*), SUM(won), SUM(draw), ROUND(AVG(acpl), 1),
               ROUND(AVG(opp_rating), 1)
        FROM games WHERE is_lag=0 AND is_cheater=0 AND acpl > 0
    """)
    row = cur.fetchone()
    n = row[0] or 1
    wins = row[1] or 0
    draws = row[2] or 0
    avg_acpl_recent = row[3] or 0
    avg_opp = row[4] or 0
    game_rating_val = calc_gr(avg_acpl_recent)
    perf_val = calc_perf(avg_opp, wins, draws, n)
    delta_gr_perf = game_rating_val - perf_val

    # Первый зевок
    cur.execute("""
        SELECT MIN(b.move_num) FROM blunders b
        JOIN games g ON g.url = b.game_url
        WHERE g.is_lag=0 AND g.is_cheater=0
          AND b.is_my_blunder=1 AND b.is_berserk=0 AND b.is_instant=0
          AND b.loss_cp > 150
        GROUP BY g.url
    """)
    first_moves = [r[0] for r in cur.fetchall() if r[0]]
    avg_first = sum(first_moves) / len(first_moves) if first_moves else 0
    n_first = len(first_moves)

    path = os.path.join(REPORTS_DIR, "coach_voice.txt")
    with open(path, "w", encoding="utf-8") as f:
        def w(line=""):
            print(line)
            f.write(line + "\n")

        w(f"Сформирован: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        w()
        w(" ПРОФИЛЬ (90 дней, без флагов):")
        w(f"  ACPL: деб {acpl_op:.0f} / мит {acpl_mid:.0f} / энд {acpl_end_90:.0f}"
          f"  | N={n_games_90} партий")
        w(f"  Недельный срез (все партии): ACPL энд {acpl_end_7:.0f}  | N={n_end_7}")
        w("  Примечание: два значения выше — разные знаменатели. "
          "98 (90д, без флагов) и 63 (7д, все партии). Не смешивать.")

        perf_label = (
            "оверперформер" if delta_gr_perf > 50
            else ("недоигрываешь" if delta_gr_perf < -50 else "баланс")
        )
        w(f"  GameR {game_rating_val:.0f} vs Perf {perf_val:.0f} "
          f"(Δ={delta_gr_perf:+.0f}, {perf_label})")

        first_label = (
            "⚠️ дебют" if avg_first <= 10
            else ("⚠️ переход" if avg_first <= 20 else "миттельшпиль")
        )
        w(f"  1-й зевок: {avg_first:.0f}-й ход ({first_label}); {_reliability(n_first, 'партий')}")
        w()

        w(" ДЕЛАТЬ СЕГОДНЯ:")
        if not matched:
            w("  P1: нет — все показатели в норме.")
            w("  P2: пауза 0.2 сек перед ходом.")
            w("  Фон: при +3.0 не менять ферзей по шаблону, держать ритм.")
        else:
            top = matched[:3]
            # P1 — первый матч
            r0 = top[0]
            adv0 = r0.get("advice", "—")
            w(f"  P1 ({r0.get('name', '?')}, метрика {r0.get('metric_val', 0):.1f}):")
            w(f"    {adv0[:160]}")
            # P2 — следующие два
            for r in top[1:3]:
                adv = r.get("advice", "—")
                w(f"  P2 ({r.get('name', '?')}, {r.get('metric_val', 0):.1f}):")
                w(f"    {adv[:160]}")
            w("  Фон: держать паузу 0.2 сек на ходах 10–15 и 21–25.")
        w()

        w(" НЕ ДЕЛАТЬ:")
        negatives = []
        if avg_first > 0 and avg_first <= 12:
            negatives.append(f"Не играй на автомате до {avg_first + 5}-го хода.")
        if perf_val > game_rating_val + 100:
            negatives.append("Не считай, что ты уже 2600+ — Perf обманчив, смотри GameR.")
        if acpl_end_90 > 80:
            negatives.append("Не доигрывай эндшпили по памяти — считай, а не угадывай.")
        if not negatives:
            negatives.append("Не расслабляйся — все метрики в норме, но тренд важнее.")
        for i, neg in enumerate(negatives[:3], 1):
            w(f"  {i}. {neg}")
        w()

        w(" МАНТРА ДНЯ:")
        if matched and matched[0].get("mantra"):
            w(f"  «{matched[0]['mantra']}»")
        else:
            w("  «Спокойный ум видит скрытые тактические удары».")
        w()

    conn.close()
    print(f"\n✅ {path}")
