# ============================================================
# analysis/opponents/weakness.py (v25.0)
# §4 (уточнение): opponent_deep анализирует ТОЛЬКО тех,
# кто в crushed_by.txt. Ищем паттерны, как они нас ломают.
# ============================================================
import os
from .common import _conn, _style_csv, REPORTS_DIR, PLAYER


def report_opponent_weakness():
    conn = _conn(); cur = conn.cursor()
    path = os.path.join(REPORTS_DIR, "opponent_weakness.txt")

    cur.execute("""
        SELECT acpl_opponent_total, won FROM games
        WHERE is_lag=0 AND is_cheater=0 AND acpl_opponent_total > 0
    """)
    rows = cur.fetchall()
    groups = {
        "ACPL < 60 (сильный)":       {"n": 0, "w": 0},
        "ACPL 60-75 (средний)":      {"n": 0, "w": 0},
        "ACPL 75-90 (слабый)":       {"n": 0, "w": 0},
        "ACPL > 90 (очень слабый)":  {"n": 0, "w": 0},
    }
    for acpl, won in rows:
        if acpl < 60: k = "ACPL < 60 (сильный)"
        elif acpl < 75: k = "ACPL 60-75 (средний)"
        elif acpl < 90: k = "ACPL 75-90 (слабый)"
        else: k = "ACPL > 90 (очень слабый)"
        groups[k]["n"] += 1
        if won:
            groups[k]["w"] += 1

    styles = _style_csv()

    with open(path, "w", encoding="utf-8") as f:
        def w(line=""):
            print(line); f.write(line + "\n")
        w("=" * 60); w(" OPPONENT WEAKNESS"); w("=" * 60)
        w("📊 ПО ACPL СОПЕРНИКА (чем выше ACPL соперника — тем он слабее):")
        for k, d in groups.items():
            if d["n"] == 0:
                continue
            w(f"  {k:<25} {d['n']:>4}п, {d['w']/d['n']*100:.1f}%")
        w()

        if styles:
            w("📊 ПО СТИЛЮ (из opponent_style.csv):")
            for s in sorted(styles, key=lambda x: -x["games"]):
                w(f"  {s['style']:<15} {s['games']:>3}п, {s['win_rate']:.1f}%, ACPL {s['my_acpl']:.0f}")
            w()
            best = max(styles, key=lambda x: x["win_rate"])
            worst = min(styles, key=lambda x: x["win_rate"])
            w("🎯 ВЕРДИКТ:")
            w(f"  Лучше всего: {best['style']} ({best['win_rate']:.0f}%)")
            w(f"  Хуже всего: {worst['style']} ({worst['win_rate']:.0f}%)")
        else:
            w("⚠️ opponent_style.csv не найден. Запусти 04_export_csv.py.")

    conn.close(); print(f"\n✅ {path}")


def report_crushed_by():
    conn = _conn(); cur = conn.cursor()
    path = os.path.join(REPORTS_DIR, "crushed_by.txt")

    cur.execute("""
        SELECT opp_username,
               ROUND(AVG(opp_rating)) as rating,
               COUNT(*) as games,
               SUM(won) as wins, SUM(draw) as draws,
               ROUND(AVG(acpl), 1) as my_acpl,
               ROUND(AVG(acpl_opponent_total), 1) as opp_acpl,
               (CAST(SUM(won) AS REAL) + 0.5 * SUM(draw)) / COUNT(*) AS my_score
        FROM games
        WHERE is_lag=0 AND is_cheater=0
          AND opp_username IS NOT NULL AND opp_username != ''
        GROUP BY opp_username
        HAVING games >= 5
           AND (CAST(SUM(won) AS REAL) + 0.5 * SUM(draw)) / games < 0.30
        ORDER BY games DESC
    """)
    rows = cur.fetchall()

    with open(path, "w", encoding="utf-8") as f:
        def w(line=""):
            print(line); f.write(line + "\n")
        w("=" * 60); w(" 🩸 ТЕ, КТО СИЛЬНЕЕ (score < 30%)"); w("=" * 60)
        w("Критерий: ты набираешь < 30% очков за >= 5 партий.")
        w()
        if not rows:
            w("✅ Таких нет.")
        else:
            w(f"  {'Соперник':<22} {'Рейт':<6} {'Игр':<5} {'W/D/L':<12} "
              f"{'Score%':<8} {'Мой ACPL':<10} {'Его ACPL'}")
            w("  " + "-" * 88)
            for opp, rating, g, wins, draws, my_acpl, opp_acpl, score in rows:
                wins = wins or 0
                draws = draws or 0
                losses = g - wins - draws
                score_pct = (score or 0) * 100
                w(f"  {opp[:20]:<22} {rating or 0:<6.0f} {g:<5} "
                  f"{wins}/{draws}/{losses:<8} {score_pct:<8.1f} "
                  f"{my_acpl or 0:<10.0f} {opp_acpl or 0:.0f}")
            w()
            w("💡 Как использовать:")
            w("  • Разбери 3-5 партий против каждого (08_psych_focus.py --review).")
            w("  • Ищи паттерн: один и тот же дебют? один и тот же тип ошибки?")
            w("  • Не пытайся 'победить их в их игре' — меняй дебют или план.")

    conn.close(); print(f"\n✅ {path}")


