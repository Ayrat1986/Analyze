# ============================================================
# web_dashboard/pages/13_Blunder_Map.py
# ============================================================
import sys
import os

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

import streamlit as st
import pandas as pd
import plotly.express as px
from analysis.dashboard_helpers import get_blunder_map_data

st.set_page_config(page_title="Карта зевков", layout="wide")
st.title("⚔️ Карта зевков (Поиск 'Часа X')")

@st.cache_data(ttl=3600)
def load_blunder_map():
    return get_blunder_map_data()

data = load_blunder_map()

if not data:
    st.warning("Нет данных о зевках в диапазоне 11-30.")
else:
    df = pd.DataFrame(data)
    
    st.subheader("Частота зевков по номерам ходов")
    fig1 = px.bar(df, x="Ход", y="Зевки", color="Время (сек)", color_continuous_scale="Reds", labels={"Ход": "Номер хода", "Зевки": "Количество зевков", "Время (сек)": "Ср. время (сек)"}, text="Зевки")
    fig1.update_layout(height=400, margin=dict(l=0, r=0, t=30, b=0), coloraxis_colorbar=dict(title="Ср. время (сек)"))
    st.plotly_chart(fig1, use_container_width=True)

    st.subheader("Средняя потеря (CP) по номерам ходов")
    fig2 = px.line(df, x="Ход", y="Потеря (CP)", markers=True, labels={"Ход": "Номер хода", "Потеря (CP)": "Средняя потеря (CP)"})
    fig2.update_traces(line_color='#FF4B4B', line_width=3)
    fig2.update_layout(height=300, margin=dict(l=0, r=0, t=30, b=0))
    st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Детали по ходам")
    st.dataframe(df, use_container_width=True)
    
    st.subheader("🎯 Твой 'Час X'")
    worst_move = df.loc[df['Зевки'].idxmax()]
    st.error(f"Самый опасный ход: **{int(worst_move['Ход'])}**. На нем ты зевнул **{int(worst_move['Зевки'])}** раз. Среднее время на ход: **{worst_move['Время (сек)']} сек**.")
    if worst_move['Время (сек)'] > 1.5:
        st.info("💡 **Совет:** На этом ходу ты тратишь слишком много времени. Скорее всего, ты ищешь мат, которого нет. В следующий раз на этом ходу просто разменяй фигуры!")