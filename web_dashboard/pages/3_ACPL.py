# web_dashboard/pages/3_ACPL.py
import streamlit as st
import plotly.express as px
import pandas as pd
import os
import re

st.set_page_config(page_title="Точность (ACPL)", page_icon="🎯", layout="wide")
from utils.db import query_df, cutoff_ts

st.title("🎯 Точность (ACPL) и Процент побед")

with st.sidebar:
    days = st.slider("Период (дней)", 7, 365, 90, 1)

ts = cutoff_ts(days)
df = query_df("""
    SELECT won, draw, opp_rating, my_rating, critical_moments, game_length,
           reason, acpl, acpl_opening, acpl_middlegame, acpl_endgame, accuracy
    FROM games WHERE end_time >= ? AND is_lag=0 AND is_cheater=0
""", (ts,))

if df.empty:
    st.warning("Нет данных.")
    st.stop()

df["result"] = df.apply(
    lambda r: "Победа" if r["won"] == 1
    else ("Ничья" if r["draw"] == 1 else "Поражение"),
    axis=1,
)

# ============================================================
# БЛОК 1: СТАБИЛЬНОСТЬ (StdDev)
# ============================================================
st.subheader("🎖️ Стабильность (Разброс ACPL)")
if not df.empty:
    mean = df["acpl"].mean()
    median = df["acpl"].median()
    stdev = df["acpl"].std()
    p10 = df["acpl"].quantile(0.1)
    p90 = df["acpl"].quantile(0.9)
    
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Средний", f"{mean:.1f}")
    c2.metric("Медиана", f"{median:.1f}")
    c3.metric("StdDev", f"{stdev:.1f}", delta="-цель: <15", delta_color="inverse")
    c4.metric("P10 (лучшие)", f"{p10:.1f}")
    c5.metric("P90 (худшие)", f"{p90:.1f}")
    
    if stdev > 25:
        st.error(f"⚠️ **Нестабильно (StdDev {stdev:.1f})**. Главная цель — сжать разброс, а не только снизить средний ACPL.")
    elif stdev < 15:
        st.success(f"✅ **Отлично (StdDev {stdev:.1f})**. Ты играешь стабильно.")
    else:
        st.info(f"➡️ **Средне (StdDev {stdev:.1f})**. Есть куда расти.")

st.divider()

# ============================================================
# БЛОК 2: GAME RATING vs PERF (по рейтингам)
# ============================================================
st.subheader("🚀 Game Rating vs Performance по рейтингам")
perf_text_path = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "reports", "game_rating_vs_perf.txt"
))
if os.path.exists(perf_text_path):
    with open(perf_text_path, "r", encoding="utf-8") as f:
        st.code(f.read(), language="text")
else:
    st.warning("game_rating_vs_perf.txt не найден. Запусти 10_psych_rating.py.")

st.divider()

# ============================================================
# БЛОК 3: ACPL ПО ФАЗАМ (Violin) - (оставляем как было)
# ============================================================
st.subheader("📊 ACPL по фазам игры")

def draw_endgame_violin(data, title_text):
    long_df = data.melt(
        id_vars=["result"],
        value_vars=["acpl_opening", "acpl_middlegame", "acpl_endgame"],
        var_name="phase", value_name="acpl_value",
    )
    long_df = long_df[(long_df["acpl_value"] > 0) & (long_df["acpl_value"] < 300)]
    long_df["phase"] = long_df["phase"].map({
        "acpl_opening": "Дебют",
        "acpl_middlegame": "Миттельшпиль",
        "acpl_endgame": "Эндшпиль",
    })
    fig = px.violin(
        long_df, x="phase", y="acpl_value", color="result",
        box=True, points="outliers",
        labels={"acpl_value": "ACPL (потеря в CP)", "phase": "Фаза игры", "result": "Результат"},
        title=title_text,
        color_discrete_map={"Победа": "#28a745", "Ничья": "#6c757d", "Поражение": "#dc3545"},
    )
    st.plotly_chart(fig, use_container_width=True)

tab1, tab2 = st.tabs(["Все партии", "Без флагов (техника)"])
with tab1:
    draw_endgame_violin(df, "Распределение ACPL (Все)")
with tab2:
    df_no_flag = df[df["reason"] != "просрочка"]
    draw_endgame_violin(df_no_flag, "Распределение ACPL (Без флагов)")