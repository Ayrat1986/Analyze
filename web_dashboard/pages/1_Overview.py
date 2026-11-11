# web_dashboard/pages/1_Overview.py
import os
import re
import streamlit as st
import plotly.express as px
import pandas as pd
from datetime import datetime, timedelta, timezone

st.set_page_config(page_title="Обзор", page_icon="📊", layout="wide")
from utils.db import query_df, cutoff_ts
from core.метрики import game_rating

st.title("📊 Обзор (Overview)")

# ---- БОКОВАЯ ПАНЕЛЬ ----
with st.sidebar:
    st.header("⚙️ Настройки")
    days = st.slider("Период для графиков (дней)", 7, 365, 90, 1)
    hide_cheaters = st.checkbox("Скрыть лаги и читеров", value=True)

ts = cutoff_ts(days)
where_extra = " AND is_lag=0 AND is_cheater=0" if hide_cheaters else ""

# ============================================================
# БЛОК 1: P10 / P50 / P90 / StdDev
# ============================================================
st.subheader("🎯 Дно и потолок (P10 / P50 / P90 / StdDev)")

df_90 = query_df("""
    SELECT acpl FROM games
    WHERE acpl > 0 AND end_time >= ? AND is_lag=0 AND is_cheater=0
""", (cutoff_ts(90),))

if not df_90.empty and len(df_90) >= 10:
    vals = sorted(df_90["acpl"].tolist())
    n = len(vals)
    p10 = vals[int(n * 0.1)]
    p50 = vals[int(n * 0.5)]
    p90 = vals[int(n * 0.9)]
    stddev = df_90["acpl"].std()
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("P10 (потолок)", f"{p10:.1f}", f"GameR {game_rating(p10):.0f}", delta_color="off")
    c2.metric("P50 (медиана)", f"{p50:.1f}", f"GameR {game_rating(p50):.0f}", delta_color="off")
    c3.metric("P90 (дно)", f"{p90:.1f}", f"GameR {game_rating(p90):.0f}", delta_color="off")
    c4.metric("StdDev (разброс)", f"{stddev:.1f}", "Цель: <15", delta_color="inverse")
    
    if stddev > 25:
        st.error(f"⚠️ **Нестабильно (StdDev {stddev:.1f})**. Главная цель — поднять P90 (дно) с {p90:.0f} до 70.")
    elif stddev < 15:
        st.success(f"✅ **Отлично (StdDev {stddev:.1f})**. Ты играешь стабильно.")
    else:
        st.info(f"➡️ **Средне (StdDev {stddev:.1f})**. Есть куда расти.")
else:
    st.warning("Мало данных для P10/P90 (нужно 10+ партий).")

st.divider()

# ============================================================
# БЛОК 2: РЕЙТИНГ vs ВРЕМЯ
# ============================================================
st.subheader("⏱️ Рейтинг vs Время на ход")
st.caption("Гипотеза: 0.9с → 2800, 1.0с → 2700, 1.1с → 2600. Проверь, совпадает ли.")

