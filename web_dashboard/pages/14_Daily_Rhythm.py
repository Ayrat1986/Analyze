# ============================================================
# web_dashboard/pages/14_Daily_Rhythm.py
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
from analysis.dashboard_helpers import get_hourly_rhythm, get_cascade_trend

st.set_page_config(page_title="Daily Rhythm", layout="wide")
st.title("🕰️ Суточный ритм и Каскады")

@st.cache_data(ttl=3600)
def load_rhythm():
    return get_hourly_rhythm()

@st.cache_data(ttl=3600)
def load_cascades(days):
    return get_cascade_trend(days)

col1, col2 = st.columns([1, 3])
with col1:
    days = st.selectbox("Окно анализа для каскадов", [7, 30, 90], index=1)

st.subheader("Твоя форма по часам суток")
hour_data = load_rhythm()
if not hour_data:
    st.warning("Нет данных по часам.")
else:
    df_h = pd.DataFrame(hour_data)
    fig = px.scatter(df_h, x="hour", y="comb_r", size="games", color="win_rate", hover_name="hour", labels={"hour": "Час суток (МСК)", "comb_r": "Combined Rating", "win_rate": "Винрейт %", "games": "Игр"}, color_continuous_scale="RdYlGn", range_color=[40, 60], size_max=30)
    fig.add_scatter(x=df_h["hour"], y=df_h["gamr"], mode='lines+markers', name='GameR', line=dict(color='#00CC96', width=2))
    fig.add_scatter(x=df_h["hour"], y=df_h["comb_r"], mode='lines', name='CombR', line=dict(color='#AB63FA', width=3, dash='dot'))
    fig.update_layout(height=500, xaxis=dict(tickmode='linear', tick0=0, dtick=2), margin=dict(l=0, r=0, t=30, b=0), coloraxis_colorbar=dict(title="Винрейт %"))
    st.plotly_chart(fig, use_container_width=True)
    
    best_hour = df_h.loc[df_h['win_rate'].idxmax()]
    worst_hour = df_h.loc[df_h['win_rate'].idxmin()]
    col_b, col_w = st.columns(2)
    col_b.success(f"🔥 Лучшее время: **{int(best_hour['hour'])}:00**. Винрейт {best_hour['win_rate']}%.")
    col_w.error(f"❄️ Худшее время: **{int(worst_hour['hour'])}:00**. Винрейт {worst_hour['win_rate']}%.")

st.divider()

st.subheader("Динамика каскадных тильтов (2+ зевка подряд)")
cascade_data = load_cascades(days)
if not cascade_data:
    st.success("🎉 За этот период не было каскадных тильтов!")
else:
    df_c = pd.DataFrame(cascade_data)
    df_c['Дата'] = pd.to_datetime(df_c['Дата'])
    fig2 = px.bar(df_c, x="Дата", y="Каскады", labels={"Каскады": "Игр с каскадом"}, color="Каскады", color_continuous_scale="Reds")
    fig2.update_layout(height=300, margin=dict(l=0, r=0, t=30, b=0))
    st.plotly_chart(fig2, use_container_width=True)
    st.info("💡 **Совет:** Если ты видишь высокий столбик, значит, в этот день ты играл в тильте. В следующий раз, когда зевнешь, просто сделай паузу на 2 секунды.")