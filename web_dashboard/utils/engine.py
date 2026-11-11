# web_dashboard/utils/engine.py
import chess.engine
import streamlit as st
import os
import json

# ⚠️ ВНИМАНИЕ: @st.cache_resource глобален для процесса.
# Если дашборд откроют одновременно два пользователя, они будут использовать один и тот же движок.
# Для личного использования это приемлемо. Для многопользовательского — нужен пул движков или мьютекс.
@st.cache_resource
def get_stockfish():
    config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "config.json"))
    stockfish_path = ""
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            stockfish_path = config.get("stockfish_path", "")
            
    if not stockfish_path or not os.path.exists(stockfish_path):
        return None
        
    try:
        return chess.engine.SimpleEngine.popen_uci(stockfish_path)
    except Exception as e:
        st.error(f"Не удалось запустить Stockfish: {e}")
        return None