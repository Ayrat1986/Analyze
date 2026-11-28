# ============================================================
# web_dashboard/app.py — Главная страница (v20.4)
# FIX: Вывод 4-факторного CombR v2 (Мышление, Интуиция,
#      Ощущения, Чувства) и актуальная ссылка на Trainer.
# ============================================================
import json
import os
import subprocess
import sys

WEB_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(WEB_DIR)
SRC_DIR = os.path.join(BASE_DIR, "src")
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from analysis.dashboard_helpers import get_daily_metrics_trend, key_numbers
from utils.sync_to_turso import sync_if_needed

st.set_page_config(page_title="Дашборд", page_icon="🏆", layout="wide")


def _can_run_local_pipeline() -> bool:
    """True только на локальном ПК, где есть run.py и установлен Stockfish."""
    if os.environ.get("STREAMLIT_SHARING_MODE") or str(BASE_DIR).startswith("/mount/src"):
        return False
    if not os.path.exists(os.path.join(SRC_DIR, "run.py")):
        return False
    cfg_path = os.path.join(BASE_DIR, "data", "config.json")
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                sf_path = json.load(f).get("stockfish_path", "")
            return bool(sf_path and os.path.exists(sf_path))
        except Exception:
            return False
    return False


def _auto_sync_on_startup():
    if st.session_state.get("_turso_startup_checked"):
        return
    st.session_state["_turso_startup_checked"] = True
    try:
        if sync_if_needed(quiet=True):
            st.cache_data.clear()
            st.toast("☁️ Новые партии автоматически выгружены в Turso", icon="✅")
    except Exception:
        pass


_auto_sync_on_startup()


@st.cache_data(ttl=3600)
def load_key_numbers():
    return key_numbers()


@st.cache_data(ttl=3600)
def load_trend(days=30):
    return get_daily_metrics_trend(days)


# --- Заголовок ---
col_title, col_btn = st.columns([4, 1])
with col_title:
    st.title("🏆 Шахматный дашборд")
    st.caption("Твой потенциал, скорость и результат в одном месте.")
with col_btn:
    if _can_run_local_pipeline():
        if st.button("🔄 Обновить данные (run.py)", use_container_width=True):
            with st.spinner("Запускаю конвейер и синхронизацию с Turso..."):
                result = subprocess.run(
                    [sys.executable, os.path.join(SRC_DIR, "run.py")],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    st.success("Данные обновлены и синхронизированы с Turso!")
                    st.cache_data.clear()
                else:
                    st.error(f"Ошибка: {result.stderr[:200]}")

st.divider()

# --- Ключевые цифры (90 дней + 4 контура CombR v2) ---
kn = load_key_numbers()
games = kn.get("Партий:", 0)
winrate = kn.get("Winrate:", "—")
acpl = kn.get("ACPL:", "—")
perf = kn.get("Perf (90д):", "—")

trend = load_trend(30)
if trend:
    latest = trend[-1]
    gamr_fallback = latest["GameR"]
    speedr_fallback = latest["SpeedR"]
    combr_fallback = latest["CombR"]
    avg_t_str = f"AvgT {latest.get('AvgT', 0)} сек"
else:
    gamr_fallback = speedr_fallback = combr_fallback = 0
    avg_t_str = "—"

col1, col2, col3, col4 = st.columns(4)
col1.metric("Партий (90д)", games, delta=f"Win: {winrate}")
col2.metric("GameR (Мышление)", kn.get("  (Мышление):", gamr_fallback), delta=f"ACPL {acpl}")
col3.metric("SpeedR (Интуиция)", kn.get("  (Интуиция):", speedr_fallback), delta=avg_t_str)
col4.metric("CombR v2 (Потенциал)", kn.get("CombR v2:", combr_fallback), delta=f"Perf {perf}")

c_state, c_aggr, c_feel, c_mom = st.columns(4)
c_state.metric("Состояние (90д)", kn.get("Состояние:", "—"))
c_aggr.metric("AggrR (Ощущения)", kn.get("  (Ощущения):", "—"))
c_feel.metric("StateR (Чувства)", kn.get("  (Чувства):", "—"))
c_mom.metric("Моментум после зевка", kn.get("Моментум после зевка:", "—"))

st.divider()

# --- График тренда ---
st.subheader("📈 Тренд за 30 дней (GameR vs SpeedR vs CombR vs Perf)")
if trend:
    df = pd.DataFrame(trend)
    df["Дата"] = pd.to_datetime(df["Дата"])

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["Дата"], y=df["GameR"], mode="lines+markers", name="GameR", line=dict(color="#00CC96", width=3)))
    fig.add_trace(go.Scatter(x=df["Дата"], y=df["SpeedR"], mode="lines+markers", name="SpeedR", line=dict(color="#EF553B", width=3)))
    fig.add_trace(go.Scatter(x=df["Дата"], y=df["CombR"], mode="lines+markers", name="CombR", line=dict(color="#AB63FA", width=3, dash="dot")))
    fig.add_trace(go.Scatter(x=df["Дата"], y=df["Perf"], mode="lines+markers", name="Perf", line=dict(color="#FFA15A", width=2)))
    fig.add_trace(go.Scatter(x=df["Дата"], y=df["Rating"], mode="lines+markers", name="Рейтинг", line=dict(color="#636EFA", width=3, dash="dash")))

    fig.update_layout(
        hovermode="x unified",
        height=400,
        margin=dict(l=0, r=0, t=30, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Нет данных за последние 30 дней.")

st.divider()

st.subheader("🚀 Быстрый доступ")
col_a, col_b, col_c = st.columns(3)
col_a.info("📖 **00_INDEX.txt** — Полный обзор в корне проекта.")
col_b.info("🎯 **Trainer** — Умная колода твоих зевков в боковом меню.")
col_c.info("📊 **00_INDEX.txt** — Смотри на P90 (дно). Цель: 70.")