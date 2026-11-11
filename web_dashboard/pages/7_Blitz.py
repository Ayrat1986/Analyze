# web_dashboard/pages/7_Blitz.py
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Блиц (Blitz)", page_icon="⏱️", layout="wide")
st.title("⏱️ Блиц против Stockfish")

if "blitz_start_pos" not in st.session_state:
    st.session_state.blitz_start_pos = ""

with st.sidebar:
    st.header("⚙️ Параметры")
    color_choice = st.radio("Твой цвет", ["Белые", "Чёрные"])
    level = st.slider("Уровень Stockfish (1-10)", 1, 10, 3)
    time_minutes = st.selectbox("Время (минут)", [1, 3, 5, 10], index=1)
    board_size = st.slider("Размер доски (px)", 400, 800, 480, 20)

    st.divider()

    if st.button("🔄 Новая партия", type="primary", use_container_width=True):
        st.session_state.blitz_start_pos = ""
        st.rerun()

    st.subheader("🧩 Начать с позиции")
    fen_input = st.text_input(
        "Вставь FEN или PGN (или оставь пустым)",
        value=st.session_state.blitz_start_pos,
    )
    if fen_input != st.session_state.blitz_start_pos:
        st.session_state.blitz_start_pos = fen_input
        st.rerun()

color_str = "w" if color_choice == "Белые" else "b"
time_seconds = time_minutes * 60
safe_start_pos = (
    st.session_state.blitz_start_pos
    .replace('"', '\\"')
    .replace("'", "\\'")
)

