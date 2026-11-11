# web_dashboard/pages/5_Blunders.py
import streamlit as st
import pandas as pd
import os
import plotly.express as px

st.set_page_config(page_title="Зевки и Колода", page_icon="⚠️", layout="wide")
from utils.db import query_df, cutoff_ts
from utils.chess_vis import fen_before_move, render_board_html, get_best_move_san

st.title("⚠️ Разбор зевков и Тренировка")

with st.sidebar:
    st.header("⚙️ Фильтры")
    days = st.slider("Период (дней)", 7, 365, 90, 1)
    min_loss = st.slider("Мин. потеря (CP)", 150, 1000, 200, 50)
    phases = st.selectbox("Фаза", ["Все", "Дебют (1-10)", "Миттельшпиль (11-30)", "Эндшпиль (31+)"])
    only_critical = st.checkbox("Только 'час X' (10-15 ход)", value=False)
    only_missed_threat = st.checkbox("Только пропущенные угрозы", value=False)

ts = cutoff_ts(days)
phase_sql = ""
if phases == "Дебют (1-10)": phase_sql = " AND b.move_num <= 10"
elif phases == "Миттельшпиль (11-30)": phase_sql = " AND b.move_num > 10 AND b.move_num <= 30"
elif phases == "Эндшпиль (31+)": phase_sql = " AND b.move_num > 30"

critical_sql = " AND b.move_num BETWEEN 10 AND 15" if only_critical else ""
threat_sql = " AND b.missed_threat = 1" if only_missed_threat else ""

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "⚠️ Разбор зевков", "📚 Колода на сегодня", "⏱️ Первый зевок",
    "🎯 Тактические угрозы", "📊 P10/P90 метрики",
])

with tab1:
    df = query_df(f"""
        SELECT b.id, b.game_url, b.move_num, b.move_uci, b.loss_cp,
               b.eval_before, b.eval_after, b.pattern_tag, b.time_spent,
               b.player_is_white, b.what, b.missed_threat,
               b.fen_before, b.best_move_uci,
               g.white, g.black, g.pgn, date(g.end_time, 'unixepoch', '+3 hours') AS dt
        FROM blunders b JOIN games g ON g.url = b.game_url
        WHERE b.is_my_blunder = 1 AND b.is_berserk = 0 AND b.is_instant = 0
          AND g.is_lag = 0 AND g.is_cheater = 0 AND g.end_time >= ?
          AND b.loss_cp >= ? {phase_sql}{critical_sql}{threat_sql}
        ORDER BY b.loss_cp DESC LIMIT 300
    """, (ts, min_loss))

    if df.empty:
        st.info("Нет зевков под фильтр.")
    else:
        df_show = df[["dt", "white", "black", "move_num", "move_uci", "loss_cp", "pattern_tag", "missed_threat", "what"]].copy()
        df_show.columns = ["дата", "белые", "чёрные", "ход", "UCI", "потеря CP", "паттерн", "угроза?", "что случилось"]
        df_show["угроза?"] = df_show["угроза?"].apply(lambda x: "⚠️ Да" if x == 1 else "Нет")
        st.dataframe(df_show, use_container_width=True, hide_index=True)

        st.divider()

        def format_blunder(row_id):
            r = df[df["id"] == row_id].iloc[0]
            return f"{r['dt']} | {r['white'][:10]} vs {r['black'][:10]} | Ход {r['move_num']} | Потеря {r['loss_cp']} CP"

        selected_id = st.selectbox("Выбери зевок для разбора:", df["id"].tolist(), format_func=format_blunder)
        row = df[df["id"] == selected_id].iloc[0]

        fen = row["fen_before"]
        if not fen:
            fen = fen_before_move(row["pgn"], int(row["move_num"]), bool(row["player_is_white"]))

        c1, c2 = st.columns([1, 1])
        with c1:
            if fen:
                st.markdown(render_board_html(fen, played_uci=row["move_uci"], size=440), unsafe_allow_html=True)
            else:
                st.error("Не удалось восстановить позицию из PGN.")
        with c2:
            st.markdown(f"**Дата:** {row['dt']}")
            st.markdown(f"**Партия:** {row['white']} — {row['black']}")
            st.markdown(f"**Ход:** {row['move_num']} ({row['move_uci']})")
            st.markdown(f"**Потеря:** {row['loss_cp']} CP")

            if row["missed_threat"] == 1:
                st.warning("⚠️ **Пропущенная угроза!** На следующем ходу соперник нанёс тактический удар.")

            if row["time_spent"]:
                st.markdown(f"**Время на ход:** {row['time_spent']:.1f} сек")

            if fen:
                if row["best_move_uci"]:
                    try:
                        import chess
                        b = chess.Board(fen)
                        best_san = b.san(chess.Move.from_uci(row["best_move_uci"]))
                    except Exception:
                        best_san = row["best_move_uci"]
                else:
                    best_san = get_best_move_san(fen)
                if best_san:
                    st.success(f"💡 Лучший ход (Stockfish): **{best_san}**")
                st.code(fen, language="text")

            st.divider()
            if st.button("🔬 Открыть партию в Анализаторе", type="primary", use_container_width=True):
                st.session_state["analyze_pgn"] = row["pgn"]
                st.session_state["analyze_fen"] = None
                st.switch_page("pages/6_Analysis.py")