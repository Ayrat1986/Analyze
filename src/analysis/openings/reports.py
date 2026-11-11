# ============================================================
# analysis/openings/reports.py — SQL-отчёты по дебютам (v19.0)
# ============================================================
import os
import sys
import sqlite3
from collections import defaultdict

import _common
from analysis.common import report_context

# Добавляем папку openings для прямого импорта common
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import REPORTS_DIR, AI_LATEST, PLAYER, _openings_csv

DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")

def _conn():
    return sqlite3.connect(DB_FILE)


def report_openings():
    rows = _openings_csv()
    with report_context("opening_recommendations") as w:
        w.w_separator(title="РЕКОМЕНДАЦИИ ПО ДЕБЮТАМ")
        
        if rows is None:
            w.w(f"❌ Не найден {AI_LATEST}/openings_stats.csv")
            w.w("   Запусти 04_export_csv.py --days 90")
            return
            
        MIN_GAMES = 10
        GOOD_WR, GOOD_ACPL = 55, 65
        BAD_WR, BAD_ACPL = 40, 75
        
        play, drop, neutral = [], [], []
        for r in rows:
            if r["games"] < MIN_GAMES:
                continue
            if r["win_rate"] >= GOOD_WR and (r["acpl"] == 0 or r["acpl"] <= GOOD_ACPL):
                play.append(r)
            elif r["win_rate"] <= BAD_WR and (r["acpl"] == 0 or r["acpl"] >= BAD_ACPL):
                drop.append(r)
            else:
                neutral.append(r)
                
        play.sort(key=lambda x: (-x["win_rate"], x["acpl"] or 999))
        drop.sort(key=lambda x: (x["win_rate"], -x["acpl"]))
        
        w.w(f"✅ ИГРАЙ ({len(play)}):")
        for r in play:
            w.w(f"  {r['eco']:<5} {r['opening'][:45]:<47} {r['games']:>3}п, {r['win_rate']:.0f}%, ACPL {r['acpl']:.0f}")
        w.w()
        w.w(f"❌ БРОСЬ ИЛИ УЧИ ЗАНОВО ({len(drop)}):")
        for r in drop:
            w.w(f"  {r['eco']:<5} {r['opening'][:45]:<47} {r['games']:>3}п, {r['win_rate']:.0f}%, ACPL {r['acpl']:.0f}")
        w.w()
        w.w(f"➡️ НЕЙТРАЛЬНО ({len(neutral)}):")
        for r in sorted(neutral, key=lambda x: -x["games"])[:10]:
            w.w(f"  {r['eco']:<5} {r['opening'][:45]:<47} {r['games']:>3}п, {r['win_rate']:.0f}%, ACPL {r['acpl']:.0f}")
        w.w()
        if drop:
            w.w("🎯 РЕКОМЕНДАЦИЯ:")
            w.w(f"  Убрать: {', '.join(r['eco'] for r in drop[:5])}")
            if play:
                w.w(f"  Добавить: {', '.join(r['eco'] for r in play[:3])}")


def report_repertoire():
    conn = _conn(); cur = conn.cursor()
    cur.execute("""
        SELECT white, won, eco, opening_line FROM games
        WHERE is_lag=0 AND is_cheater=0 AND opening_line != ''
    """)
    rows = cur.fetchall()
    
    by_color = {"white": defaultdict(lambda: {"n": 0, "w": 0}),
                "black": defaultdict(lambda: {"n": 0, "w": 0})}
    lines = {"white": defaultdict(lambda: {"n": 0, "w": 0}),
             "black": defaultdict(lambda: {"n": 0, "w": 0})}
             
    for white, won, eco, ol in rows:
        piw = (white.lower() == PLAYER.lower())
        color = "white" if piw else "black"
        eco3 = (eco or "?")[:3]
        by_color[color][eco3]["n"] += 1
        if won:
            by_color[color][eco3]["w"] += 1
        parts = ol.split()[:6]
        if len(parts) >= 4:
            key = " ".join(parts)
            lines[color][key]["n"] += 1
            if won:
                lines[color][key]["w"] += 1
                
    with report_context("opening_repertoire") as w:
        w.w_separator(title="OPENING REPERTOIRE")
        w.w(f"Всего партий: {len(rows)}")
        w.w()
        for color in ["white", "black"]:
            label = "ЗА БЕЛЫХ" if color == "white" else "ЗА ЧЁРНЫХ"
            w.w(f"♟️ {label}:")
            w.w(f"  {'ECO':<6} {'Партий':<8} {'Побед':<8} {'Win%':<8}")
            for eco3, d in sorted(by_color[color].items(), key=lambda x: -x[1]["n"])[:10]:
                if d["n"] >= 3:
                    w.w(f"  {eco3:<6} {d['n']:<8} {d['w']:<8} {d['w']/d['n']*100:<8.1f}")
            w.w()
            w.w("  🔝 ТОП-5 ЛИНИЙ:")
            for ln, d in sorted(lines[color].items(), key=lambda x: -x[1]["n"])[:5]:
                if d["n"] >= 3:
                    w.w(f"    {ln:<30} {d['n']}п, {d['w']/d['n']*100:.0f}%")
            w.w()
    conn.close()


