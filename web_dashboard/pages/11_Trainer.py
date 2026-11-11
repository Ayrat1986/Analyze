# web_dashboard/pages/11_Trainer.py
import sys
import os
import pandas as pd
import chess
import time

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
from utils.db import query_df, cutoff_ts
from utils.chess_vis import render_board_html
from utils import trainer_db
from analysis.trainer.smart_deck import generate_smart_deck

st.set_page_config(page_title="Тренажёр", page_icon="🎯", layout="wide")
st.title("🎯 Тренажёр (Daily Trainer)")
st.caption("Решённые задачи уходят в архив. Не решённые — возвращаются через 3 дня.")

trainer_db.ensure_table()

REPORTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "reports"))
SMART_DECK_CSV = os.path.join(REPORTS_DIR, "training", "smart_deck.csv")

with st.sidebar:
    st.header("⚙️ Настройки")
    days = st.slider("Период (дней) для 'Худших'", 7, 365, 90, 1)
    n_tasks = st.slider("Задач из худших партий", 5, 20, 10, 1)
    
    if st.button("🔄 Обновить Умную колоду"):
        with st.spinner("Анализируем базу..."):
            generate_smart_deck()
        st.success("Колода обновлена!")
    
    st.divider()
    st.header("📊 Статистика")
    stats = trainer_db.get_stats()
    st.metric("Всего задач", stats["total"])
    st.metric("✅ Решено", stats["solved"]["n"])
    st.metric("❌ Не решено", stats["failed"]["n"])
    st.metric("⏭ Отложено", stats["skipped"]["n"])

ts = cutoff_ts(days)

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📚 Умная Колода", "🔥 Худшие зевки", "🛡️ Эндшпиль", "📊 Прогресс", "🗄️ Архив",
])

def render_task_card(task_type: str, fen: str, title: str, subtitle: str, best_move: str = None, url: str = None):
    status = trainer_db.get_status(task_type, fen)
    
    if status and status["status"] == "solved":
        return False
    
    if status and status.get("next_review") and status["next_review"] > int(time.time()):
        return False
    
    h = trainer_db.task_hash(task_type, fen)
    
    st.markdown(f"#### {title}")
    st.caption(subtitle)
    
    c1, c2 = st.columns([1, 1])
    with c1:
        try:
            st.markdown(render_board_html(fen, size=380), unsafe_allow_html=True)
        except Exception as e:
            st.error(f"Ошибка рендера доски: {e}")
    with c2:
        if best_move:
            st.info(f"💡 Лучший ход: {best_move}")
        st.code(fen, language="text")
        st.markdown(f"[🔗 Тренировать в Lichess](https://lichess.org/analysis/standard/{fen.replace(' ', '_')})")
        
        if url:
            if st.button("🔬 Открыть партию в Анализаторе", key=f"open_{h}", use_container_width=True):
                import sqlite3
                from utils.db import DB_PATH
                conn = sqlite3.connect(DB_PATH)
                cur = conn.cursor()
                cur.execute("SELECT pgn FROM games WHERE url=?", (url,))
                row = cur.fetchone()
                if row and row[0]:
                    st.session_state["analyze_pgn"] = row[0]
                    st.session_state["analyze_fen"] = None
                    st.switch_page("pages/6_Analysis.py")
                conn.close()
        
        if status:
            st.caption(f"Попыток: {status['attempts']}")
    
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("✅ Решено", key=f"solved_{h}", use_container_width=True, type="primary"):
            trainer_db.mark_solved(task_type, fen)
            st.success("Задача ушла в архив!")
            st.rerun()
    with c2:
        if st.button("❌ Не решил", key=f"failed_{h}", use_container_width=True):
            trainer_db.mark_failed(task_type, fen, retry_days=3)
            st.warning("Вернётся через 3 дня.")
            st.rerun()
    with c3:
        if st.button("⏭ Пропустить", key=f"skip_{h}", use_container_width=True):
            trainer_db.mark_skipped(task_type, fen)
            st.info("Вернётся завтра.")
            st.rerun()
    
    st.divider()
    return True

with tab1:
    st.subheader("📚 Умная Колода на сегодня")
    st.markdown("Здесь собраны твои самые опасные зевки: **свежие (7 дней) + против агрессоров + на 'Час X' (21-25 ход)**.")
    
    if not os.path.exists(SMART_DECK_CSV):
        st.warning("Колода ещё не сгенерирована. Нажми кнопку **'🔄 Обновить Умную колоду'** в левом меню.")
    else:
        df = pd.read_csv(SMART_DECK_CSV)
        if df.empty:
            st.success("🎉 Поздравляю! В этой выборке нет грубых зевков.")
        else:
            active_fens = trainer_db.get_active_fens("smart_deck")
            visible = df[~df["fen"].isin(active_fens)]
            
            if visible.empty:
                st.success("✅ Все задачи умной колоды решены! Нажми 'Обновить', чтобы найти новые.")
            else:
                st.markdown(f"**Осталось: {len(visible)} из {len(df)}**")
                for i, r in visible.iterrows():
                    best_san = None
                    if r["best_move"]:
                        try:
                            b = chess.Board(r["fen"])
                            best_san = b.san(chess.Move.from_uci(r["best_move"]))
                        except Exception:
                            best_san = r["best_move"]
                    
                    render_task_card(
                        "smart_deck", r["fen"],
                        f"{r['white'][:12]} vs {r['black'][:12]}",
                        f"Ход {r['move_num']}, потеря {r['loss_cp']} CP, паттерн {r['pattern']}",
                        best_move=best_san, url=r["url"],
                    )

