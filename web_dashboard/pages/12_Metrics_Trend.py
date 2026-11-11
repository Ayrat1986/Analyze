# ============================================================
# web_dashboard/pages/12_Metrics_Trend.py
# ============================================================
import sys
import os
import shutil

# --- ЖЕСТКИЙ СБРОС КЭША PYTHON ---
def clear_pycache(start_path):
    for root, dirs, files in os.walk(start_path):
        for d in dirs:
            if d == '__pycache__':
                shutil.rmtree(os.path.join(root, d), ignore_errors=True)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DIR = os.path.join(BASE_DIR, "src")

# Очищаем кэш в папке src и в папке этой страницы
clear_pycache(SRC_DIR)
clear_pycache(os.path.dirname(os.path.abspath(__file__)))
# ---------------------------------

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from analysis.dashboard_helpers import get_daily_metrics_trend

st.set_page_config(page_title="Metrics Trend", layout="wide")
st.title("📈 Тренд метрик (GameR vs SpeedR vs Perf)")

# Настройки
col1, col2 = st.columns([1, 3])
with col1:
    days = st.selectbox("Окно анализа", [7, 14, 30, 60, 90], index=2)

data = get_daily_metrics_trend(days)

if not data:
    st.warning(f"Нет данных за последние {days} дней.")
else:
    df = pd.DataFrame(data)
    df['Дата'] = pd.to_datetime(df['Дата'])
    
    # СТРАХОВКА (если колонки нет)
    if 'Rating' not in df.columns:
        df['Rating'] = 0

    # --- СРЕДНИЙ РЕЙТИНГ ЗА ПЕРИОД ---
    avg_rating_window = df['Rating'].mean()
    col_m1, col_m2, col_m3 = st.columns(3)
    # Если рейтинг 0, пишем "Нет данных", а не 0
    rating_display = f"{avg_rating_window:.0f}" if avg_rating_window > 0 else "—"
    col_m1.metric("Средний рейтинг за период", rating_display)
    col_m2.metric("Средний ACPL за период", f"{df['ACPL'].mean():.1f}")
    col_m3.metric("Среднее время на ход", f"{df['AvgT'].mean():.2f} сек")
    # ----------------------------------------------
    
    # Основной график
    st.subheader("Соотношение точности, скорости и результата")
    fig = go.Figure()
    
    # Линии
    fig.add_trace(go.Scatter(x=df['Дата'], y=df['GameR'], mode='lines+markers', name='GameR (Точность)', line=dict(color='#00CC96', width=3)))
    fig.add_trace(go.Scatter(x=df['Дата'], y=df['SpeedR'], mode='lines+markers', name='SpeedR (Скорость)', line=dict(color='#EF553B', width=3)))
    fig.add_trace(go.Scatter(x=df['Дата'], y=df['CombR'], mode='lines+markers', name='CombR (Общий)', line=dict(color='#AB63FA', width=3, dash='dot')))
    fig.add_trace(go.Scatter(x=df['Дата'], y=df['Perf'], mode='lines+markers', name='Perf (Результат)', line=dict(color='#FFA15A', width=2)))
    
    # НОВАЯ ЛИНИЯ: Реальный рейтинг
    if 'Rating' in df.columns and df['Rating'].sum() > 0:
        fig.add_trace(go.Scatter(x=df['Дата'], y=df['Rating'], mode='lines+markers', name='Рейтинг (Факт)', line=dict(color='#636EFA', width=3, dash='dash')))
    
    fig.update_layout(
        hovermode="x unified",
        height=500,
        margin=dict(l=0, r=0, t=80, b=0), # Увеличили верхний отступ для легенды
        legend=dict(
            orientation="h", 
            yanchor="bottom", 
            y=1.02, 
            xanchor="center", 
            x=0.5
        )
    )
    st.plotly_chart(fig, use_container_width=True)
    
    # График разницы (Delta)
    st.subheader("Перекос: GameR − SpeedR (Δ)")
    st.markdown("Если столбик **выше нуля** — ты думал дольше обычного (точность выросла, но риск цейтнота). Если **ниже нуля** — ты спешил.")
    
    colors = ['#00CC96' if val > 0 else '#EF553B' for val in df['Delta']]
    
    fig2 = go.Figure()
    fig2.add_trace(go.Bar(
        x=df['Дата'], 
        y=df['Delta'],
        marker_color=colors,
        name='Δ (GameR - SpeedR)'
    ))
    
    fig2.update_layout(
        height=300,
        margin=dict(l=0, r=0, t=30, b=0),
        yaxis_title="Разница (пунктов)",
    )
    st.plotly_chart(fig2, use_container_width=True)
    
    # Таблица с деталями
    st.subheader("Детали по дням")
    cols_to_show = ["Дата", "Игр", "Rating", "GameR", "SpeedR", "CombR", "Perf", "Delta", "AvgT", "ACPL"]
    cols_exist = [c for c in cols_to_show if c in df.columns]
    st.dataframe(df[cols_exist], use_container_width=True)