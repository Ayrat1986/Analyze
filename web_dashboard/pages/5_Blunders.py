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
    phases = st.selectbox(
        "Фаза", ["Все", "Дебют (1-10)", "Миттельшпиль (11-30)", "Эндшпиль (31+)"],
    )
    only_critical = st.checkbox("Только 'час X' (10-15 ход)", value=False)
    only_missed_threat = st.checkbox("Только пропущенные угрозы", value=False)

ts = cutoff_ts(days)
phase_sql = ""
if phases == "Дебют (1-10)":
    phase_sql = " AND b.move_num <= 10"
elif phases == "Миттельшпиль (11-30)":
    phase_sql = " AND b.move_num > 10 AND b.move_num <= 30"
elif phases == "Эндшпиль (31+)":
    phase_sql = " AND b.move_num > 30"

critical_sql = " AND b.move_num BETWEEN 10 AND 15" if only_critical else ""
threat_sql = " AND b.missed_threat = 1" if only_missed_threat else ""

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "⚠️ Разбор зевков",
    "📚 Колода на сегодня",
    "⏱️ Первый зевок",
    "🎯 Тактические угрозы",
    "📊 P10/P90 метрики",
])

# ==========================================
# ВКЛАДКА 1: РАЗБОР ЗЕВКОВ
# ==========================================
with tab1:
    df = query_df(f"""
        SELECT b.id, b.game_url, b.move_num, b.move_uci, b.loss_cp,
               b.eval_before, b.eval_after, b.pattern_tag, b.time_spent,
               b.player_is_white, b.what, b.missed_threat,
               b.fen_before, b.best_move_uci,
               g.white, g.black, g.pgn,
               date(g.end_time, 'unixepoch', '+3 hours') AS dt
        FROM blunders b JOIN games g ON g.url = b.game_url
        WHERE b.is_my_blunder = 1 AND b.is_berserk = 0 AND b.is_instant = 0
          AND g.is_lag = 0 AND g.is_cheater = 0 AND g.end_time >= ?
          AND b.loss_cp >= ? {phase_sql}{critical_sql}{threat_sql}
        ORDER BY b.loss_cp DESC LIMIT 300
    """, (ts, min_loss))

    if df.empty:
        st.info("Нет зевков под фильтр.")
    else:
        df_show = df[[
            "dt", "white", "black", "move_num", "move_uci",
            "loss_cp", "pattern_tag", "missed_threat", "what",
        ]].copy()
        df_show.columns = [
            "дата", "белые", "чёрные", "ход", "UCI",
            "потеря CP", "паттерн", "угроза?", "что случилось",
        ]
        df_show["угроза?"] = df_show["угроза?"].apply(
            lambda x: "⚠️ Да" if x == 1 else "Нет",
        )
        st.dataframe(df_show, use_container_width=True, hide_index=True)

        st.divider()

        def format_blunder(row_id):
            r = df[df["id"] == row_id].iloc[0]
            return (
                f"{r['dt']} | {r['white'][:10]} vs {r['black'][:10]} | "
                f"Ход {r['move_num']} | Потеря {r['loss_cp']} CP"
            )

        selected_id = st.selectbox(
            "Выбери зевок для разбора:",
            df["id"].tolist(), format_func=format_blunder,
        )
        row = df[df["id"] == selected_id].iloc[0]

        fen = row["fen_before"]
        if not fen:
            fen = fen_before_move(
                row["pgn"], int(row["move_num"]), bool(row["player_is_white"]),
            )

        c1, c2 = st.columns([1, 1])
        with c1:
            if fen:
                st.markdown(
                    render_board_html(fen, played_uci=row["move_uci"], size=440),
                    unsafe_allow_html=True,
                )
            else:
                st.error("Не удалось восстановить позицию из PGN.")
        with c2:
            st.markdown(f"**Дата:** {row['dt']}")
            st.markdown(f"**Партия:** {row['white']} — {row['black']}")
            st.markdown(f"**Ход:** {row['move_num']} ({row['move_uci']})")
            st.markdown(f"**Потеря:** {row['loss_cp']} CP")

            if row["missed_threat"] == 1:
                st.warning(
                    "⚠️ **Пропущенная угроза!** На следующем ходу "
                    "соперник нанёс тактический удар (взятие или мат)."
                )

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

            st.markdown(f"[🔗 Партия на chess.com]({row['game_url']})")

            st.divider()
            if fen and st.button("🔬 Открыть в Анализаторе",
                                 type="primary", use_container_width=True):
                st.session_state["analyze_pgn"] = row["pgn"]
                st.session_state["analyze_fen"] = None
                st.switch_page("pages/6_Analysis.py")

