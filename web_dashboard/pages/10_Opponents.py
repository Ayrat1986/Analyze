# web_dashboard/pages/10_Opponents.py
import os
import re
import streamlit as st
import pandas as pd

st.set_page_config(page_title="Соперники", page_icon="🎭", layout="wide")
st.title("🎭 Психология соперников")

REPORTS_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "reports"
))


def read_report(name: str) -> str:
    path = os.path.join(REPORTS_DIR, name)
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# ---- 1. CRUSHED BY (Таблица) ----
st.subheader("🩸 Те, кто тебя раскалывает (Score < 30%)")
crushed_text = read_report("crushed_by.txt")
if crushed_text:
    rows = []
    for line in crushed_text.split("\n"):
        # Формат: oppname  2583  11  2/0/9  18.2  83  86
        parts = line.split()
        if len(parts) == 7 and parts[0] != "Соперник" and parts[0] != "-":
            try:
                rows.append({
                    "Соперник": parts[0],
                    "Рейтинг": int(parts[1]),
                    "Партий": int(parts[2]),
                    "W/D/L": parts[3],
                    "Score %": float(parts[4]),
                    "Мой ACPL": float(parts[5]),
                    "Его ACPL": float(parts[6])
                })
            except ValueError:
                continue
    
    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.caption("Разбери 3-5 партий против каждого через вкладку «Анализ».")
    else:
        st.success("✅ Таких соперников нет!")
else:
    st.warning("crushed_by.txt не найден.")

st.divider()

# ---- 2. СТИЛЬ vs РЕЙТИНГ ----
st.subheader("⚖️ Стиль vs Рейтинг (Аллергия на агрессию)")
style_text = read_report("style_vs_rating.txt")
if style_text:
    # Просто выводим текст в спойлере, так как он уже отформатирован
    with st.expander("📊 Показать таблицу стилей", expanded=True):
        st.code(style_text, language="text")
else:
    st.warning("style_vs_rating.txt не найден.")