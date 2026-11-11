# ============================================================
# analysis/trainer/smart_deck.py
# ============================================================
import os
import csv
import sqlite3
import random
from datetime import datetime, timedelta, timezone
from analysis.common import _conn, REPORTS_DIR, PLAYER

def generate_smart_deck():
    conn = _conn()
    cur = conn.cursor()
    
    training_dir = os.path.join(REPORTS_DIR, "training")
    os.makedirs(training_dir, exist_ok=True)
    
    # 1. Свежие (7 дней)
    ts_7d = int((datetime.now(timezone.utc) - timedelta(days=7)).timestamp())
    cur.execute("""
        SELECT g.url, g.white, g.black, b.move_num, b.loss_cp, b.fen_before, b.best_move_uci, b.pattern_tag, b.ply
        FROM blunders b JOIN games g ON g.url = b.game_url
        WHERE g.is_lag=0 AND g.is_cheater=0 AND b.is_my_blunder=1 AND b.is_berserk=0 AND b.is_instant=0
          AND b.loss_cp > 150 AND b.fen_before IS NOT NULL AND b.fen_before != ''
          AND g.end_time >= ?
        ORDER BY b.loss_cp DESC LIMIT 10
    """, (ts_7d,))
    fresh = cur.fetchall()

    # 2. Анти-Агрессор
    cur.execute("""
        SELECT g.url, g.white, g.black, b.move_num, b.loss_cp, b.fen_before, b.best_move_uci, b.pattern_tag, b.ply
        FROM blunders b JOIN games g ON g.url = b.game_url
        WHERE g.is_lag=0 AND g.is_cheater=0 AND b.is_my_blunder=1 AND b.is_berserk=0 AND b.is_instant=0
          AND b.loss_cp > 200 AND b.fen_before IS NOT NULL AND b.fen_before != ''
          AND g.opp_rating > 2400
        ORDER BY b.loss_cp DESC LIMIT 10
    """)
    anti_agg = cur.fetchall()

    # 3. Час X (21-25 ход)
    cur.execute("""
        SELECT g.url, g.white, g.black, b.move_num, b.loss_cp, b.fen_before, b.best_move_uci, b.pattern_tag, b.ply
        FROM blunders b JOIN games g ON g.url = b.game_url
        WHERE g.is_lag=0 AND g.is_cheater=0 AND b.is_my_blunder=1 AND b.is_berserk=0 AND b.is_instant=0
          AND b.loss_cp > 200 AND b.fen_before IS NOT NULL AND b.fen_before != ''
          AND b.move_num BETWEEN 21 AND 25
        ORDER BY b.loss_cp DESC LIMIT 10
    """)
    hour_x = cur.fetchall()

    # Объединяем и удаляем дубликаты по FEN
    all_blunders = fresh + anti_agg + hour_x
    seen_fens = set()
    unique_blunders = []
    for b in all_blunders:
        if b[5] in seen_fens: continue
        seen_fens.add(b[5])
        unique_blunders.append(b)

    # Сохраняем в CSV
    csv_path = os.path.join(training_dir, "smart_deck.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["url", "white", "black", "move_num", "loss_cp", "fen", "best_move", "pattern", "ply"])
        for b in unique_blunders:
            w.writerow(b)
            
    conn.close()
    print(f"✅ Умная колода: {len(unique_blunders)} позиций ({csv_path})")
    return csv_path