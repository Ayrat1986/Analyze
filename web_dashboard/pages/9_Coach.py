# web_dashboard/pages/9_Coach.py
import os
import re
import streamlit as st

st.set_page_config(page_title="Тренер", page_icon="🎓", layout="wide")
st.title("🎓 Тренер: План и Кодекс")

REPORTS_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "reports"
))


def read_report(name: str) -> str:
    path = os.path.join(REPORTS_DIR, name)
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# ---- 1. ПЛАН НА НЕДЕЛЮ ----
st.subheader("📅 План на неделю")
plan_text = read_report("coach_plan_weekly.txt")
if plan_text:
    # Вытаскиваем «ЦЕЛИ НА НЕДЕЛЮ»
    goals = re.search(r'🎯 ЦЕЛИ НА НЕДЕЛЮ:(.*?)(?:ГЛАВНОЕ|$)', plan_text, re.DOTALL)
    if goals:
        st.success(goals.group(1).strip())
    
    with st.expander("📋 Полный план (Д1–Д7)", expanded=False):
        st.code(plan_text, language="text")
else:
    st.warning("coach_plan_weekly.txt не найден. Запусти 12_coach.py.")

st.divider()

# ---- 2. КОДЕКС ПУЛИ ----
st.subheader("🧠 Кодекс Пули (правила)")
codex_text = read_report("codex_advice.txt")
if codex_text:
    # Достаем "ПРАВИЛО ДНЯ"
    day_rule = re.search(r'ПРАВИЛО ДНЯ:(.*?)(?:🧠 \[Блок|$)', codex_text, re.DOTALL)
    if day_rule:
        st.info(f"💡 **Правило дня:**\n{day_rule.group(1).strip()}")
    
    with st.expander("📖 Показать все 5 правил Кодекса", expanded=False):
        st.code(codex_text, language="text")
else:
    st.warning("codex_advice.txt не найден.")

st.divider()

# ---- 3. ДЕКОДЕР (Колода на сегодня уже в 5_Blunders, поэтому здесь только ссылка) ----
st.subheader("🎯 Ежедневная колода (20 FEN)")
st.markdown("Тренажер для разбора зевков находится на вкладке **⚠️ Зевки** → **Колода на сегодня**.")
if st.button("Перейти к Колоде"):
    st.switch_page("pages/5_Blunders.py")