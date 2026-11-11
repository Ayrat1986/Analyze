# ============================================================
# web_dashboard/pages/15_Review.py — Разбор партии
# ============================================================
import sys
import os

def clear_pycache(start_path):
    import shutil
    for root, dirs, files in os.walk(start_path):
        for d in dirs:
            if d == '__pycache__':
                shutil.rmtree(os.path.join(root, d), ignore_errors=True)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DIR = os.path.join(BASE_DIR, "src")
clear_pycache(SRC_DIR)
clear_pycache(os.path.dirname(os.path.abspath(__file__)))

if BASE_DIR not in sys.path: sys.path.insert(0, BASE_DIR)
if SRC_DIR not in sys.path: sys.path.insert(0, SRC_DIR)

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from analysis.dashboard_helpers import get_game_review, get_recent_games

st.set_page_config(page_title="Разбор партии", layout="wide")
st.title("🔍 Разбор партии")
st.markdown("Выбери партию из списка, чтобы увидеть её анализ: ACPL, зевки и график оценки.")

@st.cache_data(ttl=300)
def load_games():
    return get_recent_games(50)

@st.cache_data(ttl=300)
def load_review(url):
    return get_game_review(url)

games = load_games()
if not games:
    st.warning("Нет партий для разбора.")
    st.stop()

options = {g["label"]: g["url"] for g in games}
selected_label = st.selectbox("Выбери партию:", list(options.keys()))
selected_url = options[selected_label]

game = load_review(selected_url)
if not game:
    st.error("Не удалось загрузить данные партии.")
    st.stop()

# --- Заголовок ---
res = "ПОБЕДА" if game["won"] else ("НИЧЬЯ" if game["draw"] else "ПОРАЖЕНИЕ")
st.subheader(f"{game['white']} vs {game['black']} — {res}")
st.caption(f"{game['eco']} {game['opening']} | Рейтинги: {game['my_rating']} vs {game['opp_rating']} | Причина: {game['reason']}")

# --- Метрики ---
col1, col2, col3, col4 = st.columns(4)
col1.metric("ACPL общий", f"{game['acpl']:.0f}" if game['acpl'] else "—")
col2.metric("ACPL миттельшпиль", f"{game['acpl_mid']:.0f}" if game['acpl_mid'] else "—")
col3.metric("Accuracy", f"{game['accuracy']:.1f}%" if game['accuracy'] else "—")
col4.metric("Твой макс. перевес", f"+{game['max_eval_adv']/100:.1f}" if game['max_eval_adv'] else "—")

st.divider()

# --- График оценки ---
if game["hist"]:
    st.subheader("График оценки (Eval)")
    moves = [h[0] for h in game["hist"]]
    evals = [h[1] / 100.0 for h in game["hist"]]
    
    # Определяем цвет графика
    colors = ['#00CC96' if e >= 0 else '#EF553B' for e in evals]
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=moves, y=evals, mode='lines+markers', line=dict(color='#636EFA', width=2), name='Eval'))
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    
    # Подсвечиваем зевки
    blunder_moves = {b["move_num"]: b for b in game["blunders"] if b["is_my_blunder"]}
    for bm in blunder_moves:
        fig.add_vline(x=bm, line_dash="dot", line_color="red", opacity=0.5)
    
    fig.update_layout(
        height=400,
        xaxis_title="Номер хода",
        yaxis_title="Оценка (+ = лучше)",
        margin=dict(l=0, r=0, t=30, b=0),
        showlegend=False
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Нет данных для построения графика оценки.")

st.divider()

# --- Таблица зевков ---
st.subheader("📉 Твои зевки (Топ-5)")
my_blunders = [b for b in game["blunders"] if b["is_my_blunder"]]
my_blunders.sort(key=lambda x: x["loss"], reverse=True)
if not my_blunders:
    st.success("В этой партии не было зевков!")
else:
    for b in my_blunders[:5]:
        with st.expander(f"Ход {b['move_num']} ({b['move']}) — потеря {b['loss']} CP"):
            st.markdown(f"**Паттерн:** {b['pattern_tag']}")
            st.markdown(f"**Что случилось:** {b['what']}")
            st.markdown(f"**Время на ход:** {b['time_spent']} сек")
            st.markdown(f"[🔗 Открыть партию на Lichess]({game['url']})")

st.divider()

# --- Ссылка на PGN ---
if game["pgn"]:
    with st.expander("📄 PGN партии"):
        st.code(game["pgn"], language="text")