def report_opponent_deep():
    """
    v25.0 (уточнение §4): анализируем ТОЛЬКО тех, кто в crushed_by.
    Цель — раскрыть, где они видят наши слабые стороны (дебюты, тип позиции).
    """
    conn = _conn(); cur = conn.cursor()
    path = os.path.join(REPORTS_DIR, "opponent_deep.txt")

    # 1. Сначала получаем список тех, кто нас ломает
    cur.execute("""
        SELECT opp_username, COUNT(*) as g, SUM(won) as w, SUM(draw) as d
        FROM games
        WHERE is_lag=0 AND is_cheater=0 AND opp_username IS NOT NULL AND opp_username != ''
        GROUP BY opp_username
        HAVING g >= 5 AND (CAST(SUM(won) AS REAL) + 0.5 * SUM(draw)) / g < 0.30
        ORDER BY g DESC
    """)
    crushed = cur.fetchall()

    with open(path, "w", encoding="utf-8") as f:
        def w(line=""):
            print(line); f.write(line + "\n")
        w("=" * 60); w(" 🩸 РАЗБОР ТЕХ, КТО РАСКАЛЫВАЕТ"); w("=" * 60)
        w("Анализ только соперников из crushed_by.txt (score < 30%).")
        w("Ищем паттерн: в каких дебютах они ломают твою игру?\n")

        if not crushed:
            w("✅ Таких соперников нет.")
            conn.close()
            return

        w(f"Найдено 'раскалывающих': {len(crushed)}\n")

        for opp, g, wins, draws in crushed:
            wins = wins or 0
            draws = draws or 0
            score = (wins + 0.5 * draws) / g * 100

            w(f"♟️ {opp} ({g} партий, Score {score:.0f}%)")
            w("  Дебюты, где он тебя ломает:")

            # Ищем дебюты, где score против него < 30%
            cur.execute("""
                SELECT opening, COUNT(*) as g, SUM(won) as w, SUM(draw) as d
                FROM games
                WHERE opp_username = ? AND is_lag=0 AND is_cheater=0
                  AND opening IS NOT NULL AND opening != ''
                GROUP BY opening
                HAVING g >= 2 AND (CAST(SUM(won) AS REAL) + 0.5 * SUM(draw)) / g < 0.30
                ORDER BY g DESC
            """, (opp,))
            bad_openings = cur.fetchall()

            if bad_openings:
                for op, og, ow, od in bad_openings:
                    wr = ((ow or 0) + 0.5 * (od or 0)) / og * 100
                    w(f"    {op[:45]:<47} {og}п, Score {wr:.0f}%")
            else:
                w("    (нет явно слабых дебютов — проблема в миттельшпиле)")

            # Средний финальный перевес (по eval_final)
            cur.execute("""
                SELECT AVG(eval_final) FROM games
                WHERE opp_username = ? AND is_lag=0 AND is_cheater=0
            """, (opp,))
            avg_eval = cur.fetchone()[0]
            if avg_eval is not None and avg_eval < -200:
                w(f"  📉 Средний финальный перевес: {avg_eval/100:.1f} "
                  f"(ты часто доминируешь в начале)")
            w()

    conn.close(); print(f"\n✅ {path}")