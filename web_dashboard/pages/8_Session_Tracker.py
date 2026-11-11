# web_dashboard/pages/8_Session_Tracker.py
import sys
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
from utils.db import query_df
from core.метрики import game_rating

st.set_page_config(page_title="Микро-сессии", page_icon="⚡", layout="wide")

st.title("⚡ Микро-сессии (Live Tracker)")
st.caption("Анализ твоей последней сессии. Обнови страницу (Rerun) после игры, чтобы увидеть импульс.")

# ============================================================
# 1. ВЫТАСКИВАЕМ ПОСЛЕДНЮЮ СЕССИЮ
# ============================================================
df_all = query_df("""
    SELECT end_time, acpl, won, draw, opp_rating, my_rating, accuracy
    FROM games WHERE is_lag=0 AND is_cheater=0
    ORDER BY end_time DESC LIMIT 100
""")

if df_all.empty:
    st.warning("Нет данных для анализа.")
    st.stop()

last_session = []
prev_time = None

for _, row in df_all.iterrows():
    if prev_time is None:
        last_session.append(row)
        prev_time = row['end_time']
    else:
        if (prev_time - row['end_time']) <= 1800:
            last_session.append(row)
            prev_time = row['end_time']
        else:
            break

df = pd.DataFrame(last_session[::-1]).reset_index(drop=True)
df["game_num"] = range(1, len(df) + 1)

df["GameR"] = df["acpl"].apply(lambda x: game_rating(x) if x > 0 else 0)
df["result"] = df.apply(
    lambda r: "Победа" if r["won"]
    else ("Ничья" if r["draw"] else "Поражение"),
    axis=1,
)

# ============================================================
# 2. СВОДКА ПО СЕССИИ
# ============================================================
n = len(df)
wins = int(df["won"].sum())
win_rate = wins / n * 100 if n else 0

valid_acpl = df[df["acpl"] > 0]
avg_acpl = valid_acpl["acpl"].mean() if not valid_acpl.empty else 0
avg_gamr = valid_acpl["GameR"].mean() if not valid_acpl.empty else 0

st.subheader(f"📊 Твоя последняя сессия ({n} партий)")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Винрейт", f"{win_rate:.1f}%")
c2.metric("Средний ACPL", f"{avg_acpl:.1f}" if avg_acpl else "—")
c3.metric("GameR сессии", f"{avg_gamr:.0f}" if avg_gamr else "—")
c4.metric("Длительность", f"{int((df['end_time'].max() - df['end_time'].min()) / 60)} мин")

# ============================================================
# 3. ГРАФИК РЕЙТИНГА ПО ТОЧНОСТИ (GameR)
# ============================================================
st.subheader("📈 Импульс сессии (GameR по партиям)")
st.markdown("Показывает, как росло качество твоих ходов от партии к партии.")

df_plot = df[df["GameR"] > 0]

if not df_plot.empty:
    fig = px.line(
        df_plot, x="game_num", y="GameR", markers=True,
        labels={
            "game_num": "Номер партии",
            "GameR": "GameR (Рейтинг по точности)",
        },
        title="Твой потенциал (GameR) по ходу сессии",
    )

    ts_7d = int((datetime.now().timestamp()) - 7 * 86400)
    norm_df = query_df(
        "SELECT AVG(acpl) AS acpl FROM games "
        "WHERE end_time >= ? AND is_lag=0 AND is_cheater=0 AND acpl>0",
        (ts_7d,),
    )
    norm_gamr = None
    if not norm_df.empty and pd.notna(norm_df.iloc[0]["acpl"]):
        norm_acpl = norm_df.iloc[0]["acpl"]
        norm_gamr = game_rating(norm_acpl)
        fig.add_hline(
            y=norm_gamr, line_dash="dash", line_color="gray",
            annotation_text=f"Норма 7д (GameR {norm_gamr:.0f})",
        )

    fig.update_layout(height=400)
    st.plotly_chart(fig, use_container_width=True)

    # FIX: текстовый вердикт vs нормы 7 дней
    if norm_gamr:
        delta = avg_gamr - norm_gamr
        if delta > 30:
            st.success(f"🔥 Твоя сессия **лучше нормы 7д на {delta:+.0f}** пунктов GameR.")
        elif delta < -30:
            st.warning(f"⚠️ Твоя сессия **хуже нормы 7д на {delta:+.0f}** пунктов GameR.")
        else:
            st.info(f"➡️ Твоя сессия **в пределах нормы 7д** (Δ {delta:+.0f} пунктов).")
