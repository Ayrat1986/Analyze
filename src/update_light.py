# src/update_light.py
import os
import sys
import sqlite3
import json
import traceback
from importlib import import_module
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, SRC_DIR)

import _common

fetch_api = import_module("01_fetch_chess_api")

DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")

def main():
    print("🚀 Запуск легкого обновления...")
    try:
        print("📥 Шаг 1: Загрузка API...")
        fetch_api.main()
        
        API_CACHE = str(_common.BASE_DIR / "data" / "chess_api_cache.json")
        if not os.path.exists(API_CACHE):
            print("❌ Нет кэша API")
            return
            
        with open(API_CACHE, "r", encoding="utf-8") as f:
            api_cache = json.load(f)
            
        print("💾 Шаг 2: Обновление базы...")
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        
        cur.execute("SELECT url FROM games")
        existing_urls = {row[0] for row in cur.fetchall()}
        
        new_games = 0
        for url, data in api_cache.items():
            if not isinstance(data, dict) or "games" not in data:
                continue
                
            for g in data["games"]:
                g_url = g.get("url")
                if not g_url or g_url in existing_urls:
                    continue
                    
                white = g.get("white", {})
                black = g.get("black", {})
                is_white = white.get("username", "").lower() == fetch_api.PLAYER.lower()
                
                my_rating = white.get("rating", 0) if is_white else black.get("rating", 0)
                opp_rating = black.get("rating", 0) if is_white else white.get("rating", 0)
                opp_username = black.get("username", "") if is_white else white.get("username", "")
                
                my_result = white.get("result") if is_white else black.get("result")
                won = 1 if my_result == "win" else 0
                draw = 1 if my_result in ["agreed", "repetition", "stalemate", "insufficient"] else 0
                reason = my_result if my_result else "unknown"
                
                cur.execute("""
                    INSERT OR IGNORE INTO games 
                    (url, end_time, white, black, my_rating, opp_rating, opp_username, 
                     won, draw, reason, is_lag, is_cheater, acpl, analyzed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, ?)
                """, (
                    g_url, g.get("end_time", 0), white.get("username", ""), black.get("username", ""),
                    my_rating, opp_rating, opp_username, won, draw, reason, datetime.now().isoformat()
                ))
                new_games += 1
                
        conn.commit()
        conn.close()
        print(f"✅ Добавлено новых партий: {new_games}")

    except Exception as e:
        print(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
