# ============================================================
# web_dashboard/pages/6_Analysis.py (v28.4)
# - Добавлена интерактивность (перетаскивание фигур).
# - Исправлена отрисовка стрелок для черных.
# ============================================================
import sys
import os
import io
import json
import chess
import chess.pgn
import streamlit as st
import streamlit.components.v1 as components

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DIR = os.path.join(BASE_DIR, "src")
if BASE_DIR not in sys.path: sys.path.insert(0, BASE_DIR)
if SRC_DIR not in sys.path: sys.path.insert(0, SRC_DIR)

st.set_page_config(page_title="Анализ позиции", page_icon="🔬", layout="wide")
st.title("🔬 Анализ позиции")

with st.sidebar:
    st.header("⚙️ Настройки")
    board_size = st.slider("Размер доски (px)", 400, 1000, 600, 50)
    show_arrows = st.checkbox("Показывать стрелки", value=True)

if "analyze_pgn" not in st.session_state: st.session_state.analyze_pgn = None
if "analyze_fen" not in st.session_state: st.session_state.analyze_fen = chess.STARTING_FEN
if "input_value" not in st.session_state: st.session_state.input_value = st.session_state.analyze_pgn or st.session_state.analyze_fen

raw_input = st.text_area("Вставь FEN или PGN партии:", value=st.session_state.input_value, height=100)

if st.button("Применить / Анализировать", type="primary"):
    if "[" in raw_input and "]" in raw_input:
        st.session_state.analyze_pgn = raw_input
        st.session_state.analyze_fen = None
        st.session_state.input_value = raw_input
    elif raw_input.count('/') >= 7:
        st.session_state.analyze_fen = raw_input.strip()
        st.session_state.analyze_pgn = None
        st.session_state.input_value = raw_input
    else:
        st.error("Не удалось распознать FEN или PGN.")
    st.rerun()

def render_custom_board(pgn_str=None, fen_str=None, size=600, draw_arrows=True):
    moves_uci = []
    w_name, b_name = "Белые", "Чёрные"
    start_fen = chess.STARTING_FEN
    orientation = "white"

    if pgn_str:
        game = chess.pgn.read_game(io.StringIO(pgn_str))
        if game:
            w_name = game.headers.get("White", "Белые")
            b_name = game.headers.get("Black", "Чёрные")
            start_fen = game.board().fen() if game.headers.get("SetUp") == "1" else chess.STARTING_FEN
            moves_uci = [m.move.uci() for m in game.mainline()]
    elif fen_str:
        start_fen = fen_str
        parts = start_fen.split()
        if len(parts) > 1 and parts[1] == 'b':
            orientation = "black"

    moves_json = json.dumps(moves_uci)
    start_fen_json = json.dumps(start_fen)
    draw_arrows_js = "true" if draw_arrows else "false"

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
            .layout {{ display: flex; gap: 20px; justify-content: center; flex-wrap: wrap; }}
            #board-wrapper {{ position: relative; width: {size}px; height: {size}px; }}
            #svg-overlay {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: 10; }}
            .panel {{ width: 320px; display: flex; flex-direction: column; gap: 10px; }}
            .player {{ font-weight: bold; background: #f8f9fa; padding: 10px; border-radius: 5px; border: 1px solid #ddd; }}
            .moves {{ height: 200px; overflow-y: auto; border: 1px solid #ddd; padding: 10px; border-radius: 5px; font-family: monospace; font-size: 14px; background: #fff; line-height: 1.5; text-align: left; }}
            .move-san {{ cursor: pointer; padding: 2px 5px; border-radius: 3px; display: inline-block; }}
            .move-san:hover {{ background: #eee; }}
            .move-san.active {{ background: #b2d8ff; font-weight: bold; }}
            .controls {{ display: flex; gap: 5px; justify-content: center; flex-wrap: wrap; }}
            button {{ padding: 8px; cursor: pointer; border: 1px solid #ccc; border-radius: 4px; background: #fff; }}
            button:hover {{ background: #eee; }}
            .engine-panel {{ background: #e3f2fd; padding: 10px; border-radius: 5px; font-family: monospace; font-size: 13px; display: flex; flex-direction: column; gap: 5px; min-height: 50px; overflow: hidden; }}
            .engine-line {{ display: flex; align-items: flex-start; gap: 8px; margin-bottom: 2px; text-align: left; }}
            .eval-score {{ font-weight: bold; width: 45px; background: #fff; text-align: center; border-radius: 3px; padding: 2px; flex-shrink: 0; }}
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
                <div class="player">{b_name}</div>
                <div class="engine-panel" id="engine-info">
                    <div style="color: #666; text-align: center;">Ожидание движка...</div>
                </div>
                <div class="moves" id="move-list"></div>
                <div class="player">{w_name}</div>
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
            var drawArrowsConfig = {draw_arrows_js};
            var currentOrientation = '{orientation}';
            var engineLines = {{}};

            $(document).ready(function() {{
                board = Chessboard('board', {{
                    draggable: true, // ФИГУРЫ МОЖНО ДВИГАТЬ
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
                        
                        // Создаем новую ветку
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
                                    for (var i = 0; i < Math.min(pvMovesUci.length, 5); i++) {{
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
                        else analyzeCurrent();
                    }}).catch(e => {{
                        document.getElementById('engine-info').innerHTML = '<div style="color:red; text-align:center;">Ошибка загрузки движка</div>';
                        console.error(e);
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
                    if (drawArrowsConfig && bestUcis.length > 0) drawArrows(bestUcis);
                }}
            }}

            function drawArrows(uciMoves) {{
                var svg = document.getElementById('svg-overlay');
                svg.innerHTML = ''; 
                var colors = ['rgba(50, 205, 50, 0.7)', 'rgba(30, 144, 255, 0.7)'];
                
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
                    
                    // Вычисляем координаты относительно текущей ориентации доски
                    function getCenter(sq) {{
                        var file = sq.charCodeAt(0) - 97; 
                        var rank = parseInt(sq[1]) - 1;   
                        if (currentOrientation === 'black') {{
                            file = 7 - file;
                            rank = 7 - rank;
                        }}
                        var sqSize = {size} / 8; 
                        return {{
                            x: (file * sqSize) + (sqSize / 2),
                            y: ((7 - rank) * sqSize) + (sqSize / 2)
                        }};
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

if st.session_state.analyze_pgn:
    components.html(render_custom_board(pgn_str=st.session_state.analyze_pgn, size=board_size, draw_arrows=show_arrows), height=board_size + 150)
elif st.session_state.analyze_fen:
    components.html(render_custom_board(fen_str=st.session_state.analyze_fen, size=board_size, draw_arrows=show_arrows), height=board_size + 150)