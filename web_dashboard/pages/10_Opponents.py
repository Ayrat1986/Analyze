# web_dashboard/pages/10_Opponents.py
import streamlit as st
import pandas as pd
import os
import sqlite3

st.set_page_config(page_title="Соперники", page_icon="🎭", layout="wide")
st.title("🎭 Психология соперников")

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "chess.db"))

def read_report(name):
    path = os.path.join(os.path.dirname(__file__), "..", "..", "reports", name)
    if not os.path.exists(path): return ""
    with open(path, "r", encoding="utf-8") as f: return f.read()

st.subheader("🩸 Те, кто тебя раскалывает (Score < 30%)")
crushed_text = read_report("crushed_by.txt")
if crushed_text:
    rows = []
    for line in crushed_text.split("\n"):
        parts = line.split()
        if len(parts) == 7 and parts[0] not in ["Соперник", "-"]:
            try:
                rows.append({
                    "Соперник": parts[0], "Рейтинг": int(parts[1]), "Партий": int(parts[2]),
                    "W/D/L": parts[3], "Score %": float(parts[4]), "Мой ACPL": float(parts[5]), "Его ACPL": float(parts[6])
                })
            except ValueError: continue
    
    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        # ВЫБОР СОПЕРНИКА ДЛЯ ПРОСМОТРА ПАРТИЙ
        st.divider()
        st.subheader("🔍 Разбор партий против конкретного соперника")
        opponent = st.selectbox("Выбери соперника:", ["—"] + df["Соперник"].tolist())
        
        if opponent != "—":
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("""
                SELECT end_time, white, black, won, draw, reason, url, pgn
                FROM games WHERE opp_username = ? AND is_lag=0 AND is_cheater=0
                ORDER BY end_time DESC
            """, (opponent,))
            games = cur.fetchall()
            conn.close()
            
            for g in games:
                res = "Победа" if g[3] else ("Ничья" if g[4] else "Поражение")
                date = pd.to_datetime(g[0], unit='s').strftime('%d.%m.%y')
                
                with st.expander(f"{date} | {g[1]} vs {g[2]} | {res} ({g[5]})"):
                    if st.button("🔬 Открыть в Анализаторе", key=f"ana_{g[6]}"):
                        st.session_state["analyze_pgn"] = g[7]
                        st.session_state["analyze_fen"] = None
                        st.switch_page("pages/6_Analysis.py")
    else:
        st.success("✅ Таких соперников нет!")