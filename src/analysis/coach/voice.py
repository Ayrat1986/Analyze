# ============================================================
# analysis/coach/voice.py — v22.1 (acpl_endgame без флагов)
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


def report_coach_voice():
    if not os.path.exists(DB_FILE):
        print("⚠️ coach_voice пропущен.")
        return
    conn = _conn()
    metrics = get_metrics(conn)
    matched = check_rules(metrics)
    matched.sort(key=lambda r: -r.get("priority", 1))
    cur = conn.cursor()

    # Базовые ACPL — как раньше
    cur.execute("""
        SELECT ROUND(AVG(acpl), 1), ROUND(AVG(acpl_middlegame), 1),
               ROUND(AVG(acpl_opening), 1), COUNT(*)
        FROM games WHERE is_lag=0 AND is_cheater=0 AND acpl > 0
    """)
    acpl_all, acpl_mid, acpl_op, n_games = cur.fetchone()
    acpl_all = acpl_all or 0
    acpl_mid = acpl_mid or 0
    acpl_op = acpl_op or 0
    n_games = n_games or 0

    # acpl_endgame БЕЗ флагов — согласовано с codex.py (endgame_weak) и endgame_skills.txt
    cur.execute("""
        SELECT ROUND(AVG(acpl_endgame), 1)
        FROM games
        WHERE is_lag=0 AND is_cheater=0 AND acpl_endgame > 0
          AND reason NOT LIKE '%просроч%' AND reason NOT LIKE '%time%'
    """)
    acpl_end = cur.fetchone()[0] or 0

    # Для справки — с флагами (как в endgame_skills «все»)
    cur.execute("""
        SELECT ROUND(AVG(acpl_endgame), 1)
        FROM games WHERE is_lag=0 AND is_cheater=0 AND acpl_endgame > 0
    """)
    acpl_end_all = cur.fetchone()[0] or 0

    cur.execute("SELECT COUNT(*), SUM(won), SUM(draw), ROUND(AVG(acpl), 1), ROUND(AVG(opp_rating), 1) FROM games WHERE is_lag=0 AND is_cheater=0 AND acpl > 0")
    row = cur.fetchone()
    n = row[0] or 1
    wins = row[1] or 0
    draws = row[2] or 0
    avg_acpl_recent = row[3] or 0
    avg_opp = row[4] or 0
    game_rating_val = calc_gr(avg_acpl_recent)
    perf_val = calc_perf(avg_opp, wins, draws, n)

    cur.execute("SELECT MIN(b.move_num) FROM blunders b JOIN games g ON g.url = b.game_url WHERE g.is_lag=0 AND g.is_cheater=0 AND b.is_my_blunder=1 AND b.is_berserk=0 AND b.is_instant=0 AND b.loss_cp > 150 GROUP BY g.url")
    first_moves = [r[0] for r in cur.fetchall() if r[0]]
    avg_first = sum(first_moves) / len(first_moves) if first_moves else 0

    path = os.path.join(REPORTS_DIR, "coach_voice.txt")
    with open(path, "w", encoding="utf-8") as f:
        def w(line=""):
            print(line)
            f.write(line + "\n")

        w("=" * 60)
        w(" 🎯 СОВЕТ ТРЕНЕРА НА СЕГОДНЯ")
        w("=" * 60)
        w(f"Сформирован: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        w()
        w("📊 ПРОФИЛЬ:")
        w(f"  ACPL: деб {acpl_op:.0f} / мит {acpl_mid:.0f} / энд {acpl_end:.0f}  (энд без флагов)")
        w(f"  ACPL энд (с флагами): {acpl_end_all:.0f}  — флаговые победы дают «грязную» цифру, техника в мат/сдаче чище")
        perf_label = (
            "оверперформер" if perf_val > game_rating_val + 50
            else ("недоигрываешь" if game_rating_val > perf_val + 50 else "баланс")
        )
        w(f"  GameR {game_rating_val:.0f} vs Perf {perf_val:.0f}  ({perf_label})")
        first_label = (
            "⚠️ дебют" if avg_first <= 10
            else ("⚠️ переход" if avg_first <= 20 else "миттельшпиль")
        )
        w(f"  1-й зевок: в среднем на {avg_first:.0f}-м ходу  ({first_label})")
        w()

        w("🎯 ДЕЛАТЬ СЕГОДНЯ:")
        if not matched:
            w("  1. Все показатели в норме — играй как обычно.")
            w("  2. Держи паузу 0.2 сек перед ходом.")
            w("  3. При +3.0 меняй ферзей.")
        else:
            for i, r in enumerate(matched[:3], 1):
                advice = r["advice"]
                if len(advice) > 110:
                    advice = advice[:107] + "..."
                w(f"  {i}. {advice}")
                w(f"     → {r['name']} (метрика: {r['metric_val']:.1f})")
        w()

        w("🚫 НЕ ДЕЛАТЬ:")
        negatives = []
        if acpl_mid > 70:
            negatives.append("Не углубляйся в тактику — у тебя не тактика, а миттельшпиль.")
        if avg_first > 0 and avg_first <= 12:
            negatives.append(f"Не играй на автомате до {avg_first + 5}-го хода.")
        if perf_val > game_rating_val + 100:
            negatives.append("Не считай, что ты уже 2600+ — Perf обманчив, смотри GameR.")
        if acpl_end > 80:
            negatives.append("Не доигрывай эндшпили по памяти — считай, а не угадывай.")
        if not negatives:
            negatives.append("Не расслабляйся — все метрики в норме, но тренд важнее.")
        for i, neg in enumerate(negatives[:3], 1):
            w(f"  {i}. {neg}")
        w()

        w("🗣️ МАНТРА ДНЯ:")
        if matched:
            mantra = matched[0].get("mantra", "")
            if mantra:
                w(f"  «{mantra}»")
            else:
                w("  «Играй не против соперника, а против хаоса в своей голове».")
        else:
            w("  «Спокойный ум видит скрытые тактические удары».")
        w()

    conn.close()
    print(f"\n✅ {path}")