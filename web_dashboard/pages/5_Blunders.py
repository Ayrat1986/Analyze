# ============================================================
# web_dashboard/pages/5_Blunders.py (v27.1)
# FIX: Убраны эмодзи из st.radio (баг исчезновения текста).
# FIX: Убран текст из шапки файла, вызывавший SyntaxError.
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
clear_pycache(SRC_DIR)
clear_pycache(os.path.dirname(os.path.abspath(__file__)))
# ---------------------------------

if BASE_DIR not in sys.path: sys.path.insert(0, BASE_DIR)
if SRC_DIR not in sys.path: sys.path.insert(0, SRC_DIR)

import streamlit as st
import pandas as pd
import numpy as np
import json
import chess
import chess.pgn
import io
import re
import streamlit.components.v1 as components
import plotly.express as px
from utils.db import query_df, cutoff_ts
from utils import trainer_db
from utils.chess_vis import render_board_html, fen_before_move, get_best_move_san

st.set_page_config(page_title="Зевки и Колода", page_icon="⚠️", layout="wide")
st.title("⚠️ Разбор зевков и Тренировка")

trainer_db.ensure_table()

# ============================================================
# БОКОВАЯ ПАНЕЛЬ (Навигация + Фильтры)
# ============================================================
with st.sidebar:
    st.header("🧭 Навигация")
    view_mode = st.radio(
        "Раздел:", 
        ["Разбор зевков", "Колода на сегодня", "Тактические угрозы", "Архив"],
        label_visibility="collapsed"
    )
    
    st.divider()
    st.header("⚙️ Фильтры")
    days = st.slider("Период (дней)", 7, 365, 90, 1)
    min_loss = st.slider("Мин. потеря (CP)", 150, 1000, 200, 50)
    phases = st.selectbox("Фаза", ["Все", "Дебют (1-10)", "Миттельшпиль (11-30)", "Эндшпиль (31+)"])
    only_critical = st.checkbox("Только 'час X' (10-15 ход)", value=False)
    only_missed_threat = st.checkbox("Только пропущенные угрозы", value=False)
    
    st.divider()
    board_size = st.slider("Размер главной доски (px)", 400, 1000, 500, 50)

ts = cutoff_ts(days)
phase_sql = ""
if phases == "Дебют (1-10)": phase_sql = " AND b.move_num <= 10"
elif phases == "Миттельшпиль (11-30)": phase_sql = " AND b.move_num > 10 AND b.move_num <= 30"
elif phases == "Эндшпиль (31+)": phase_sql = " AND b.move_num > 30"

critical_sql = " AND b.move_num BETWEEN 10 AND 15" if only_critical else ""
threat_sql = " AND b.missed_threat = 1" if only_missed_threat else ""