def report_openings_winrate_trend():
    conn = _conn(); cur = conn.cursor()
    with report_context("openings_winrate_trend") as w:
        w.w_separator(title="ТРЕНД WIN RATE ПО ДЕБЮТАМ")
        w.w()
        
        cur.execute("""
            SELECT substr(eco, 1, 3) AS eco3, COUNT(*) AS games
            FROM games
            WHERE is_lag=0 AND is_cheater=0 AND eco IS NOT NULL AND length(eco) >= 3
            GROUP BY eco3 HAVING games >= 10
            ORDER BY games DESC LIMIT 10
        """)
        top_ecos = cur.fetchall()
        
        for eco3, total_games in top_ecos:
            w.w(f"\n♟️ {eco3} ({total_games} партий):")
            cur.execute("""
                SELECT strftime('%Y-%W', datetime(end_time, 'unixepoch')) AS week,
                       COUNT(*) AS games,
                       SUM(won) AS wins
                FROM games
                WHERE is_lag=0 AND is_cheater=0 AND substr(eco, 1, 3) = ?
                GROUP BY week HAVING games >= 2
                ORDER BY week DESC LIMIT 6
            """, (eco3,))
            weeks = cur.fetchall()
            if not weeks:
                w.w("  — мало данных по неделям")
                continue
            weeks_rev = list(reversed(weeks))
            w.w(f"  {'Неделя':<10} {'Игр':<6} {'Win%':<7} {'Тренд'}")
            prev_wr = None
            for week, games, wins in weeks_rev:
                wr = wins / games * 100 if games else 0
                mark = ""
                if prev_wr is not None:
                    d = wr - prev_wr
                    mark = "↑" if d > 5 else ("↓" if d < -5 else "→")
                w.w(f"  {week:<10} {games:<6} {wr:<7.0f} {mark}")
                prev_wr = wr
                
            if len(weeks_rev) >= 2:
                first_wr = weeks_rev[0][2] / weeks_rev[0][1] * 100 if weeks_rev[0][1] else 0
                last_wr = weeks_rev[-1][2] / weeks_rev[-1][1] * 100 if weeks_rev[-1][1] else 0
                delta = last_wr - first_wr
                if delta > 5:
                    w.w(f"  ✅ РАСТЁТ: {first_wr:.0f}% → {last_wr:.0f}% ({delta:+.0f})")
                elif delta < -5:
                    w.w(f"  ⚠️ ПАДАЕТ: {first_wr:.0f}% → {last_wr:.0f}% ({delta:+.0f})")
                else:
                    w.w(f"  ➡️ СТАБИЛЬНО: {first_wr:.0f}% → {last_wr:.0f}%")
                    
        w.w()
        w.w("🎯 ВЕРДИКТ:")
        w.w("  Играй дебюты, где win rate растёт.")
        w.w("  Бросай дебюты, где win rate падает 2+ недели подряд.")
    conn.close()


