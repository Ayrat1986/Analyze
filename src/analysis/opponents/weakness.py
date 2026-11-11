# ============================================================
# analysis/opponents/weakness.py — слабости, deep, crushed_by (v19.5)
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


def report_opponent_deep():
    conn = _conn(); cur = conn.cursor()
    path = os.path.join(REPORTS_DIR, "opponent_deep.txt")

    with open(path, "w", encoding="utf-8") as f:
        def w(line=""):
            print(line); f.write(line + "\n")
        w("=" * 60); w(" ПРОФИЛИ ТОП-10 СОПЕРНИКОВ"); w("=" * 60); w()

        cur.execute("SELECT ROUND(AVG(acpl), 1) FROM games WHERE is_lag=0 AND is_cheater=0")
        my_avg_acpl = cur.fetchone()[0] or 0
        w(f"Твой средний ACPL: {my_avg_acpl:.0f}")
        w()

        cur.execute("""
            SELECT opp_username, opp_rating, COUNT(*) AS games,
                   SUM(won) AS wins,
                   SUM(draw) AS draws,
                   ROUND(AVG(acpl), 1) AS my_acpl,
                   ROUND(AVG(acpl_opponent_total), 1) AS opp_acpl
            FROM games
            WHERE is_lag=0 AND is_cheater=0
              AND opp_username IS NOT NULL AND opp_username != ''
            GROUP BY opp_username
            ORDER BY games DESC LIMIT 10
        """)
        opps = cur.fetchall()

        for opp, rating, games, wins, draws, my_acpl, opp_acpl in opps:
            if not games:
                continue
            wins = wins or 0
            draws = draws or 0
            losses = games - wins - draws
            w(f"♟️ {opp} ({rating if rating else '?'}, {games} партий, W:{wins} D:{draws} L:{losses})")
            wr = wins / games * 100
            my_acpl = my_acpl if my_acpl is not None else 0
            opp_acpl = opp_acpl if opp_acpl is not None else 0

            acpl_delta = my_acpl - my_avg_acpl
            mark_acpl = ""
            if acpl_delta > 5: mark_acpl = " ⚠️ хуже среднего"
            elif acpl_delta < -5: mark_acpl = " ✅ лучше среднего"
            w(f"  Win rate: {wr:.0f}%")
            w(f"  Мой ACPL: {my_acpl:.0f} ({acpl_delta:+.0f}){mark_acpl}")
            w(f"  ACPL соперника: {opp_acpl:.0f}")

            cur.execute("""
                SELECT opening, COUNT(*), SUM(won)
                FROM games
                WHERE is_lag=0 AND is_cheater=0 AND opp_username = ?
                  AND opening IS NOT NULL AND opening != ''
                GROUP BY opening HAVING COUNT(*) >= 2
                ORDER BY COUNT(*) DESC LIMIT 5
            """, (opp,))
            openings = cur.fetchall()
            if openings:
                w("  Дебюты:")
                for op, g, wr_ in openings:
                    w(f"    {op[:40]:<42} {g}п, {wr_:.0f}поб")
            w()

        w("🎯 ВЕРДИКТ:")
        w("  Против кого win rate < 40% — разбери 3 партии (08_psych_focus.py --review --url).")
        w("  В каких дебютах чаще проигрываешь — избегай или учи.")

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