# ============================================================
# JS-ДВИЖОК (Интерактивная доска)
# ============================================================
def render_interactive_board(fen_str, size=500, uid="default"):
    if not isinstance(fen_str, str) or len(fen_str.split()) < 6:
        return "<div style='color:red; padding:20px;'>Ошибка: Неверный FEN</div>"

    fen_json = json.dumps(fen_str)
    turn = fen_str.split()[1] if len(fen_str.split()) > 1 else 'w'
    orientation = 'white' if turn == 'w' else 'black'
    
    id_board = f"board_{uid}"
    id_svg = f"svg_{uid}"
    id_info = f"info_{uid}"
    id_moves = f"moves_{uid}"
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <link rel="stylesheet" href="https://unpkg.com/@chrisoakman/chessboardjs@1.0.0/dist/chessboard-1.0.0.min.css">
        <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
        <script src="https://unpkg.com/@chrisoakman/chessboardjs@1.0.0/dist/chessboard-1.0.0.min.js"></script>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/chess.js/0.10.3/chess.min.js"></script>
        <style>
            body {{ font-family: sans-serif; margin: 0; padding: 0; background: transparent; }}
            .layout {{ display: flex; gap: 15px; justify-content: center; flex-wrap: wrap; }}
            .board-wrapper {{ position: relative; width: {size}px; height: {size}px; }}
            .svg-overlay {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: 10; }}
            .panel {{ width: 260px; display: flex; flex-direction: column; gap: 10px; }}
            .moves {{ height: 250px; overflow-y: auto; border: 1px solid #ddd; padding: 10px; border-radius: 5px; font-family: monospace; font-size: 13px; background: #fff; line-height: 1.5; text-align: left; }}
            .move-san {{ cursor: pointer; padding: 2px 5px; border-radius: 3px; display: inline-block; }}
            .move-san:hover {{ background: #eee; }}
            .move-san.active {{ background: #b2d8ff; font-weight: bold; }}
            .controls {{ display: flex; gap: 5px; justify-content: center; flex-wrap: wrap; }}
            button {{ padding: 6px; cursor: pointer; border: 1px solid #ccc; border-radius: 4px; background: #fff; font-size: 12px; }}
            button:hover {{ background: #eee; }}
            .engine-panel {{ background: #e3f2fd; padding: 8px; border-radius: 5px; font-family: monospace; font-size: 12px; display: flex; flex-direction: column; gap: 5px; min-height: 40px; overflow: hidden; }}
            .engine-line {{ display: flex; align-items: flex-start; gap: 5px; margin-bottom: 2px; text-align: left; }}
            .eval-score {{ font-weight: bold; width: 40px; background: #fff; text-align: center; border-radius: 3px; padding: 2px; flex-shrink: 0; }}
            .pv-moves {{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex-grow: 1; }}
        </style>
    </head>
    <body>
        <div class="layout">
            <div class="board-wrapper">
                <div id="{id_board}"></div>
                <svg id="{id_svg}" class="svg-overlay" viewBox="0 0 {size} {size}"></svg>
            </div>
            <div class="panel">
                <div class="engine-panel" id="{id_info}">
                    <div style="color: #666; text-align: center;">Ожидание...</div>
                </div>
                <div class="moves" id="{id_moves}"></div>
                <div class="controls">
                    <button onclick="flipBoard()">↕️</button>
                    <button onclick="undoMove()">↩️</button>
                    <button onclick="resetBoard()">🔄</button>
                </div>
            </div>
        </div>

        <script>
            var startFen = {fen_json};
            var game = new Chess(startFen);
            var positions = [startFen];
            var historySan = [];
            var currentIdx = 0;
            var stockfish = null;
            var board = null;
            var currentOrientation = '{orientation}';
            var engineLines = {{}};

            $(document).ready(function() {{
                board = Chessboard('{id_board}', {{
                    draggable: true, position: startFen, orientation: currentOrientation,
                    size: {size}, 
                    pieceTheme: 'https://lichess1.org/assets/piece/cburnett/{{piece}}.svg',
                    onDragStart: function(source, piece) {{
                        if (game.game_over() || (game.turn() === 'w' && piece.search(/^b/) !== -1) || (game.turn() === 'b' && piece.search(/^w/) !== -1)) return false;
                    }},
                    onDrop: function(source, target) {{
                        var move = game.move({{ from: source, to: target, promotion: 'q' }});
                        if (move === null) return 'snapback';
                        positions = positions.slice(0, currentIdx + 1); historySan = historySan.slice(0, currentIdx);
                        positions.push(game.fen()); historySan.push(move.san); currentIdx++;
                        renderMoves(); $('.move-san').removeClass('active');
                        if (currentIdx > 0) $('#move-' + (currentIdx - 1)).addClass('active');
                        analyzeCurrent();
                    }},
                    onSnapEnd: function() {{ board.position(game.fen()); }}
                }});
                renderMoves();

                fetch('https://cdnjs.cloudflare.com/ajax/libs/stockfish.js/10.0.2/stockfish.js')
                    .then(response => response.blob())
                    .then(blob => {{
                        const blobUrl = URL.createObjectURL(blob);
                        stockfish = new Worker(blobUrl);
                        stockfish.onmessage = function(event) {{
                            var msg = event.data;
                            if (typeof msg === 'string' && msg.indexOf('info depth') !== -1 && msg.indexOf('pv') !== -1) {{
                                var multipvMatch = msg.match(/multipv (\d+)/);
                                var pvMatch = msg.match(/ pv (.*)/);
                                var scoreCpMatch = msg.match(/score cp (-?\d+)/);
                                var scoreMateMatch = msg.match(/score mate (-?\d+)/);
                                var pvIdx = multipvMatch ? parseInt(multipvMatch[1]) : 1;
                                if (pvMatch && (scoreCpMatch || scoreMateMatch)) {{
                                    var evalStr = ""; var side = game.turn() === 'w' ? 1 : -1;
                                    if (scoreCpMatch) {{ var sc = parseInt(scoreCpMatch[1]) * side; evalStr = (sc > 0 ? "+" : "") + (sc / 100).toFixed(2); }}
                                    else if (scoreMateMatch) {{ var mate = parseInt(scoreMateMatch[1]) * side; evalStr = "M" + Math.abs(mate); }}
                                    var pvMovesUci = pvMatch[1].trim().split(' ');
                                    var tempGame = new Chess(game.fen()); var sanMoves = [];
                                    for (var i = 0; i < Math.min(pvMovesUci.length, 4); i++) {{
                                        var m = tempGame.move(pvMovesUci[i], {{sloppy: true}});
                                        if (m) sanMoves.push(m.san);
                                    }}
                                    engineLines[pvIdx] = {{ evalStr: evalStr, pvStr: sanMoves.join(' '), firstUci: pvMovesUci[0] }};
                                    updateEngineUI();
                                }}
                            }}
                        }};
                        stockfish.postMessage('uci');
                        stockfish.postMessage('setoption name MultiPV value 2'); 
                        analyzeCurrent();
                    }});
            }});

            function renderMoves() {{
                var html = "";
                for (var i = 0; i < historySan.length; i += 2) {{
                    var num = i / 2 + 1; var wSan = historySan[i]; var bSan = (i + 1 < historySan.length) ? historySan[i+1] : "";
                    html += `<div>${{num}}. <span class="move-san" id="move-${{i}}" onclick="jumpToMove(${{i+1}})">${{wSan}}</span>`;
                    if (bSan) html += ` <span class="move-san" id="move-${{i+1}}" onclick="jumpToMove(${{i+2}})">${{bSan}}</span>`;
                    html += `</div>`;
                }}
                document.getElementById('{id_moves}').innerHTML = html || '<i>Сделай ход...</i>';
            }}

            function updateEngineUI() {{
                var html = ""; var bestUcis = [];
                for (var i = 1; i <= 2; i++) {{
                    if (engineLines[i]) {{
                        html += `<div class="engine-line"><span class="eval-score">${{engineLines[i].evalStr}}</span> <span class="pv-moves">${{engineLines[i].pvStr}}</span></div>`;
                        bestUcis.push({{uci: engineLines[i].firstUci, idx: i}});
                    }}
                }}
                if (html) {{ document.getElementById('{id_info}').innerHTML = html; drawArrows(bestUcis); }}
            }}

            function drawArrows(uciMoves) {{
                var svg = document.getElementById('{id_svg}'); svg.innerHTML = ''; 
                var colors = ['rgba(50, 205, 50, 0.8)', 'rgba(30, 144, 255, 0.8)'];
                var defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
                colors.forEach((color, i) => {{
                    defs.innerHTML += `<marker id="arrowhead-${{i+1}}" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><polygon points="0 0, 6 3, 0 6" fill="${{color}}" /></marker>`;
                }});
                svg.appendChild(defs);
                uciMoves.forEach((item) => {{
                    if (!item.uci || item.uci.length < 4) return;
                    var fromSq = item.uci.substring(0, 2); var toSq = item.uci.substring(2, 4);
                    function getCenter(sq) {{
                        var file = sq.charCodeAt(0) - 97; var rank = parseInt(sq[1]) - 1; var sqSize = {size} / 8;
                        var x = (currentOrientation === 'white') ? (file * sqSize + sqSize / 2) : ((7 - file) * sqSize + sqSize / 2);
                        var y = (currentOrientation === 'white') ? ((7 - rank) * sqSize + sqSize / 2) : (rank * sqSize + sqSize / 2);
                        return {{x: x, y: y}};
                    }}
                    var p1 = getCenter(fromSq); var p2 = getCenter(toSq);
                    var line = document.createElementNS("http://www.w3.org/2000/svg", "line");
                    line.setAttribute("x1", p1.x); line.setAttribute("y1", p1.y); line.setAttribute("x2", p2.x); line.setAttribute("y2", p2.y);
                    line.setAttribute("stroke", colors[item.idx === 1 ? 0 : 1]); line.setAttribute("stroke-width", item.idx === 1 ? "12" : "8");
                    line.setAttribute("marker-end", `url(#arrowhead-${{item.idx}})`); svg.appendChild(line);
                }});
            }}

            function analyzeCurrent() {{
                engineLines = {{}}; document.getElementById('{id_info}').innerHTML = '<div style="color: #666; text-align: center;">Анализ...</div>';
                document.getElementById('{id_svg}').innerHTML = '';
                if (stockfish) {{ stockfish.postMessage('stop'); stockfish.postMessage('position fen ' + positions[currentIdx]); stockfish.postMessage('go depth 14'); }}
            }}

            window.jumpToMove = function(idx) {{ currentIdx = Math.max(0, Math.min(positions.length - 1, idx)); game.load(positions[currentIdx]); board.position(positions[currentIdx], false); $('.move-san').removeClass('active'); if (currentIdx > 0) $('#move-' + (currentIdx - 1)).addClass('active'); analyzeCurrent(); }}
            window.undoMove = function() {{ if (currentIdx > 0) jumpToMove(currentIdx - 1); }}
            window.resetBoard = function() {{ positions = [startFen]; historySan = []; currentIdx = 0; game.load(startFen); board.position(startFen); renderMoves(); analyzeCurrent(); }}
            window.flipBoard = function() {{ board.flip(); currentOrientation = board.orientation(); analyzeCurrent(); }}
        </script>
    </body>
    </html>
    """
    return html

# ============================================================
# УНИВЕРСАЛЬНЫЙ РЕНДЕР
# ============================================================
def render_analysis_ui(df, state_key, task_type):
    if df.empty:
        st.success("🎉 Здесь пока пусто! Все задачи решены или нет данных.")
        return

    df = df.reset_index(drop=True)

    if state_key not in st.session_state or st.session_state[state_key] not in df["id"].values:
        st.session_state[state_key] = df["id"].iloc[0]
        
    current_idx = df[df['id'] == st.session_state[state_key]].index[0]

    c_prev, c_sel, c_next = st.columns([1, 8, 1])
    with c_prev:
        if st.button("⬅️ Назад", key=f"prev_{state_key}", use_container_width=True, disabled=(current_idx == 0)):
            st.session_state[state_key] = df["id"].iloc[current_idx - 1]
            st.rerun()
    with c_next:
        if st.button("Вперед ➡️", key=f"next_{state_key}", use_container_width=True, disabled=(current_idx == len(df) - 1)):
            st.session_state[state_key] = df["id"].iloc[current_idx + 1]
            st.rerun()
            
    def format_row(row_id):
        r = df[df["id"] == row_id].iloc[0]
        label = f"{r.get('dt', '')} | {r['white'][:12]} vs {r['black'][:12]} | Ход {r['move_num']}"
        if 'loss_cp' in r and pd.notna(r['loss_cp']): label += f" | -{r['loss_cp']} CP"
        return label
        
    with c_sel:
        selected_id = st.selectbox("Выбери позицию:", df["id"].tolist(), index=current_idx, format_func=format_row, label_visibility="collapsed", key=f"sel_{state_key}")
        if selected_id != st.session_state[state_key]:
            st.session_state[state_key] = selected_id
            st.rerun()

    st.divider()

    row = df[df["id"] == st.session_state[state_key]].iloc[0]
    fen = row["fen_before"]
    if pd.isna(fen) and "pgn" in row and pd.notna(row["pgn"]):
        fen = fen_before_move(row["pgn"], int(row["move_num"]), bool(row.get("player_is_white", True)))

    if isinstance(fen, str):
        fen = fen.strip()

    c1, c2 = st.columns([1.5, 1])
    with c1:
        safe_uid = f"{state_key}_{current_idx}"
        components.html(render_interactive_board(fen, size=board_size, uid=safe_uid), height=board_size + 120)
    with c2:
        if "dt" in row: st.markdown(f"**Дата:** {row['dt']}")
        st.markdown(f"**Партия:** {row['white']} — {row['black']}")
        st.markdown(f"**Ход:** {row['move_num']} ({row.get('move_uci', '?')})")
        if "loss_cp" in row: st.markdown(f"**Потеря:** {row['loss_cp']} CP")
        if "pattern_tag" in row: st.markdown(f"**Паттерн:** {row['pattern_tag']}")
        if row.get("time_spent"): st.markdown(f"**Время на ход:** {row['time_spent']:.1f} сек")

        st.code(fen, language="text")
        if st.button("🔬 Открыть в Анализаторе", type="primary", use_container_width=True, key=f"an_{state_key}"):
            st.session_state["analyze_fen"] = fen
            st.session_state["analyze_pgn"] = None
            st.session_state["input_value"] = fen
            st.switch_page("pages/6_Analysis.py")

        st.divider()
        st.markdown("**Тренировка:**")
        
        status_info = trainer_db.get_status(task_type, fen) if fen else None
        if status_info and status_info["status"] == "solved":
            st.success("✅ Эта позиция уже в архиве (Решено).")
        else:
            c_sol, c_fail, c_skip = st.columns(3)
            with c_sol:
                if st.button("✅ Решено", key=f"sol_{state_key}", use_container_width=True, type="primary"):
                    if fen:
                        trainer_db.mark_solved(task_type, fen)
                        if current_idx < len(df) - 1: st.session_state[state_key] = df["id"].iloc[current_idx + 1]
                        st.rerun()
            with c_fail:
                if st.button("❌ Не решил", key=f"fail_{state_key}", use_container_width=True):
                    if fen:
                        trainer_db.mark_failed(task_type, fen, retry_days=3)
                        if current_idx < len(df) - 1: st.session_state[state_key] = df["id"].iloc[current_idx + 1]
                        st.rerun()
            with c_skip:
                if st.button("⏭ Пропустить", key=f"skip_{state_key}", use_container_width=True):
                    if fen:
                        trainer_db.mark_skipped(task_type, fen)
                        if current_idx < len(df) - 1: st.session_state[state_key] = df["id"].iloc[current_idx + 1]
                        st.rerun()

# ============================================================
# ЛОГИКА ОТОБРАЖЕНИЯ
# ============================================================

# --- РАЗДЕЛ 1: РАЗБОР ЗЕВКОВ ---
if view_mode == "Разбор зевков":
    st.subheader("⚠️ Разбор зевков")
    df = query_df(f"""
        SELECT b.id, b.game_url, b.move_num, b.move_uci, b.loss_cp,
               b.pattern_tag, b.time_spent, b.missed_threat,
               b.fen_before, g.white, g.black, g.pgn, date(g.end_time, 'unixepoch', '+3 hours') AS dt
        FROM blunders b JOIN games g ON g.url = b.game_url
        WHERE b.is_my_blunder = 1 AND b.is_berserk = 0 AND b.is_instant = 0
          AND g.is_lag = 0 AND g.is_cheater = 0 AND g.end_time >= ?
          AND b.loss_cp >= ? {phase_sql}{critical_sql}{threat_sql}
          AND (b.fen_before IS NULL OR b.fen_before NOT IN (SELECT fen FROM trainer_progress WHERE status = 'solved'))
        ORDER BY b.loss_cp DESC LIMIT 300
    """, (ts, min_loss))
    
    render_analysis_ui(df, "blunder_idx", "worst")
    
    st.divider()
    with st.expander("📊 Статистика: Первый зевок в партии (Водораздел)", expanded=True):
        avg_time_df = query_df("""
            SELECT AVG(b.time_spent) as avg_time
            FROM blunders b
            JOIN (SELECT game_url, MIN(move_num) as first_move FROM blunders WHERE is_my_blunder=1 GROUP BY game_url) f
              ON b.game_url = f.game_url AND b.move_num = f.first_move
        """)
        avg_first_time = avg_time_df["avg_time"].iloc[0] if not avg_time_df.empty else 0

        fb_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "reports", "first_blunder_report.txt"))
        if os.path.exists(fb_path):
            with open(fb_path, "r", encoding="utf-8") as f: text = f.read()
            avg_move_m = re.search(r"Средний ход 1-го зевка:\s+([\d.]+)", text)
            avg_move = float(avg_move_m.group(1)) if avg_move_m else 17.2
            wr_bad_m = re.search(r"Партии С зевком:\s+([\d.]+)%", text)
            wr_bad = float(wr_bad_m.group(1)) if wr_bad_m else 46.0
            wr_good_m = re.search(r"Партии БЕЗ зевков:\s+([\d.]+)%", text)
            wr_good = float(wr_good_m.group(1)) if wr_good_m else 85.0

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Средний ход 1-го зевка", f"{avg_move:.1f}")
            c2.metric("Винрейт С зевком", f"{wr_bad:.1f}%", delta="-39.5%", delta_color="inverse")
            c3.metric("Винрейт БЕЗ зевков", f"{wr_good:.1f}%", delta="+39.5%", delta_color="normal")
            c4.metric("Время на 1-й зевок", f"{avg_first_time:.1f} сек" if pd.notna(avg_first_time) else "—")

            moves_data = re.findall(r"^\s+(\d+)\s+(\d+)\s*$", text, re.MULTILINE)
            if moves_data:
                df_moves = pd.DataFrame(moves_data, columns=["Ход", "Количество"]).astype(int)
                df_moves = df_moves.sort_values("Ход").head(15)
                total_blunders = df_moves["Количество"].sum()
                df_moves["Процент"] = (df_moves["Количество"] / total_blunders) * 100
                
                fig = px.bar(df_moves, x="Ход", y="Процент", title="Где чаще всего случается первый зевок (1-15 ход)")
                fig.update_layout(height=300, margin=dict(l=0, r=0, t=30, b=0), yaxis_title="% от всех первых зевков")
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("Отчет не найден.")

# --- РАЗДЕЛ 2: КОЛОДА ---
elif view_mode == "Колода на сегодня":
    st.subheader("📚 Умная Колода на сегодня")
    st.info("Свежие и случайные зевки. Одна ошибка за раз. Решенные автоматически скрываются.")
    
    deck_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "reports", "training", "smart_deck.csv"))
    if os.path.exists(deck_path):
        df_deck = pd.read_csv(deck_path)
        if not df_deck.empty:
            df_deck = df_deck.rename(columns={"loss_cp": "loss_cp", "pattern": "pattern_tag", "fen": "fen_before"})
            df_deck["id"] = df_deck.index + 1000000
            df_deck["dt"] = "Из колоды"
            
            df_deck = df_deck.dropna(subset=['fen_before'])
            df_deck["fen_before"] = df_deck["fen_before"].astype(str).str.strip()
            
            solved_fens = trainer_db.get_active_fens("smart_deck")
            df_deck = df_deck[~df_deck['fen_before'].isin(solved_fens)]
            
            render_analysis_ui(df_deck, "deck_idx", "smart_deck")
        else:
            st.success("🎉 Колода пуста!")
    else:
        st.warning("Колода не сгенерирована.")

# --- РАЗДЕЛ 3: УГРОЗЫ ---
elif view_mode == "Тактические угрозы":
    st.subheader("🎯 Тактические угрозы (Missed Threats)")
    st.info("Зевки, после которых соперник нанёс тактический удар.")
    
    threats = query_df("""
        SELECT b.id, b.fen_before, b.move_num, b.move_uci, b.loss_cp, b.pattern_tag, 
               g.white, g.black, g.pgn, date(g.end_time, 'unixepoch', '+3 hours') AS dt,
               1 AS missed_threat
        FROM blunders b JOIN games g ON g.url = b.game_url
        WHERE b.is_my_blunder=1 AND b.missed_threat=1
          AND b.fen_before IS NOT NULL AND b.fen_before != ''
          AND (b.fen_before NOT IN (SELECT fen FROM trainer_progress WHERE status = 'solved'))
        ORDER BY b.loss_cp DESC LIMIT 50
    """)
    
    render_analysis_ui(threats, "threat_idx", "worst")

# --- РАЗДЕЛ 4: АРХИВ ---
elif view_mode == "Архив":
    st.subheader("🗄️ Архив решенных позиций")
    st.info("Здесь хранятся все зевки, которые ты отметил как 'Решено'.")
    
    archive = trainer_db.get_archive(limit=100)
    if not archive:
        st.info("Архив пуст.")
    else:
        st.markdown(f"**Всего решено: {len(archive)}**")
        for i, item in enumerate(archive[:20], 1):
            with st.expander(f"#{i}. {item['task_type']} — попыток: {item['attempts']}, дата: {pd.to_datetime(item['last_seen'], unit='s').strftime('%d.%m.%y')}"):
                st.code(item["fen"], language="text")
                board_html = render_board_html(item["fen"], size=300)
                st.markdown(board_html, unsafe_allow_html=True)