# ==========================================
# ВКЛАДКА 2: КОЛОДА НА СЕГОДНЯ
# ==========================================
with tab2:
    st.subheader("🎯 Колода на сегодня (20 FEN)")
    st.markdown(
        "Свежие зевки (последние 7 дней) + Топ-100 из истории. "
        "Тренируй в Lichess или в **Тренажёре** (с памятью прогресса)."
    )

    if st.button("🎯 Открыть Тренажёр (с памятью)", type="primary"):
        st.switch_page("pages/11_Trainer.py")

    fresh = query_df("""
        SELECT b.fen_before, b.move_num, b.loss_cp, b.best_move_uci,
               g.white, g.black, g.url, g.end_time
        FROM blunders b JOIN games g ON g.url = b.game_url
        WHERE g.is_lag=0 AND g.is_cheater=0 AND b.is_my_blunder=1
          AND b.is_berserk=0 AND b.is_instant=0 AND b.loss_cp > 150
          AND b.fen_before IS NOT NULL AND b.fen_before != ''
          AND g.end_time >= strftime('%s', 'now', '-7 days')
        ORDER BY b.loss_cp DESC LIMIT 20
    """)

    if fresh.empty:
        st.info("Нет свежих зевков за 7 дней. Отдыхай!")
    else:
        for i in range(0, len(fresh), 2):
            cols = st.columns(2)
            for j in range(2):
                if i + j < len(fresh):
                    r = fresh.iloc[i + j]
                    with cols[j]:
                        st.markdown(
                            f"**{r['white'][:12]} vs {r['black'][:12]}** "
                            f"(ход {r['move_num']}, потеря {r['loss_cp']} CP)"
                        )
                        st.markdown(
                            render_board_html(r['fen_before'], size=350),
                            unsafe_allow_html=True,
                        )
                        st.caption(
                            f"[Тренировать в Lichess]"
                            f"(https://lichess.org/analysis/standard/"
                            f"{r['fen_before'].replace(' ', '_')})"
                        )
                        st.divider()

# ==========================================
# ВКЛАДКА 3: ПЕРВЫЙ ЗЕВОК
# ==========================================
with tab3:
    st.subheader("⏱️ Когда происходит первый зевок?")
    st.caption("Твой 'час X' — 17-й ход. Окно 10-15 — замедлись.")

    first_move_df = query_df("""
        SELECT b.move_num AS move, COUNT(*) AS cnt
        FROM blunders b JOIN games g ON g.url = b.game_url
        WHERE g.is_lag=0 AND g.is_cheater=0
          AND b.is_my_blunder=1 AND b.is_berserk=0 AND b.is_instant=0
          AND b.loss_cp > 150
          AND b.move_num = (
              SELECT MIN(b2.move_num) FROM blunders b2
              WHERE b2.game_url = b.game_url
                AND b2.is_my_blunder=1 AND b2.is_berserk=0 AND b2.is_instant=0
                AND b2.loss_cp > 150
          )
        GROUP BY b.move_num ORDER BY b.move_num
    """)

    if not first_move_df.empty:
        fig = px.bar(
            first_move_df, x="move", y="cnt",
            labels={"move": "Номер хода", "cnt": "Первый зевок"},
            title="Распределение первого зевка по ходам (твой 'час X' — 17)",
        )
        fig.add_vline(x=17, line_dash="dash", line_color="red",
                      annotation_text="Час X = 17")
        fig.add_vrect(x0=10, x1=15, fillcolor="yellow", opacity=0.15,
                      annotation_text="Окно 10-15 (замедлись)")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Нет данных.")

    first_path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..", "reports", "first_blunder_report.txt"
    ))
    if os.path.exists(first_path):
        with open(first_path, "r", encoding="utf-8") as f:
            with st.expander("📊 Полный отчёт first_blunder_report.txt", expanded=False):
                st.code(f.read(), language="text")

# ==========================================
# ВКЛАДКА 4: ТАКТИЧЕСКИЕ УГРОЗЫ
# ==========================================
with tab4:
    st.subheader("🎯 Пропущенные тактические угрозы")
    threats_path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..", "reports", "missed_threats.txt"
    ))
    if os.path.exists(threats_path):
        with open(threats_path, "r", encoding="utf-8") as f:
            with st.expander("📊 Показать missed_threats.txt", expanded=True):
                st.code(f.read(), language="text")
    else:
        st.warning("missed_threats.txt не найден. Запусти 08_psych_focus.py.")

# ==========================================
# ВКЛАДКА 5: P10/P90 МЕТРИКИ ЗЕВКОВ
# ==========================================
with tab5:
    st.subheader("📊 Распределение зевков (P10 / P50 / P90)")
    st.caption("P10 = лёгкие зевки, P90 = катастрофические. Если P90 растёт — ты зеваешь хуже.")

    blunders_df = query_df("""
        SELECT b.loss_cp
        FROM blunders b JOIN games g ON g.url = b.game_url
        WHERE g.is_lag=0 AND g.is_cheater=0
          AND b.is_my_blunder=1 AND b.is_berserk=0 AND b.is_instant=0
          AND g.end_time >= ?
    """, (ts,))

    if not blunders_df.empty and len(blunders_df) >= 10:
        vals = sorted(blunders_df["loss_cp"].tolist())
        n = len(vals)
        p10 = vals[int(n * 0.1)]
        p50 = vals[int(n * 0.5)]
        p90 = vals[int(n * 0.9)]
        avg = sum(vals) / n

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("P10 (лёгкие)", f"{p10:.0f} CP")
        c2.metric("P50 (медиана)", f"{p50:.0f} CP")
        c3.metric("P90 (катастрофа)", f"{p90:.0f} CP")
        c4.metric("Среднее", f"{avg:.0f} CP")

        hist_df = pd.DataFrame({"loss_cp": vals})
        fig = px.histogram(
            hist_df, x="loss_cp", nbins=50,
            title="Распределение потерь в зевках",
            labels={"loss_cp": "Потеря (CP)", "count": "Зевков"},
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Мало данных для P10/P90 (нужно 10+ зевков).")