else:
    st.warning("В этой сессии нет партий с проанализированным ACPL.")

# ============================================================
# 4. СРАВНЕНИЕ С ОКНАМИ 1, 2, 7, 30, 90 ДНЕЙ
# ============================================================
st.divider()
st.subheader("⚖️ Твоя сессия vs Окна (Тренд)")

windows = [1, 2, 7, 30, 90]
trend_data = []

trend_data.append({
    "Окно": "🔥 Эта сессия",
    "Игр": n,
    "Win%": round(win_rate, 1),
    "ACPL": round(avg_acpl, 1) if avg_acpl else 0,
    "GameR": round(avg_gamr) if avg_gamr else 0,
})

for w in windows:
    ts = int((datetime.now().timestamp()) - w * 86400)
    df_w = query_df(
        "SELECT won, draw, acpl FROM games "
        "WHERE end_time >= ? AND is_lag=0 AND is_cheater=0 AND acpl > 0",
        (ts,),
    )

    if df_w.empty:
        trend_data.append({
            "Окно": f"{w} дн.", "Игр": 0,
            "Win%": 0, "ACPL": 0, "GameR": 0,
        })
        continue

    n_w = len(df_w)
    wins_w = int(df_w["won"].sum())
    draws_w = int(df_w["draw"].sum())
    avg_acpl_w = df_w["acpl"].mean()
    gamr_w = game_rating(avg_acpl_w)

    trend_data.append({
        "Окно": f"{w} дн.",
        "Игр": n_w,
        "Win%": round(wins_w / n_w * 100, 1),
        "ACPL": round(avg_acpl_w, 1),
        "GameR": round(gamr_w),
    })

trend_df = pd.DataFrame(trend_data)
st.dataframe(trend_df, use_container_width=True, hide_index=True)

# ============================================================
# 5. АНАЛИЗ "ВОСХОДА" ИЛИ "ТИЛЬТА"
# ============================================================
st.divider()
st.subheader("🔥 Вердикт по импульсу")

if len(valid_acpl) >= 3:
    mid = len(valid_acpl) // 2
    first_half = valid_acpl.iloc[:mid]
    second_half = valid_acpl.iloc[mid:]

    gr_1 = first_half["GameR"].mean()
    gr_2 = second_half["GameR"].mean()

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Первая половина:**")
        st.write(f"GameR: {gr_1:.0f}")
    with col2:
        st.markdown(f"**Вторая половина:**")
        st.write(f"GameR: {gr_2:.0f}")

    if gr_2 > gr_1 + 50:
        st.success("🚀 **ВХОД В ПОТОК!** Ты разогрелся и начал играть значительно лучше.")
    elif gr_2 < gr_1 - 50:
        st.error("📉 **ТИЛЬТ/УСТАЛОСТЬ.** Ты сгорел к концу сессии. Пора сделать перерыв.")
    else:
        st.info("➡️ Стабильная игра. Без резких скачков.")
else:
    st.info("Слишком короткая сессия для анализа импульса (нужно хотя бы 3 проанализированные партии).")

# ============================================================
# 6. СЫРОЙ ОТЧЕТ
# ============================================================
st.divider()
pot_path = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "reports", "micro_sessions.txt"
))
if os.path.exists(pot_path):
    with open(pot_path, "r", encoding="utf-8") as f:
        with st.expander("📄 Показать micro_sessions.txt", expanded=False):
            st.code(f.read(), language="text")