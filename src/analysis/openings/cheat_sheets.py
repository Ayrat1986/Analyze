# ============================================================
# analysis/openings/cheat_sheets.py
# ============================================================
import os
import sqlite3
import json
from collections import Counter
from datetime import datetime
from analysis.common import _conn, REPORTS_DIR, PLAYER

def report_opening_cheat_sheets():
    conn = _conn()
    cur = conn.cursor()
    
    # Интересующие дебюты
    targets = {
        "D00": "Ферзевый гамбит (Черные поля)",
        "D02": "Ферзевый гамбит (Псевдо-Каталон)",
        "D10": "Славянская защита (Обменный вариант)"
    }
    
    path = os.path.join(REPORTS_DIR, "opening_cheat_sheets.txt")
    
    with open(path, "w", encoding="utf-8") as f:
        def w(line=""):
            print(line); f.write(line + "\n")
            
        w("=" * 60)
        w(" 🧠 ШПАРГАЛКИ ПО ПРОБЛЕМНЫМ ДЕБЮТАМ (D00, D02, D10)")
        w("=" * 60)
        w(f"Сформировано: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        w("💡 Цель: выучить план на первые 10-12 ходов, чтобы экономить время.")
        w()

        for eco, name in targets.items():
            w("=" * 60)
            w(f" ♟️ {eco} — {name}")
            w("=" * 60)

            # 1. Общая статистика
            cur.execute("""
                SELECT COUNT(*), SUM(won), SUM(draw), AVG(acpl), AVG(my_rating), AVG(opp_rating)
                FROM games WHERE is_lag=0 AND is_cheater=0 AND eco = ?
            """, (eco,))
            n, wins, draws, acpl, my_r, opp_r = cur.fetchone()
            
            if not n or n < 5:
                w(" ⚠️ Мало данных для анализа.")
                w()
                continue
                
            score = (wins + 0.5 * draws) / n * 100
            w(f" 📊 Партий: {n} | Винрейт: {score:.1f}% | ACPL: {acpl:.1f}")
            w(f"    Твой рейтинг: {my_r:.0f} | Соперники: {opp_r:.0f}")
            w()

            # 2. Где ты зеваешь (Номер хода)
            cur.execute("""
                SELECT b.move_num, COUNT(*), AVG(b.loss_cp)
                FROM blunders b JOIN games g ON g.url = b.game_url
                WHERE g.eco = ? AND b.is_my_blunder = 1 AND b.is_berserk = 0 AND b.is_instant = 0
                GROUP BY b.move_num ORDER BY COUNT(*) DESC LIMIT 5
            """, (eco,))
            blunders = cur.fetchall()
            if blunders:
                w(" 🚨 ТОП-5 ХОДОВ, ГДЕ ТЫ ЗЕВАЕШЬ (в этом дебюте):")
                for mn, cnt, loss in blunders:
                    w(f"    Ход {mn}: {cnt} раз (средняя потеря {loss:.0f} CP)")
                w("    💡 Совет: на этих ходах делай паузу или форсируй размен.")
                w()

            # 3. Планы (статистика по первым 10 ходам из PGN)
            cur.execute("SELECT pgn FROM games WHERE eco = ? AND pgn IS NOT NULL LIMIT 100", (eco,))
            pgns = cur.fetchall()
            
            move_counts = [Counter() for _ in range(10)] # 10 ходов
            
            try:
                import chess.pgn, io
                for (pgn,) in pgns:
                    game = chess.pgn.read_game(io.StringIO(pgn))
                    if not game: continue
                    board = game.board()
                    for i, node in enumerate(game.mainline()):
                        if i >= 20: break # только первые 10 ходов (20 полуходов)
                        move_counts[i // 2][node.move.uci()] += 1
            except ImportError:
                w(" ⚠️ python-chess не установлен, ходы не проанализировать.")
            
            w(" 📖 ПЛАН НА ПЕРВЫЕ 10 ХОДОВ (твои частые продолжения):")
            for i, counter in enumerate(move_counts):
                if not counter: continue
                top_moves = counter.most_common(2)
                moves_str = ", ".join([f"{m} ({c} раз)" for m, c in top_moves])
                w(f"    Ход {i+1}: {moves_str}")
            
            w()
            w(" 🎯 РЕКОМЕНДАЦИЯ:")
            if eco == "D10":
                w("    • В Славянке ты часто играешь 3.Nc3. Это ведет к сложной борьбе.")
                w("    • Если не хочешь сжигать время, играй 3.Nf3 или 3.e3 (более спокойно).")
                w("    • Не атакуй ферзем на 10-м ходу. Сначала развей коней.")
            elif eco == "D00":
                w("    • В Ферзевом гамбите ты играешь Blackmar-Diemer (3.e4).")
                w("    • Это гамбит! Ты отдаешь пешку за атаку. Если не видишь атаку — не играй его.")
                w("    • Альтернатива: 3.Nf3 (спокойный план).")
            elif eco == "D02":
                w("    • Псевдо-Каталон. Ты часто ставишь слона на g2.")
                w("    • План: атака на ферзевый фланг через b4 и c5. Но сначала поставь ладью на c1.")
            w()

    conn.close()
    print(f"\n✅ {path}")