with tab2:
    st.subheader(f"🔥 Топ-{n_tasks} худших зевков за период")
    worst = query_df(f"""
        SELECT b.fen_before, b.move_num, b.loss_cp, b.best_move_uci,
               b.pattern_tag, g.white, g.black, g.url, g.end_time
        FROM blunders b JOIN games g ON g.url = b.game_url
        WHERE g.is_lag=0 AND g.is_cheater=0 AND b.is_my_blunder=1
          AND b.is_berserk=0 AND b.is_instant=0
          AND b.fen_before IS NOT NULL AND b.fen_before != ''
          AND g.end_time >= ?
        ORDER BY b.loss_cp DESC LIMIT ?
    """, (ts, n_tasks))
    
    if worst.empty:
        st.info("Нет зевков за период.")
    else:
        active_fens = trainer_db.get_active_fens("worst")
        visible = worst[~worst["fen_before"].isin(active_fens)]
        
        if visible.empty:
            st.success("✅ Все худшие зевки решены! Отдыхай.")
        else:
            st.markdown(f"**Осталось: {len(visible)} из {len(worst)}**")
            for _, r in visible.iterrows():
                best_san = None
                if r["best_move_uci"]:
                    try:
                        b = chess.Board(r["fen_before"])
                        best_san = b.san(chess.Move.from_uci(r["best_move_uci"]))
                    except Exception:
                        best_san = r["best_move_uci"]
                render_task_card(
                    "worst", r["fen_before"],
                    f"{r['white'][:12]} vs {r['black'][:12]}",
                    f"Ход {r['move_num']}, потеря {r['loss_cp']} CP, паттерн {r['pattern_tag']}",
                    best_move=best_san, url=r["url"],
                )

with tab3:
    st.subheader("🛡️ Эндшпильный тренажёр")
    endgame_path = os.path.join(REPORTS_DIR, "training", "endgame_positions.csv")
    if os.path.exists(endgame_path):
        eg_df = pd.read_csv(endgame_path)
        if not eg_df.empty:
            active_fens = trainer_db.get_active_fens("endgame")
            visible = eg_df[~eg_df["fen"].isin(active_fens)]
            
            if visible.empty:
                st.success("✅ Все эндшпильные задачи решены!")
            else:
                st.markdown(f"**Осталось: {len(visible)} из {len(eg_df)}**")
                for _, r in visible.head(10).iterrows():
                    render_task_card(
                        "endgame", r["fen"],
                        f"Эндшпиль (ACPL {r['acpl_endgame']:.0f})",
                        f"Из партии: {r['url'][:60]}",
                        url=r["url"],
                    )
        else:
            st.info("Эндшпильные позиции пусты.")
    else:
        st.warning("endgame_positions.csv не найден. Запусти 07_endgame.py.")

with tab4:
    st.subheader("📊 Прогресс тренировок")
    stats = trainer_db.get_stats()
    if stats["total"] == 0:
        st.info("Ты ещё не решил ни одной задачи. Начни с колоды.")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Всего задач", stats["total"])
        c2.metric("✅ Решено", stats["solved"]["n"], f"{stats['solved']['n']/stats['total']*100:.0f}%")
        c3.metric("❌ Не решено", stats["failed"]["n"], f"{stats['failed']['n']/stats['total']*100:.0f}%")
        c4.metric("⏭ Отложено", stats["skipped"]["n"], f"{stats['skipped']['n']/stats['total']*100:.0f}%")
        
        solved_pct = stats["solved"]["n"] / stats["total"] * 100
        st.progress(min(solved_pct / 100, 1.0))
        st.caption(f"Решено {solved_pct:.0f}% всех задач")

with tab5:
    st.subheader("🗄️ Архив решённых задач")
    st.caption("Задачи, которые ты пометил '✅ Решено'.")
    archive = trainer_db.get_archive(limit=100)
    if not archive:
        st.info("Архив пуст. Реши первую задачу — она появится здесь.")
    else:
        st.markdown(f"**Всего решено: {len(archive)}**")
        for i, item in enumerate(archive[:20], 1):
            with st.expander(f"#{i}. {item['task_type']} — попыток: {item['attempts']}, дата: {pd.to_datetime(item['last_seen'], unit='s').strftime('%d.%m.%y')}"):
                st.code(item["fen"], language="text")
                if st.button("↩️ Вернуть в очередь", key=f"reset_{i}_{item['fen'][:10]}"):
                    trainer_db.reset_task(item["task_type"], item["fen"])
                    st.success("Задача возвращена в очередь.")
                    st.rerun()