# ============================================================
# web_dashboard/pages/16_Monitoring.py
# ============================================================
import sys
import os
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import sqlite3

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

from utils.db import query_df, DB_PATH

st.set_page_config(page_title="Мониторинг", page_icon="📊", layout="wide")

# Сбрасываем кэш Streamlit при каждом открытии страницы, чтобы видеть свежие данные!
st.cache_data.clear()

st.title("📊 Мониторинг динамики (Снапшоты)")
st.markdown("Здесь сохраняется история твоих метрик. Каждый запуск `15_daily_monitor.py` создает новую точку на графике.")

# Проверка существования таблицы
table_exists = False
if os.path.exists(DB_PATH):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='monitoring_log'")
    if cur.fetchone():
        table_exists = True
    conn.close()

if not table_exists:
    st.warning("⚠️ Таблица `monitoring_log` не найдена в базе данных.")
    st.info("💡 **Как исправить:** Запусти в терминале `python run.py --steps 3,15`, чтобы создать таблицу и сделать первый снапшот.")
    st.stop()

# Загружаем данные
df = query_df("SELECT * FROM monitoring_log ORDER BY date ASC")

if df.empty:
    st.info("Таблица создана, но пока пуста. Запусти `python run.py --steps 15`, чтобы сделать первый снапшот.")
else:
    # Превращаем дату в строку, чтобы Plotly не рисовал наносекунды
    df['date_str'] = df['date'].astype(str)
    
    # Если снапшотов меньше 2, предупреждаем
    if len(df) < 2:
        st.info("📈 Пока сделан только 1 снапшот. Графики линий начнут рисоваться, когда накопится хотя бы 2 дня.")
    
    # --- БЛОК 1: РЕЙТИНГИ ---
    st.subheader("📈 CombR, GameR, SpeedR")
    
    fig1 = go.Figure()
    fig1.add_trace(go.Scatter(x=df['date_str'], y=df['combined_r'], mode='lines+markers', name='CombR (Общий)', line=dict(color='#AB63FA', width=3)))
    fig1.add_trace(go.Scatter(x=df['date_str'], y=df['game_r'], mode='lines+markers', name='GameR (Точность)', line=dict(color='#00CC96', width=2)))
    fig1.add_trace(go.Scatter(x=df['date_str'], y=df['speed_r'], mode='lines+markers', name='SpeedR (Скорость)', line=dict(color='#EF553B', width=2)))
    fig1.update_layout(xaxis_type='category', title="Динамика рейтингов", margin=dict(l=0, r=0, t=30, b=0), hovermode="x unified")
    st.plotly_chart(fig1, use_container_width=True)

    # --- БЛОК 2: DELTA ---
    st.subheader("Δ (Delta): перекос в скорость или точность")
    st.caption("Идеал: от -30 до +30. Если столбик красный и высокий — ты медлишь (риск цейтнота). Если падает вниз — суетишься.")
    
    df['delta_color'] = df['delta'].apply(lambda x: '#EF553B' if abs(x) > 30 else '#00CC96')
    
    fig2 = go.Figure(data=[
        go.Bar(
            x=df['date_str'], 
            y=df['delta'],
            marker_color=df['delta_color'],
            text=df['delta'],
            textposition='auto'
        )
    ])
    fig2.add_hline(y=30, line_dash="dash", line_color="orange", annotation_text="Граница цейтнота (+30)")
    fig2.add_hline(y=-30, line_dash="dash", line_color="orange", annotation_text="Граница суеты (-30)")
    fig2.update_layout(xaxis_type='category', title="Δ (GameR - SpeedR)", margin=dict(l=0, r=0, t=30, b=0))
    st.plotly_chart(fig2, use_container_width=True)

    # --- БЛОК 3: STDDEV И АГРЕССИЯ ---
    st.subheader("🎯 Стабильность (StdDev) и Агрессия (Охотник/Защитник)")
    
    col1, col2 = st.columns(2)
    with col1:
        fig3 = px.line(df, x='date_str', y='stddev_acpl', markers=True,
                       title="Разброс ACPL (StdDev)",
                       labels={'stddev_acpl': 'StdDev', 'date_str': 'Дата'})
        fig3.add_hline(y=15, line_dash="dash", line_color="red", annotation_text="Цель: 15")
        fig3.update_layout(xaxis_type='category')
        st.plotly_chart(fig3, use_container_width=True)
        
    with col2:
        fig4 = go.Figure()
        fig4.add_trace(go.Bar(x=df['date_str'], y=df['aggression'], name='Агрессия (Hunter Score)', marker_color='#636EFA'))
        fig4.add_trace(go.Scatter(x=df['date_str'], y=df['hunter_pct'], name='Охотник %', mode='lines+markers', line=dict(color='#FFA15A', width=3), yaxis='y2'))
        
        fig4.add_hline(y=8.0, line_dash="dash", line_color="green", annotation_text="Порог Охотника (8.0)")
        fig4.update_layout(
            xaxis_type='category', 
            title="Агрессия и % партий Охотника",
            yaxis=dict(title="Hunter Score"),
            yaxis2=dict(title="% Охотника", overlaying='y', side='right', range=[0, 100]),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig4, use_container_width=True)

    # --- БЛОК 4: ТАБЛИЦА ---
    st.subheader("📋 История снапшотов")
    df_display = df.rename(columns={
        'date': 'Дата', 'games': 'Игр', 'avg_my_rating': 'Ср.Рейт',
        'avg_opp_rating': 'Ср.Соп', 'perf_rating': 'Perf', 'acpl': 'ACPL',
        'combined_r': 'CombR', 'delta': 'Δ', 'stddev_acpl': 'StdDev',
        'aggression': 'Агрессия', 'hunter_pct': 'Охотник %', 'notes': 'Заметка'
    })
    
    df_display['Дата'] = pd.to_datetime(df_display['Дата']).dt.strftime('%Y-%m-%d')
    
    st.dataframe(df_display[['Дата', 'Игр', 'Ср.Рейт', 'Ср.Соп', 'Perf', 'ACPL', 
                             'CombR', 'Δ', 'StdDev', 'Агрессия', 'Охотник %', 'Заметка']], 
                 use_container_width=True, hide_index=True)