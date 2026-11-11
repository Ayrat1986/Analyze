# web_dashboard/pages/4_Endurance.py
import streamlit as st
import plotly.express as px
import pandas as pd
import os

st.set_page_config(page_title="Выносливость (Endurance)", page_icon="🏃", layout="wide")
from utils.db import query_df, cutoff_ts

st.title("🏃 Выносливость (Endurance)")


def render_endurance(days):
    ts = cutoff_ts(days)
    df = query_df("""
        WITH ranked AS (
            SELECT url, end_time, acpl, accuracy, won,
                   LAG(end_time) OVER (ORDER BY end_time) as prev_time
            FROM games WHERE is_lag=0 AND is_cheater=0 AND acpl > 0
              AND end_time >= ?
        ),
        sessions AS (
            SELECT *,
                SUM(CASE WHEN prev_time IS NULL
                         OR (end_time - prev_time) > 1800 THEN 1 ELSE 0 END)
                OVER (ORDER BY end_time) as session_id
            FROM ranked
        ),
        game_nums AS (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY session_id ORDER BY end_time
            ) as game_num
            FROM sessions
        )
        SELECT
            CASE
                WHEN game_num = 1 THEN '1-я'
                WHEN game_num <= 3 THEN '2-3'
                WHEN game_num <= 5 THEN '4-5'
                WHEN game_num <= 10 THEN '6-10'
                WHEN game_num <= 20 THEN '11-20'
                WHEN game_num <= 50 THEN '21-50'
                ELSE '50+'
            END AS bucket,
            AVG(acpl) AS avg_acpl,
            AVG(accuracy) AS avg_acc,
            AVG(won) * 100 AS win_rate,
            COUNT(*) AS cnt
        FROM game_nums GROUP BY bucket
    """, (ts,))

    if df.empty:
        st.warning(f"Нет данных за последние {days} дней.")
        return

    order = ["1-я", "2-3", "4-5", "6-10", "11-20", "21-50", "50+"]
    df["bucket"] = pd.Categorical(df["bucket"], categories=order, ordered=True)
    df = df.sort_values("bucket")
    df["avg_acpl"] = df["avg_acpl"].round(1)

    base_acpl = df[df["bucket"] == "1-я"]["avg_acpl"].values[0]

    fig = px.bar(
        df, x="bucket", y="avg_acpl", text="avg_acpl",
        hover_data=["cnt"],
        color="avg_acpl", color_continuous_scale="RdYlGn",
        title=f"Средний ACPL по номеру партии (Окно: {days} дней)",
    )
    fig.update_traces(texttemplate='%{text:.1f}', textposition='outside')
    fig.add_hline(
        y=base_acpl, line_dash="dash", line_color="gray",
        annotation_text=f"База: {base_acpl:.0f} CP",
    )

    # Визуальная линия предела выносливости (18-я партия)
    if "11-20" in df["bucket"].values and days >= 30:
        fig.add_vline(
            x=3.5, line_dash="dot", line_color="red",
            annotation_text="Предел ~18 партий",
            annotation_position="top",
        )

    fig.update_xaxes(title="Номер партии в сессии")
    fig.update_yaxes(title="Средний ACPL (потеря в CP)")
    st.plotly_chart(fig, use_container_width=True)

    df_show = df.copy()
    df_show.columns = [
        "Номер партии", "Ср. ACPL", "Ср. Точность %", "Винрейт %", "Кол-во партий",
    ]
    st.dataframe(df_show, use_container_width=True, hide_index=True)
    st.caption(
        "💡 `Ср. ACPL` — средняя потеря качества в сантипешках. "
        "`База` — ACPL в самых первых партиях сессии. "
        "Красная линия — порог, после которого ACPL стабильно растёт."
    )


tab1, tab2, tab3 = st.tabs(["📅 7 дней", "📅 30 дней", "📅 90 дней"])
with tab1:
    render_endurance(7)
with tab2:
    render_endurance(30)
with tab3:
    render_endurance(90)

st.divider()
st.subheader("🧠 Каскадный тильт по фазам")

cascade_path = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "reports", "cascade_tilt.txt"
))

if os.path.exists(cascade_path):
    with open(cascade_path, "r", encoding="utf-8") as f:
        cascade_text = f.read()
    
    with st.expander("📊 Показать отчёт cascade_tilt.txt", expanded=True):
        st.code(cascade_text, language="text")
else:
    st.warning("cascade_tilt.txt не найден. Запусти 09_psych_state.py.")