try:
    from analysis.psych_state.speed_rating import _compute_avg_time
    from analysis.psych_state.common import _is_player_white

    windows_data = []
    for w in [1, 2, 7, 30, 90]:
        ts_w = cutoff_ts(w)
        df_w = query_df("""
            SELECT AVG(acpl) AS avg_acpl, AVG(my_rating) AS avg_r, COUNT(*) AS n
            FROM games
            WHERE end_time >= ? AND is_lag=0 AND is_cheater=0
              AND my_rating > 0 AND acpl > 0
        """, (ts_w,))
        if not df_w.empty and df_w["n"].iloc[0] > 0:
            avg_acpl = df_w["avg_acpl"].iloc[0]
            avg_r = df_w["avg_r"].iloc[0]

            # avg_time через clocks
            df_time = query_df("""
                SELECT clocks, eval_history, white, time_control
                FROM games
                WHERE end_time >= ? AND is_lag=0 AND is_cheater=0
                  AND my_rating > 0 AND acpl > 0
                  AND clocks IS NOT NULL AND clocks != '[]'
                  AND eval_history IS NOT NULL AND eval_history != '[]'
            """, (ts_w,))
            avg_times = []
            if not df_time.empty:
                for _, row in df_time.iterrows():
                    piw = _is_player_white(row["white"])
                    t = _compute_avg_time(row["clocks"], row["eval_history"], piw, row["time_control"])
                    if t:
                        avg_times.append(t["avg"])
            avg_time = sum(avg_times) / len(avg_times) if avg_times else 0

            windows_data.append({
                "Окно": f"{w} дн.",
                "Игр": int(df_w["n"].iloc[0]),
                "Ср. время": round(avg_time, 2),
                "ACPL": round(avg_acpl, 1),
                "Рейтинг": round(avg_r),
            })

    if windows_data:
        time_df = pd.DataFrame(windows_data)
        st.dataframe(time_df, use_container_width=True, hide_index=True)

        fig = px.scatter(
            time_df, x="Ср. время", y="Рейтинг",
            size="Игр", text="Окно",
            title="Время на ход vs Рейтинг (размер = число партий)",
        )
        fig.update_traces(textposition="top center")
        st.plotly_chart(fig, use_container_width=True)
except ImportError as e:
    st.info(f"Рейтинг vs Время: модуль не найден ({e}). Запусти 09_psych_state.py.")

st.divider()

# ============================================================
# БЛОК 3: ТАБЛИЦА ТРЕНДОВ (с P10/P90)
# ============================================================
st.subheader("📈 Динамика по окнам (Рейтинг, GameR, P10, P90)")
windows = [1, 2, 7, 30, 90]
trend_data = []

base_df = query_df("""
    SELECT AVG(my_rating) AS avg_r, AVG(acpl) AS acpl, AVG(opp_rating) AS opp,
           SUM(won) AS wins, SUM(draw) AS draws, COUNT(*) AS n
    FROM games
    WHERE my_rating > 0 AND end_time >= ? AND is_lag=0 AND is_cheater=0
""", (cutoff_ts(90),))

if not base_df.empty and pd.notna(base_df["avg_r"].iloc[0]):
    b = base_df.iloc[0]
    base_90 = b["avg_r"]
    base_gamr = game_rating(b["acpl"] or 0)
    score = (b["wins"] + 0.5 * b["draws"]) / b["n"] if b["n"] else 0
    base_perf = b["opp"] + (score - 0.5) * 800 if b["opp"] else 0
else:
    base_90 = base_gamr = base_perf = 0

for w in windows:
    df_w = query_df("""
        SELECT * FROM games WHERE end_time >= ? AND is_lag=0 AND is_cheater=0
    """, (cutoff_ts(w),))

    if df_w.empty:
        trend_data.append({
            "Окно": f"{w} дн.", "Игр": 0, "Win%": 0, "ACPL": 0,
            "Рейтинг": 0, "ΔР": 0, "GameR": 0, "P10": 0, "P90": 0,
        })
        continue

    n = len(df_w)
    wins = int(df_w["won"].sum())
    draws = int(df_w["draw"].sum())
    avg_acpl = df_w["acpl"].mean()
    avg_opp = df_w["opp_rating"].mean()

    valid_ratings = df_w[df_w["my_rating"] > 0]["my_rating"]
    avg_r = valid_ratings.mean() if not valid_ratings.empty else 0

    gamr = game_rating(avg_acpl) if avg_acpl else 0
    score = (wins + 0.5 * draws) / n if n else 0
    perf = avg_opp + (score - 0.5) * 800 if avg_opp else 0

    valid_acpl = sorted(df_w[df_w["acpl"] > 0]["acpl"].tolist())
    if len(valid_acpl) >= 10:
        p10 = valid_acpl[int(len(valid_acpl) * 0.1)]
        p90 = valid_acpl[int(len(valid_acpl) * 0.9)]
    else:
        p10 = p90 = 0

    trend_data.append({
        "Окно": f"{w} дн.",
        "Игр": n,
        "Win%": round(wins / n * 100, 1),
        "ACPL": round(avg_acpl, 1),
        "Рейтинг": round(avg_r) if avg_r else 0,
        "ΔР": round(avg_r - base_90) if (avg_r and base_90) else 0,
        "GameR": round(gamr),
        "P10": round(p10),
        "P90": round(p90),
    })