def report_opening_performance():
    conn = _conn(); cur = conn.cursor()
    with report_context("opening_performance") as w:
        w.w_separator(title="ПРОИЗВОДИТЕЛЬНОСТЬ ПО ДЕБЮТАМ")
        w.w()
        
        cur.execute("""
            SELECT substr(eco, 1, 3) AS eco3,
                   COUNT(*) as games,
                   SUM(won) as wins,
                   ROUND(AVG(acpl), 1) as acpl,
                   ROUND(AVG(opp_rating)) as avg_opp,
                   ROUND(AVG(opp_rating + ((CASE WHEN won=1 THEN 1.0 WHEN draw=1 THEN 0.5 ELSE 0.0 END) - 0.5) * 800)) as perf
            FROM games
            WHERE is_lag=0 AND is_cheater=0 AND eco IS NOT NULL
            GROUP BY eco3
            HAVING games >= 10
            ORDER BY perf DESC
        """)
        rows = cur.fetchall()
        
        w.w(f"  {'ECO':<6} {'Игр':<6} {'Побед':<7} {'Win%':<7} {'ACPL':<6} {'Перф':<6} {'Ср. рейт соп.'}")
        for eco, cnt, wins, acpl, avg_opp, perf in rows:
            wr = wins / cnt * 100
            w.w(f"  {eco:<6} {cnt:<6} {wins:<7} {wr:<7.1f} {acpl:<6.0f} {perf:<6.0f} {avg_opp:.0f}")
            
        w.w()
        w.w("🎯 ВЕРДИКТ:")
        if rows:
            best = rows[0]
            w.w(f"  Лучший дебют: {best[0]} (Перф {best[5]:.0f}, Win% {best[2]/best[1]*100:.0f}%)")
            if len(rows) > 1:
                worst = rows[-1]
                w.w(f"  Худший дебют: {worst[0]} (Перф {worst[5]:.0f}, Win% {worst[2]/worst[1]*100:.0f}%)")
        w.w("  Играй дебюты, где перфоманс > 2600. Убирай те, где < 2400.")
    conn.close()


def report_weak_spots_matrix():
    conn = _conn(); cur = conn.cursor()
    with report_context("weak_spots_matrix") as w:
        w.w_separator(title="МАТРИЦА СЛАБОСТЕЙ (дебют × фаза × рейтинг)")
        w.w()
        
        cur.execute("""
            SELECT substr(eco, 1, 3) AS eco3,
                   CASE
                       WHEN opp_rating < 2500 THEN '2400-2499'
                       WHEN opp_rating < 2600 THEN '2500-2599'
                       WHEN opp_rating < 2700 THEN '2600-2699'
                       ELSE '2700+'
                   END AS rng,
                   COUNT(*),
                   ROUND(AVG(acpl_middlegame), 1),
                   ROUND(100.0*SUM(won)/COUNT(*), 1)
            FROM games
            WHERE is_lag=0 AND is_cheater=0 AND eco IS NOT NULL AND acpl_middlegame > 0
            GROUP BY eco3, rng HAVING COUNT(*) >= 5
            ORDER BY AVG(acpl_middlegame) DESC LIMIT 10
        """)
        w.w("📊 ТОП-10 ХУДШИХ КОМБИНАЦИЙ (дебют + рейтинг):")
        w.w(f"  {'Дебют':<6} {'Рейтинг':<12} {'Игр':<6} {'ACPL мит':<10} {'Win%'}")
        for eco, rng, cnt, acpl_mid, wr in cur.fetchall():
            w.w(f"  {eco:<6} {rng:<12} {cnt:<6} {acpl_mid:<10.1f} {wr:<.0f}%")
        w.w()
        
        cur.execute("""
            SELECT substr(eco, 1, 3) AS eco3,
                   CASE
                       WHEN opp_rating < 2500 THEN '2400-2499'
                       WHEN opp_rating < 2600 THEN '2500-2599'
                       WHEN opp_rating < 2700 THEN '2600-2699'
                       ELSE '2700+'
                   END AS rng,
                   COUNT(*),
                   ROUND(AVG(acpl_middlegame), 1),
                   ROUND(100.0*SUM(won)/COUNT(*), 1)
            FROM games
            WHERE is_lag=0 AND is_cheater=0 AND eco IS NOT NULL AND acpl_middlegame > 0
            GROUP BY eco3, rng HAVING COUNT(*) >= 5
            ORDER BY (SUM(won)*1.0/COUNT(*)) DESC, AVG(acpl_middlegame) ASC LIMIT 10
        """)
        w.w("📊 ТОП-10 ЛУЧШИХ КОМБИНАЦИЙ (где ты силён):")
        w.w(f"  {'Дебют':<6} {'Рейтинг':<12} {'Игр':<6} {'ACPL мит':<10} {'Win%'}")
        for eco, rng, cnt, acpl_mid, wr in cur.fetchall():
            w.w(f"  {eco:<6} {rng:<12} {cnt:<6} {acpl_mid:<10.1f} {wr:<.0f}%")
        w.w()
        
        w.w("🎯 ВЕРДИКТ:")
        w.w("  Худшие комбинации — учи или избегай.")
        w.w("  Лучшие комбинации — играй агрессивно, это твоё оружие.")
    conn.close()


