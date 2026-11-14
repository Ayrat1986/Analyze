# ============================================================
# web_dashboard/pages/2_Openings.py (v25.2)
# NEW: Добавлен ползунок размера доски и drag-and-drop 
#      (взято из 6_Analysis.py и 11_Trainer.py).
# ============================================================
import streamlit as st
import plotly.express as px
import pandas as pd
import json, os, chess, io
import chess.pgn
import re
import streamlit.components.v1 as components
import _common
from utils.db import query_df, cutoff_ts

st.set_page_config(page_title="Дебюты (Openings)", page_icon="♟️", layout="wide")
st.title("♟️ Дебюты (Openings)")

PLAYER = _common.CONFIG.get("player", "unknown").lower()

with st.sidebar:
    days = st.slider("Период (дней)", 7, 365, 90, 1)
    board_size = st.slider("Размер доски (px)", 400, 1000, 480, 50) # Добавлен ползунок

ts = cutoff_ts(days)

# ============================================================
# 1. ПОЛУЧАЕМ ДАННЫЕ ИЗ БД
# ============================================================
df = query_df("""
    SELECT opening, eco, CASE WHEN LOWER(white) = LOWER(?) THEN 'Белые' ELSE 'Чёрные' END AS color,
           MAX(opening_line) AS opening_line, COUNT(*) AS games, SUM(won) AS wins, AVG(acpl) AS acpl
    FROM games WHERE end_time >= ? AND is_lag=0 AND is_cheater=0 AND opening IS NOT NULL AND opening != ''
    GROUP BY opening, eco, color ORDER BY games DESC
""", (PLAYER, ts))

if df.empty:
    st.warning("Нет данных за выбранный период.")
    st.stop()

df["win_rate"] = (df["wins"] / df["games"] * 100).round(1)
df["acpl"] = df["acpl"].round(0)
df_reliable = df[df["games"] >= 5]

# ============================================================
# 2. ГРАФИКИ ТОП-10 (Белые / Чёрные)
# ============================================================
def draw_top_10(data, title_prefix):
    if data.empty:
        st.info("Мало данных (нужно минимум 5 партий на дебют).")
        return
    c1, c2 = st.columns(2)
    with c1:
        st.subheader(f"✅ Топ-10 лучших ({title_prefix})")
        best = data.sort_values("win_rate", ascending=False).head(10)
        fig = px.bar(best, x="win_rate", y="opening", orientation="h", text="win_rate",
                     hover_data=["games", "opening_line"], color_discrete_sequence=["#28a745"])
        fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=400, xaxis_title="Винрейт %")
        fig.update_xaxes(range=[0, 100])
        fig.update_traces(texttemplate='%{text}%<br>(%{customdata[0]} игр)', customdata=best[["games"]])
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.subheader(f"❌ Топ-10 худших ({title_prefix})")
        worst = data.sort_values("win_rate", ascending=True).head(10)
        fig2 = px.bar(worst, x="win_rate", y="opening", orientation="h", text="win_rate",
                      hover_data=["games", "opening_line"], color_discrete_sequence=["#dc3545"])
        fig2.update_layout(yaxis={"categoryorder": "total descending"}, height=400, xaxis_title="Винрейт %")
        fig2.update_xaxes(range=[0, 100])
        fig2.update_traces(texttemplate='%{text}%<br>(%{customdata[0]} игр)', customdata=worst[["games"]])
        st.plotly_chart(fig2, use_container_width=True)

tab_w, tab_b = st.tabs(["♔ За белых", "♚ За чёрных"])
with tab_w:
    draw_top_10(df_reliable[df_reliable["color"] == "Белые"], "Белые")
with tab_b:
    draw_top_10(df_reliable[df_reliable["color"] == "Чёрные"], "Чёрные")

st.divider()

