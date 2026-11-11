# ============================================================
# analysis/opponents/trainer.py — v20.0
# Тренажер позиций против агрессоров
# ============================================================
import os
import csv
from .common import _conn, REPORTS_DIR, PLAYER
from _chess_utils import build_opponent_style_map

def report_anti_aggressor_trainer():
    conn = _conn()
    cur = conn.cursor()
    
    # 1. Получаем карту стилей (кто агрессор)
    style_map = build_opponent_style_map(conn, PLAYER)
    
    # 2. Достаем зевки против агрессоров
    cur.execute("""
        SELECT g.url, g.white, g.black, g.opp_username, b.move_num, b.loss_cp, 
               b.fen_before, b.best_move_uci, b.pattern_tag
        FROM blunders b JOIN games g ON g.url = b.game_url
        WHERE g.is_lag=0 AND g.is_cheater=0 
          AND b.is_my_blunder=1 AND b.is_berserk=0 AND b.is_instant=0
          AND b.loss_cp > 200
          AND b.fen_before IS NOT NULL AND b.fen_before != ''
    """)
    rows = cur.fetchall()
    
    aggressive_blunders = []
    for url, white, black, opp, mn, loss, fen, best, tag in rows:
        opp_clean = (opp or "").lower()
        if style_map.get(opp_clean) == "aggressive":
            aggressive_blunders.append({
                "url": url, "white": white, "black": black, "opp": opp,
                "move_num": mn, "loss_cp": loss, "fen": fen, "best_move": best, "tag": tag
            })
            
    # Сортируем по потерянным CP (самые страшные сверху)
    aggressive_blunders.sort(key=lambda x: x["loss_cp"], reverse=True)
    
    # 3. Сохраняем в CSV для веб-дашборда
    training_dir = os.path.join(REPORTS_DIR, "training")
    os.makedirs(training_dir, exist_ok=True)
    
    csv_path = os.path.join(training_dir, "anti_aggressor.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["url", "white", "black", "opponent", "move_num", "loss_cp", "fen", "best_move", "pattern"])
        for b in aggressive_blunders[:100]: # Берем топ-100
            writer.writerow([b["url"], b["white"], b["black"], b["opp"], b["move_num"], b["loss_cp"], b["fen"], b["best_move"], b["tag"]])
            
    # 4. Пишем текстовый отчет
    txt_path = os.path.join(REPORTS_DIR, "anti_aggressor_trainer.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        def w(line=""):
            print(line); f.write(line + "\n")
            
        w("=" * 60)
        w(" 🛡️ ТРЕНАЖЕР АНТИ-АГРЕССОРА")
        w("=" * 60)
        w(f"Найдено зевков против агрессоров: {len(aggressive_blunders)}")
        w("Топ-5 позиций для разбора (открой в Lichess):")
        w()
        
        for b in aggressive_blunders[:5]:
            w(f"• Ход {b['move_num']} (потеря {b['loss_cp']} CP). Паттерн: {b['tag']}")
            w(f"  Соперник: {b['opp']}")
            w(f"  FEN: {b['fen']}")
            w(f"  Лучший ход: {b['best_move']}")
            w(f"  Тренируй: https://lichess.org/analysis/standard/{b['fen'].replace(' ', '_')}")
            w()
            
    conn.close()
    print(f"\n✅ {txt_path}")
    print(f"✅ {csv_path}")