trend_df = pd.DataFrame(trend_data)
st.dataframe(trend_df, use_container_width=True, hide_index=True)
st.caption("P90 — твоё дно. Если оно падает — ты растёшь. P10 — твой потолок (не должен расти).")

st.divider()

# ============================================================
# БЛОК 4: ГРАФИК РЕЙТИНГА
# ============================================================
st.subheader("📈 Динамика рейтинга, GameR и Перформанса")
daily_df = query_df(f"""
    SELECT date(end_time, 'unixepoch', '+3 hours') AS day, 
           AVG(my_rating) AS rating, AVG(acpl) AS acpl,
           AVG(opp_rating) AS avg_opp, AVG(won) AS win_rate, AVG(draw) AS draw_rate
    FROM games 
    WHERE end_time >= ?{where_extra} AND my_rating > 0
    GROUP BY day ORDER BY day
""", (ts,))

if not daily_df.empty:
    daily_df["day"] = pd.to_datetime(daily_df["day"])
    daily_df["GameR"] = daily_df["acpl"].apply(lambda x: game_rating(x) if x else 0)
    daily_df["Perf"] = daily_df["avg_opp"] + (
        (daily_df["win_rate"] + 0.5 * daily_df["draw_rate"]) - 0.5
    ) * 800

    fig = px.line(
        daily_df, x="day", y=["rating", "GameR", "Perf"],
        markers=True,
        labels={"value": "Рейтинг", "variable": "Метрика", "day": "Дата"},
        title="Твой Рейтинг, Потенциал (GameR) и Перформанс",
    )
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ============================================================
# БЛОК 5: ТРЕНЕР И ПОТЕНЦИАЛ
# ============================================================
col1, col2 = st.columns(2)

with col1:
    st.subheader("🎯 Совет тренера на сегодня")
    coach_path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..", "reports", "coach_voice.txt"
    ))
    if os.path.exists(coach_path):
        with open(coach_path, "r", encoding="utf-8") as f:
            coach_text = f.read()
        mantra_match = re.search(r'МАНТРА ДНЯ:\s*\n\s*«(.*?)»', coach_text)
        mantra = mantra_match.group(1) if mantra_match else "Играй не против соперника, а против хаоса."
        st.info(f"🗣️ **Мантра дня:**\n«{mantra}»")

        do_match = re.search(r'ДЕЛАТЬ СЕГОДНЯ:(.*?)НЕ ДЕЛАТЬ:', coach_text, re.DOTALL)
        if do_match:
            actions = [line.strip() for line in do_match.group(1).strip().split('\n') if line.strip()]
            st.markdown("**План на сегодня:**")
            for act in actions[:5]:
                st.markdown(act)
        with st.expander("Показать полный текст"):
            st.code(coach_text, language="text")
    else:
        st.info("coach_voice.txt ещё не создан.")

with col2:
    st.subheader("🚀 Потенциал (7 дней)")
    pot_path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..", "reports", "potential_tracker.txt"
    ))
    if os.path.exists(pot_path):
        with open(pot_path, "r", encoding="utf-8") as f:
            pot_text = f.read()
        blocks = pot_text.split("=" * 60)
        for block in blocks:
            if "ОКНО: 7 ДНЕЙ" in block:
                st.code("=" * 60 + block, language="text")
                break
        else:
            st.info("Нет данных за 7 дней.")
        with st.expander("Показать за 1, 2, 30, 90 дней"):
            st.code(pot_text, language="text")
    else:
        st.info("potential_tracker.txt ещё не создан.")