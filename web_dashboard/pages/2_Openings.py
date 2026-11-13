# web_dashboard/pages/2_Openings.py
import streamlit as st
import plotly.express as px
import pandas as pd
import json, os, chess, io
import chess.pgn
import re
from utils.chess_vis import render_board_html
import _common
from utils.db import query_df, cutoff_ts

st.set_page_config(page_title="Дебюты (Openings)", page_icon="♟️", layout="wide")
st.title("♟️ Дебюты (Openings)")

# ФИКС: Берем PLAYER из конфига, без хардкода
PLAYER = _common.CONFIG.get("player", "unknown").lower()

with st.sidebar:
    days = st.slider("Период (дней)", 7, 365, 90, 1)
ts = cutoff_ts(days)

df = query_df("""
    SELECT opening, eco, CASE WHEN LOWER(white) = LOWER(?) THEN 'Белые' ELSE 'Чёрные' END AS color,
           MAX(opening_line) AS opening_line, COUNT(*) AS games, SUM(won) AS wins, AVG(acpl) AS acpl
    FROM games WHERE end_time >= ? AND is_lag=0 AND is_cheater=0 AND opening IS NOT NULL AND opening != ''
    GROUP BY opening, eco, color ORDER BY games DESC
""", (PLAYER, ts))

if df.empty:
    st.warning("Нет данных.")
    st.stop()

df["win_rate"] = (df["wins"] / df["games"] * 100).round(1)
df["acpl"] = df["acpl"].round(0)
df_reliable = df[df["games"] >= 5]
df_white = df_reliable[df_reliable["color"] == "Белые"]
df_black = df_reliable[df_reliable["color"] == "Чёрные"]

tab_w, tab_b = st.tabs(["♔ За белых", "♚ За чёрных"])


def draw_top_10(data, title_prefix):
    if data.empty:
        st.info("Мало данных (нужно минимум 5 партий на дебют).")
        return
    c1, c2 = st.columns(2)
    with c1:
        st.subheader(f"✅ Топ-10 лучших ({title_prefix})")
        best = data.sort_values("win_rate", ascending=False).head(10)
        fig = px.bar(
            best, x="win_rate", y="opening", orientation="h", text="win_rate",
            hover_data=["games", "opening_line"],
        )
        fig.update_layout(
            yaxis={"categoryorder": "total ascending"},
            height=400, xaxis_title="Винрейт %",
        )
        fig.update_xaxes(range=[0, 100])
        fig.update_traces(
            texttemplate='%{text}%<br>(%{customdata[0]} игр)',
            customdata=best[["games"]],
        )
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.subheader(f"❌ Топ-10 худших ({title_prefix})")
        worst = data.sort_values("win_rate", ascending=True).head(10)
        fig2 = px.bar(
            worst, x="win_rate", y="opening", orientation="h", text="win_rate",
            hover_data=["games", "opening_line"],
            color_discrete_sequence=["#dc3545"],
        )
        fig2.update_layout(
            yaxis={"categoryorder": "total descending"},
            height=400, xaxis_title="Винрейт %",
        )
        fig2.update_xaxes(range=[0, 100])
        fig2.update_traces(
            texttemplate='%{text}%<br>(%{customdata[0]} игр)',
            customdata=worst[["games"]],
        )
        st.plotly_chart(fig2, use_container_width=True)


with tab_w:
    draw_top_10(df_white, "Белые")
with tab_b:
    draw_top_10(df_black, "Чёрные")

st.divider()
st.subheader("📋 Все дебюты (сортировка по количеству игр)")

tab_tw, tab_tb = st.tabs(["Таблица: Белые", "Таблица: Чёрные"])
cols = ["opening", "eco", "games", "win_rate", "acpl", "opening_line"]
with tab_tw:
    st.dataframe(df[df["color"] == "Белые"][cols],
                 use_container_width=True, hide_index=True)
with tab_tb:
    st.dataframe(df[df["color"] == "Чёрные"][cols],
                 use_container_width=True, hide_index=True)

st.divider()
st.subheader("🔬 Разбор конкретной линии (с доской)")

valid_df = df.dropna(subset=["opening_line"])
valid_df = valid_df[valid_df["opening_line"] != ""]
line_dict = dict(zip(
    valid_df["opening_line"],
    valid_df["eco"] + " (" + valid_df["opening"] + ")",
))

if line_dict:
    selected_line = st.selectbox(
        "Выбери линию (UCI) для визуализации:",
        options=list(line_dict.keys()),
        format_func=lambda x: f"{line_dict[x]}: {x}",
    )

    if selected_line:
        board = chess.Board()
        for move in selected_line.split():
            try:
                board.push_uci(move)
            except Exception:
                break

        game = chess.pgn.Game()
        game.add_line(board.move_stack)
        exporter = chess.pgn.StringExporter(
            headers=False, variations=False, comments=False,
        )
        pgn_str = game.accept(exporter)

        c_board, c_info = st.columns([1, 1])
        with c_board:
            st.markdown(render_board_html(board.fen(), size=440),
                        unsafe_allow_html=True)
        with c_info:
            st.markdown(f"**FEN:** `{board.fen()}`")
            st.code(board.fen(), language="text")
            if st.button("🔬 Открыть в Анализаторе", type="primary",
                         use_container_width=True):
                st.session_state["analyze_pgn"] = pgn_str
                st.session_state["analyze_fen"] = None
                st.switch_page("pages/6_Analysis.py")

st.divider()
st.subheader("🌳 OPENING PLANNER (Stockfish) — рекомендации")

planner_path = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "reports", "opening_planner.txt"
))

if os.path.exists(planner_path):
    with open(planner_path, "r", encoding="utf-8") as f:
        planner_text = f.read()

    ecos = re.findall(r'♟️ ([A-Z]\d{2}) \(\d+ партий', planner_text)
    ecos = sorted(list(set(ecos)))

    if ecos:
        selected_eco = st.selectbox("Выбери дебют (ECO) для рекомендаций:", ecos)
        pattern = rf'(♟️ {selected_eco} \(\d+ партий.*?)(?=♟️ [A-Z]\d{{2}} \(\d+ партий|РЕЗЮМЕ ПО ВСЕМ ДЕБЮТАМ|$)'
        match = re.search(pattern, planner_text, re.DOTALL)
        if match:
            st.code(match.group(1).strip(), language="text")
        else:
            st.info("Не удалось найти блок для этого ECO.")
    else:
        st.warning("В planner.txt нет данных по ECO.")
else:
    st.warning("opening_planner.txt не найден. Запусти 05_openings.py.")