# ============================================================
# 3. JS-ДВИЖОК ДЛЯ ИНТЕРАКТИВНОЙ ДОСКИ (с drag-and-drop)
# ============================================================
def render_interactive_board(pgn_str, size=480):
    game = chess.pgn.read_game(io.StringIO(pgn_str))
    moves_uci = [m.move.uci() for m in game.mainline()] if game else []
    
    moves_json = json.dumps(moves_uci)
    start_fen_json = json.dumps(chess.STARTING_FEN)
    
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
            #board-wrapper {{ position: relative; width: {size}px; height: {size}px; }}
            #svg-overlay {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: 10; }}
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
            <div id="board-wrapper">
                <div id="board"></div>
                <svg id="svg-overlay" viewBox="0 0 {size} {size}"></svg>
            </div>
            <div class="panel">
                <div class="engine-panel" id="engine-info">
                    <div style="color: #666; text-align: center;">Ожидание...</div>
                </div>
                <div class="moves" id="move-list"></div>
                <div class="controls">
                    <button onclick="flipBoard()">↕️ Перевернуть</button>
                    <button onclick="jumpToMove(0)">⏮</button>
                    <button onclick="stepMove(-1)">⬅️</button>
                    <button onclick="stepMove(1)">➡️</button>
                    <button onclick="jumpToMove(positions.length-1)">⏭</button>
                </div>
            </div>
        </div>

        <script>
            var startFen = {start_fen_json};
            var movesUci = {moves_json};
            var game = new Chess(startFen);
            var positions = [startFen];
            var historySan = [];
            var currentIdx = 0;
            var stockfish = null;
            var board = null;
            var currentOrientation = 'white';
            var engineLines = {{}};

            $(document).ready(function() {{
                board = Chessboard('board', {{
                    draggable: true,
                    position: startFen,
                    orientation: currentOrientation,
                    pieceTheme: 'https://lichess1.org/assets/piece/cburnett/{{piece}}.svg',
                    onDragStart: function(source, piece, position, orientation) {{
                        if (game.game_over()) return false;
                        if ((game.turn() === 'w' && piece.search(/^b/) !== -1) || (game.turn() === 'b' && piece.search(/^w/) !== -1)) {{
                            return false;
                        }}
                    }},
                    onDrop: function(source, target) {{
                        var move = game.move({{ from: source, to: target, promotion: 'q' }});
                        if (move === null) return 'snapback';
                        
                        positions = positions.slice(0, currentIdx + 1);
                        historySan = historySan.slice(0, currentIdx);
                        positions.push(game.fen());
                        historySan.push(move.san);
                        currentIdx++;
                        
                        renderMoves();
                        $('.move-san').removeClass('active');
                        if (currentIdx > 0) $('#move-' + (currentIdx - 1)).addClass('active');
                        analyzeCurrent();
                    }},
                    onSnapEnd: function() {{
                        board.position(game.fen());
                    }}
                }});

                for (var i = 0; i < movesUci.length; i++) {{
                    var m = game.move(movesUci[i], {{sloppy: true}});
                    if (m) {{
                        positions.push(game.fen());
                        historySan.push(m.san);
                    }}
                }}
                game.load(startFen);

                function renderMoves() {{
                    var html = "";
                    for (var i = 0; i < historySan.length; i += 2) {{
                        var num = i / 2 + 1;
                        var wSan = historySan[i];
                        var bSan = (i + 1 < historySan.length) ? historySan[i+1] : "";
                        html += `<div>${{num}}. <span class="move-san" id="move-${{i}}" onclick="jumpToMove(${{i+1}})">${{wSan}}</span>`;
                        if (bSan) html += ` <span class="move-san" id="move-${{i+1}}" onclick="jumpToMove(${{i+2}})">${{bSan}}</span>`;
                        html += `</div>`;
                    }}
                    document.getElementById('move-list').innerHTML = html;
                }}
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
                                    var evalStr = "";
                                    var side = game.turn() === 'w' ? 1 : -1;
                                    
                                    if (scoreCpMatch) {{
                                        var sc = parseInt(scoreCpMatch[1]) * side;
                                        evalStr = (sc > 0 ? "+" : "") + (sc / 100).toFixed(2);
                                    }} else if (scoreMateMatch) {{
                                        var mate = parseInt(scoreMateMatch[1]) * side;
                                        evalStr = "M" + Math.abs(mate);
                                    }}
                                    
                                    var pvMovesUci = pvMatch[1].trim().split(' ');
                                    var firstMoveUci = pvMovesUci[0];
                                    
                                    var tempGame = new Chess(game.fen());
                                    var sanMoves = [];
                                    for (var i = 0; i < Math.min(pvMovesUci.length, 4); i++) {{
                                        var m = tempGame.move(pvMovesUci[i], {{sloppy: true}});
                                        if (m) sanMoves.push(m.san);
                                    }}
                                    
                                    engineLines[pvIdx] = {{
                                        evalStr: evalStr,
                                        pvStr: sanMoves.join(' '),
                                        firstUci: firstMoveUci
                                    }};
                                    
                                    updateEngineUI();
                                }}
                            }}
                        }};
                        stockfish.postMessage('uci');
                        stockfish.postMessage('setoption name MultiPV value 2'); 
                        
                        if (positions.length > 1) jumpToMove(positions.length - 1);
                    }}).catch(e => {{
                        document.getElementById('engine-info').innerHTML = '<div style="color:red; text-align:center;">Ошибка загрузки движка</div>';
                    }});
            }});

            function updateEngineUI() {{
                var html = "";
                var bestUcis = [];
                
                for (var i = 1; i <= 2; i++) {{
                    if (engineLines[i]) {{
                        html += `<div class="engine-line">
                                    <span class="eval-score">${{engineLines[i].evalStr}}</span> 
                                    <span class="pv-moves">${{engineLines[i].pvStr}}</span>
                                 </div>`;
                        bestUcis.push({{uci: engineLines[i].firstUci, idx: i}});
                    }}
                }}
                
                if (html) {{
                    document.getElementById('engine-info').innerHTML = html;
                    drawArrows(bestUcis);
                }}
            }}

            function drawArrows(uciMoves) {{
                var svg = document.getElementById('svg-overlay');
                svg.innerHTML = ''; 
                var colors = ['rgba(50, 205, 50, 0.8)', 'rgba(30, 144, 255, 0.8)'];
                
                var defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
                colors.forEach((color, i) => {{
                    defs.innerHTML += `<marker id="arrowhead-${{i+1}}" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
                                        <polygon points="0 0, 6 3, 0 6" fill="${{color}}" />
                                      </marker>`;
                }});
                svg.appendChild(defs);

                uciMoves.forEach((item, index) => {{
                    if (!item.uci || item.uci.length < 4) return;
                    var fromSq = item.uci.substring(0, 2);
                    var toSq = item.uci.substring(2, 4);
                    
                    function getCenter(sq) {{
                        var file = sq.charCodeAt(0) - 97; 
                        var rank = parseInt(sq[1]) - 1;   
                        var sqSize = {size} / 8;
                        
                        var x, y;
                        if (currentOrientation === 'white') {{
                            x = file * sqSize + sqSize / 2;
                            y = (7 - rank) * sqSize + sqSize / 2;
                        }} else {{
                            x = (7 - file) * sqSize + sqSize / 2;
                            y = rank * sqSize + sqSize / 2;
                        }}
                        return {{x: x, y: y}};
                    }}
                    
                    var p1 = getCenter(fromSq);
                    var p2 = getCenter(toSq);
                    var colorIndex = item.idx === 1 ? 0 : 1; 
                    
                    var line = document.createElementNS("http://www.w3.org/2000/svg", "line");
                    line.setAttribute("x1", p1.x);
                    line.setAttribute("y1", p1.y);
                    line.setAttribute("x2", p2.x);
                    line.setAttribute("y2", p2.y);
                    line.setAttribute("stroke", colors[colorIndex]);
                    line.setAttribute("stroke-width", item.idx === 1 ? "12" : "8");
                    line.setAttribute("marker-end", `url(#arrowhead-${{item.idx}})`);
                    svg.appendChild(line);
                }});
            }}

            function analyzeCurrent() {{
                engineLines = {{}}; 
                document.getElementById('engine-info').innerHTML = '<div style="color: #666; text-align: center;">Анализ...</div>';
                document.getElementById('svg-overlay').innerHTML = '';
                
                if (stockfish) {{
                    stockfish.postMessage('stop');
                    stockfish.postMessage('position fen ' + positions[currentIdx]);
                    stockfish.postMessage('go depth 14');
                }}
            }}

            window.jumpToMove = function(idx) {{
                currentIdx = Math.max(0, Math.min(positions.length - 1, idx));
                game.load(positions[currentIdx]);
                board.position(positions[currentIdx], false);
                $('.move-san').removeClass('active');
                if (currentIdx > 0) $('#move-' + (currentIdx - 1)).addClass('active');
                analyzeCurrent();
            }}

            window.stepMove = function(dir) {{ jumpToMove(currentIdx + dir); }}
            
            window.flipBoard = function() {{ 
                board.flip(); 
                currentOrientation = board.orientation();
                analyzeCurrent(); 
            }}
        </script>
    </body>
    </html>
    """
    return html

# ============================================================
# 4. РАЗБОР КОНКРЕТНОЙ ЛИНИИ
# ============================================================
st.subheader("🔬 Разбор конкретной линии")

bad_openings = df_reliable[df_reliable["win_rate"] < 45].sort_values("games", ascending=False).head(10)
good_openings = df_reliable[df_reliable["win_rate"] >= 55].sort_values("games", ascending=False).head(5)

options = []
for _, row in bad_openings.iterrows():
    options.append(f"🔴 [BAD] {row['eco']} — {row['opening'][:35]} ({row['win_rate']}%, {row['games']}п)")
for _, row in good_openings.iterrows():
    options.append(f"🟢 [TOP] {row['eco']} — {row['opening'][:35]} ({row['win_rate']}%, {row['games']}п)")

option_map = {opt: row for opt, (_, row) in zip(options, pd.concat([bad_openings, good_openings]).iterrows())}

selected_opt = st.selectbox("Выбери проблемный или сильный дебют для разбора:", ["—"] + options)

if selected_opt != "—":
    row = option_map[selected_opt]
    line_uci = row["opening_line"]
    
    board = chess.Board()
    for move in line_uci.split():
        try:
            board.push_uci(move)
        except Exception:
            break
            
    game = chess.pgn.Game()
    game.add_line(board.move_stack)
    exporter = chess.pgn.StringExporter(headers=False, variations=False, comments=False)
    pgn_str = game.accept(exporter)

    c_board, c_info = st.columns([1.5, 1])
    
    with c_board:
        components.html(render_interactive_board(pgn_str, size=board_size), height=board_size + 120)
        
    with c_info:
        st.markdown(f"**Дебют:** {row['eco']} — {row['opening']}")
        st.markdown(f"**Партий:** {row['games']} | **Винрейт:** {row['win_rate']}% | **ACPL:** {row['acpl']}")
        st.code(line_uci, language="text")
        
        if st.button("🔬 Открыть в полном Анализаторе", type="primary", use_container_width=True):
            st.session_state["analyze_pgn"] = pgn_str
            st.session_state["analyze_fen"] = None
            st.switch_page("pages/6_Analysis.py")

st.divider()
st.subheader("🌳 OPENING PLANNER (Stockfish) — рекомендации")

planner_path = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "reports", "opening_planner.txt"
))

if os.path.exists(planner_path):
    with open(planner_path, "r", encoding="utf-8") as f:
        planner_text = f.read()

    ecos = re.findall(r'♟️ ([A-Z]\d{2}) \(\d+ партий', planner_text)
    ecos = sorted(list(set(ecos)))

    if ecos:
        selected_eco = st.selectbox("Выбери дебют (ECO) для глубоких рекомендаций:", ecos)
        pattern = rf'(♟️ {selected_eco} \(\d+ партий.*?)(?=♟️ [A-Z]\d{{2}} \(\d+ партий|РЕЗЮМЕ ПО ВСЕМ ДЕБЮТАМ|$)'
        match = re.search(pattern, planner_text, re.DOTALL)
        if match:
            st.code(match.group(1).strip(), language="text")
        else:
            st.info("Не удалось найти блок для этого ECO.")
    else:
        st.warning("В planner.txt нет данных по ECO.")
else:
    st.warning("opening_planner.txt не найден. Запусти 05_openings.py.")