def report_rating_by_opening():
    import chess, chess.pgn
    conn = _conn(); cur = conn.cursor()
    
    cur.execute("""
        WITH ranked_games AS (
            SELECT substr(eco, 1, 3) AS eco3,
                   CASE WHEN LOWER(white) = LOWER(?) THEN 'White' ELSE 'Black' END AS color,
                   my_rating, opening, opening_line,
                   ROW_NUMBER() OVER (PARTITION BY substr(eco, 1, 3), CASE WHEN LOWER(white) = LOWER(?) THEN 'White' ELSE 'Black' END ORDER BY end_time ASC) as rn_asc,
                   ROW_NUMBER() OVER (PARTITION BY substr(eco, 1, 3), CASE WHEN LOWER(white) = LOWER(?) THEN 'White' ELSE 'Black' END ORDER BY end_time DESC) as rn_desc,
                   COUNT(*) OVER (PARTITION BY substr(eco, 1, 3), CASE WHEN LOWER(white) = LOWER(?) THEN 'White' ELSE 'Black' END) as total_games
            FROM games
            WHERE is_lag=0 AND is_cheater=0 AND my_rating > 0 AND eco IS NOT NULL
        )
        SELECT a.eco3, a.color, a.total_games, a.my_rating as start_rating, d.my_rating as end_rating,
               (d.my_rating - a.my_rating) as delta, MAX(a.opening) as opening_name, MAX(a.opening_line) as opening_moves
        FROM ranked_games a
        JOIN ranked_games d ON a.eco3 = d.eco3 AND a.color = d.color
        WHERE a.rn_asc = 1 AND d.rn_desc = 1 AND a.total_games >= 10
        GROUP BY a.eco3, a.color
        ORDER BY delta DESC
    """, (PLAYER, PLAYER, PLAYER, PLAYER))
    rows = cur.fetchall()
    
    with report_context("rating_by_opening") as w:
        w.w_separator(title="ДИНАМИКА РЕЙТИНГА ПО ДЕБЮТАМ (Δ)")
        w.w("⚠️ ВАЖНО: Δ — это изменение рейтинга за период, пока ты играл этот дебют.")
        w.w("   Рейтинг меняется из-за ВСЕХ партий, не только этих.")
        w.w("   «A40 −81» ≠ «A40 приносит −81». Это «за период A40 рейтинг упал на 81».")
        w.w()
        
        w.w(f"  {'Цвет':<7} {'Игр':<5} {'Старт':<7} {'Конец':<7} {'Δ':<6} {'Название и первые ходы'}")
        w.w("  " + "-" * 75)
        
        for eco, color, games, start_r, end_r, delta, name, moves in rows:
            trend = "📈" if delta > 15 else ("📉" if delta < -15 else "➡️")
            clean_name = (name or "Unknown").replace("Defense", "Def").replace("Opening", "Open")
            if len(clean_name) > 35:
                clean_name = clean_name[:32] + "..."
                
            san_moves = ""
            if moves:
                try:
                    b = chess.Board()
                    game = chess.pgn.Game()
                    game.setup(b)
                    node = game
                    for uci in moves.split()[:20]:
                        move = chess.Move.from_uci(uci)
                        san = b.san(move)
                        node = node.add_variation(move)
                        b.push(move)
                    san_moves = game.accept(chess.pgn.StringExporter(headers=False, variations=False, comments=False))
                    if len(san_moves) > 40:
                        san_moves = san_moves[:37] + "..."
                except Exception:
                    san_moves = " ".join(moves.split()[:10])
                    
            w.w(f"  {color:<7} {games:<5} {start_r:<7} {end_r:<7} {delta:+6d}   {trend} {clean_name}")
            if san_moves:
                w.w(f"  {'':<32} └─ {san_moves}")
                
        w.w()
        w.w("🎯 ВЕРДИКТ:")
        if rows:
            best = rows[0]
            worst = rows[-1]
            w.w(f"  Лучший: {best[0]} {best[1]} ({best[5]:+d} п.) - {best[6]}")
            w.w(f"  Худший: {worst[0]} {worst[1]} ({worst[5]:+d} п.) - {worst[6]}")
            w.w("  💡 Δ показывает изменение рейтинга за период. Winrate/ACPL — эффект дебюта.")
    conn.close()