html_code = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <link rel="stylesheet" href="https://unpkg.com/@chrisoakman/chessboardjs@1.0.0/dist/chessboard-1.0.0.min.css">
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <script src="https://unpkg.com/@chrisoakman/chessboardjs@1.0.0/dist/chessboard-1.0.0.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/chess.js/0.10.3/chess.min.js"></script>
    <style>
        body {{ font-family: sans-serif; text-align: center; background: #f0f2f6; margin-top: 10px; }}
        #board {{ width: {board_size}px; height: {board_size}px; margin: 20px auto; }}
        #status {{ font-size: 20px; font-weight: bold; margin: 10px; color: #333; }}
        #timer {{ font-size: 24px; margin: 10px; display: flex; justify-content: center; gap: 20px; }}
        .clock {{ padding: 5px 15px; background: #fff; border: 2px solid #333; border-radius: 5px; min-width: 120px; }}
        .active {{ background: #ffeb3b; border-color: #ff9800; font-weight: bold; }}
        .controls {{ margin: 15px auto; display: flex; justify-content: center; gap: 10px; }}
        button {{ padding: 8px 15px; font-size: 16px; cursor: pointer; border-radius: 5px; border: 1px solid #ccc; background: #fff; }}
        button:hover {{ background: #eee; }}
        .panel {{ display: flex; justify-content: center; gap: 20px; margin-top: 15px; width: 90%; margin-left: 5%; }}
        #move-list {{ width: 300px; height: 150px; overflow-y: scroll; text-align: left; border: 1px solid #ccc; padding: 10px; background: #fff; font-family: monospace; }}
        #pgn-output {{ width: 400px; height: 150px; resize: none; border: 1px solid #ccc; padding: 10px; background: #fff; font-family: monospace; }}
        .stats {{ font-size: 18px; font-weight: bold; color: #4a4a4a; background: #fff; display: inline-block; padding: 10px 20px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
        .history-container {{ margin-top: 15px; padding: 10px; background: #fff; border-radius: 5px; width: 300px; margin-left: auto; margin-right: auto; }}
        #history-select {{ width: 100%; padding: 5px; font-size: 14px; border-radius: 5px; }}
    </style>
</head>
<body>
    <div class="stats" id="score-board">Счет: 0 - 0 - 0</div>
    <div class="history-container">
        <label><b>История партий:</b></label>
        <select id="history-select" onchange="loadPastGame()">
            <option value="">-- Выберите партию --</option>
        </select>
    </div>
    <div id="status" style="margin-top: 15px;">Загрузка...</div>
    <div id="timer">
        <div class="clock" id="my-clock">Мой: {time_minutes:02d}:00</div>
        <div class="clock" id="opp-clock">Бот: {time_minutes:02d}:00</div>
    </div>
    <div id="board"></div>
    <div class="controls">
        <button onclick="flipBoard()">🔄 Повернуть</button>
        <button onclick="undoMove()">⬅️ Назад</button>
        <button onclick="redoMove()">➡️ Вперед</button>
    </div>
    <div class="panel">
        <div id="move-list"><b>Ходы:</b><br></div>
        <textarea id="pgn-output" readonly placeholder="Здесь появится PGN партии..."></textarea>
    </div>
    <script>
        $(document).ready(function() {{
            var board = null;
            var game = new Chess();
            var $status = $('#status');
            var myColor = '{color_str}';
            var botLevel = {level};
            var gameOver = false;
            var stockfish = null;
            var redoStack = [];
            var isReviewing = false;
            var myTime = {time_seconds};
            var oppTime = {time_seconds};
            var timerInterval = null;

            // --- СТАТИСТИКА (через window.localStorage, безопасно в iframe) ---
            function safeGet(key, def) {{
                try {{ return localStorage.getItem(key) || def; }}
                catch(e) {{ return def; }}
            }}
            function safeSet(key, val) {{
                try {{ localStorage.setItem(key, val); }}
                catch(e) {{}}
            }}

            var wins = parseInt(safeGet('blitz_wins', '0'));
            var losses = parseInt(safeGet('blitz_losses', '0'));
            var draws = parseInt(safeGet('blitz_draws', '0'));
            var history = [];
            try {{ history = JSON.parse(safeGet('blitz_history', '[]')); }}
            catch(e) {{ history = []; }}

            function updateUI() {{
                $('#score-board').text('Счет: ' + wins + ' - ' + losses + ' - ' + draws);
                var $select = $('#history-select');
                $select.empty().append('<option value="">-- Выберите партию --</option>');
                history.forEach(function(item, index) {{
                    $select.append('<option value="' + index + '">Партия ' + (index + 1) + ' (' + item.result + ')</option>');
                }});
            }}

            window.loadPastGame = function() {{
                var index = $('#history-select').val();
                if (index !== "") {{
                    $('#pgn-output').val(history[index].pgn);
                    $('#move-list').html('<b>Ходы:</b><br>Партия загружена в поле PGN справа.');
                }}
            }};

            var rawInput = "{safe_start_pos}".trim();
            if (rawInput !== "") {{
                try {{
                    if (rawInput.includes('/')) {{
                        game.load(rawInput);
                    }} else {{
                        game.load_pgn(rawInput);
                    }}
                }} catch(e) {{
                    game.reset();
                }}
            }}

            function formatTime(sec) {{
                var m = Math.floor(sec / 60);
                var s = sec % 60;
                return (m < 10 ? '0' : '') + m + ':' + (s < 10 ? '0' : '') + s;
            }}

            function updateClocks() {{
                $('#my-clock').text('Мой: ' + formatTime(myTime));
                $('#opp-clock').text('Бот: ' + formatTime(oppTime));
                if (gameOver) return;
                if (game.turn() === myColor) {{
                    $('#my-clock').addClass('active');
                    $('#opp-clock').removeClass('active');
                }} else {{
                    $('#my-clock').removeClass('active');
                    $('#opp-clock').addClass('active');
                }}
            }}

            function startTimer() {{
                if (timerInterval) clearInterval(timerInterval);
                timerInterval = setInterval(function() {{
                    if (gameOver || game.game_over() || isReviewing) return;
                    if (game.turn() === myColor) {{
                        myTime--;
                        if (myTime <= 0) {{ myTime = 0; endGame('Время вышло! Вы проиграли.', 'loss'); }}
                    }} else {{
                        oppTime--;
                        if (oppTime <= 0) {{ oppTime = 0; endGame('У соперника упал флаг! Вы выиграли!', 'win'); }}
                    }}
                    updateClocks();
                }}, 1000);
            }}

            function endGame(msg, resultType) {{
                if (gameOver) return;
                gameOver = true;
                clearInterval(timerInterval);
                $status.text(msg);
                updatePGN();
                if (resultType === 'win') wins++;
                else if (resultType === 'loss') losses++;
                else if (resultType === 'draw') draws++;
                history.push({{ pgn: game.pgn(), result: msg }});
                safeSet('blitz_wins', wins);
                safeSet('blitz_losses', losses);
                safeSet('blitz_draws', draws);
                safeSet('blitz_history', JSON.stringify(history));
                updateUI();
            }}

            const stockfishUrl = 'https://cdnjs.cloudflare.com/ajax/libs/stockfish.js/10.0.2/stockfish.js';
            fetch(stockfishUrl)
                .then(response => response.blob())
                .then(blob => {{
                    const blobUrl = URL.createObjectURL(blob);
                    stockfish = new Worker(blobUrl);
                    stockfish.onmessage = function(event) {{
                        var move = event.data;
                        if (typeof move === 'string' && move.indexOf('bestmove') === 0) {{
                            var bestMove = move.split(' ')[1];
                            if (bestMove && bestMove !== '(none)') {{
                                game.move({{ from: bestMove.substring(0,2), to: bestMove.substring(2,4), promotion: 'q' }});
                                board.position(game.fen());
                                updateStatus();
                            }}
                        }}
                    }};
                    stockfish.postMessage('uci');
                    stockfish.postMessage('setoption name Skill Level value ' + botLevel);
                    updateStatus();
                }})
                .catch(err => {{
                    $status.text('⚠️ Ошибка загрузки движка. Играйте вручную.');
                }});

            function makeBotMove() {{
                if (game.game_over() || game.turn() === myColor || gameOver || isReviewing) return;
                $status.text('Stockfish думает...');
                setTimeout(function() {{
                    if (stockfish) {{
                        stockfish.postMessage('position fen ' + game.fen());
                        stockfish.postMessage('go depth 10');
                    }}
                }}, 300);
            }}

            function updateStatus() {{
                if (game.game_over()) {{
                    var resultMsg = 'Игра окончена! Результат: ';
                    var resType = 'draw';
                    if (game.in_checkmate()) {{
                        var winner = game.turn() === 'w' ? 'Чёрные' : 'Белые';
                        resultMsg += 'Мат (' + winner + ')';
                        resType = (winner === 'Белые' && myColor === 'w') || (winner === 'Чёрные' && myColor === 'b') ? 'win' : 'loss';
                    }} else if (game.in_draw() || game.in_stalemate() || game.in_threefold_repetition()) {{
                        resultMsg += 'Ничья';
                        resType = 'draw';
                    }}
                    endGame(resultMsg, resType);
                    return;
                }}
                if (gameOver) return;
                var turnText = game.turn() === 'w' ? 'Белые' : 'Чёрные';
                $status.text('Ход: ' + turnText);
                updateClocks();
                startTimer();
                updatePGN();
                if (game.turn() !== myColor && !isReviewing) {{
                    makeBotMove();
                }}
            }}

            function updatePGN() {{
                var historyMoves = game.history({{ verbose: true }});
                var html = "<b>Ходы:</b><br>";
                for (var i = 0; i < historyMoves.length; i += 2) {{
                    var moveNum = i / 2 + 1;
                    html += moveNum + ". " + historyMoves[i].san + " ";
                    if (i + 1 < historyMoves.length) {{
                        html += historyMoves[i+1].san + " ";
                    }}
                }}
                $("#move-list").html(html);
                $("#pgn-output").val(game.pgn());
            }}

            var config = {{
                draggable: true,
                position: game.fen(),
                orientation: myColor === 'w' ? 'white' : 'black',
                onDragStart: onDragStart,
                onDrop: onDrop,
                pieceTheme: 'https://chessboardjs.com/img/chesspieces/wikipedia/{{piece}}.png'
            }};
            board = Chessboard('board', config);

            function onDragStart(source, piece, position, orientation) {{
                if (game.game_over() || gameOver || isReviewing) return false;
                if ((game.turn() === 'w' && piece.search(/^b/) !== -1) ||
                    (game.turn() === 'b' && piece.search(/^w/) !== -1)) return false;
                if (game.turn() !== myColor) return false;
            }}

            function onDrop(source, target) {{
                redoStack = [];
                var move = game.move({{ from: source, to: target, promotion: 'q' }});
                if (move === null) return 'snapback';
                updateStatus();
            }}

            window.flipBoard = function() {{ board.flip(); }};

            window.undoMove = function() {{
                if (game.history().length === 0) return;
                isReviewing = true;
                var move = game.undo();
                redoStack.push(move);
                board.position(game.fen());
                updateStatus();
                isReviewing = false;
            }};

            window.redoMove = function() {{
                if (redoStack.length === 0) return;
                isReviewing = true;
                var move = redoStack.pop();
                game.move(move);
                board.position(game.fen());
                updateStatus();
                isReviewing = false;
            }};

            updateUI();
            updateClocks();
            startTimer();
        }});
    </script>
</body>
</html>
"""

components.html(html_code, height=950)