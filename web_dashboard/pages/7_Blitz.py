# web_dashboard/pages/7_Blitz.py
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Блиц (Blitz)", page_icon="⏱️", layout="wide")
st.title("⏱️ Блиц против Stockfish")

with st.sidebar:
    st.header("⚙️ Параметры")
    color_choice = st.radio("Твой цвет", ["Белые", "Чёрные"])
    level = st.slider("Уровень Stockfish (1-10)", 1, 10, 3)
    time_minutes = st.selectbox("Время (минут)", [1, 3, 5, 10], index=1)
    board_size = st.slider("Размер доски (px)", 400, 800, 500, 20)
    
    st.divider()
    start_fen = st.text_input("Вставь FEN (оставь пустым для старта)", value="")

color_str = "white" if color_choice == "Белые" else "black"
time_seconds = time_minutes * 60
safe_fen = start_fen.replace('"', '\\"').replace("'", "\\'") if start_fen else ""

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
        .controls {{ margin: 15px auto; display: flex; justify-content: center; gap: 10px; flex-wrap: wrap; }}
        button {{ padding: 8px 15px; font-size: 16px; cursor: pointer; border-radius: 5px; border: 1px solid #ccc; background: #fff; }}
        button:hover {{ background: #eee; }}
        .panel {{ display: flex; justify-content: center; gap: 20px; margin-top: 15px; width: 90%; margin-left: 5%; }}
        #move-list {{ width: 250px; height: 150px; overflow-y: scroll; text-align: left; border: 1px solid #ccc; padding: 10px; background: #fff; font-family: monospace; }}
        #fen-output {{ width: 250px; height: 150px; border: 1px solid #ccc; padding: 10px; background: #fff; font-family: monospace; font-size: 10px; }}
        .score {{ font-size: 18px; font-weight: bold; color: #4a4a4a; background: #fff; display: inline-block; padding: 10px 20px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
        /* Подсветка для премува */
        .premove-target {{ background-color: rgba(255, 152, 0, 0.5) !important; }}
    </style>
</head>
<body>
    <div class="score" id="score-board">Счет: 0 - 0 - 0</div>
    <div id="status" style="margin-top: 10px;">Загрузка...</div>
    <div id="timer">
        <div class="clock" id="my-clock">Мой: {time_minutes:02d}:00</div>
        <div class="clock" id="opp-clock">Бот: {time_minutes:02d}:00</div>
    </div>
    <div id="board"></div>
    <div class="controls">
        <button onclick="newGame()">🔄 Новая партия</button>
        <button onclick="board.flip()">↕️ Повернуть</button>
        <button onclick="copyFen()">📋 Копировать FEN</button>
    </div>
    <div class="panel">
        <div id="move-list"><b>Ходы:</b><br></div>
        <textarea id="fen-output" readonly placeholder="Текущий FEN..."></textarea>
    </div>

    <script>
        var board = null;
        var game = new Chess();
        var $status = $('#status');
        var myTurnColor = '{color_str}' === 'white' ? 'w' : 'b';
        var botLevel = {level};
        var startFen = "{safe_fen}";
        
        var gameOver = false;
        var stockfish = null;
        var myTime = {time_seconds};
        var oppTime = {time_seconds};
        var timerInterval = null;
        
        var wins = 0, losses = 0, draws = 0;
        
        // Для премувов
        var premove = null;
        var premoveSquare = null;

        function updateClocks() {{
            $('#my-clock').text('Мой: ' + formatTime(myTime));
            $('#opp-clock').text('Бот: ' + formatTime(oppTime));
            if (gameOver) return;
            if (game.turn() === myTurnColor) {{
                $('#my-clock').addClass('active');
                $('#opp-clock').removeClass('active');
            }} else {{
                $('#my-clock').removeClass('active');
                $('#opp-clock').addClass('active');
            }}
        }}

        function formatTime(sec) {{
            var m = Math.floor(sec / 60);
            var s = sec % 60;
            return (m < 10 ? '0' : '') + m + ':' + (s < 10 ? '0' : '') + s;
        }}

        function startTimer() {{
            if (timerInterval) clearInterval(timerInterval);
            timerInterval = setInterval(function() {{
                if (gameOver || game.game_over()) return;
                if (game.turn() === myTurnColor) {{
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
            if (resultType === 'win') wins++;
            else if (resultType === 'loss') losses++;
            else if (resultType === 'draw') draws++;
            $('#score-board').text('Счет: ' + wins + ' - ' + losses + ' - ' + draws);
            updatePGN();
        }}

        function newGame() {{
            game.reset();
            if (startFen && startFen.length > 10) {{
                try {{ game.load(startFen); }} catch(e) {{}}
            }}
            myTime = {time_seconds};
            oppTime = {time_seconds};
            gameOver = false;
            premove = null;
            premoveSquare = null;
            $('.premove-target').removeClass('premove-target');
            
            board.position(game.fen());
            updateClocks();
            updateStatus();
            startTimer();
            updatePGN();
            
            if (myTurnColor === 'b') {{
                makeBotMove();
            }}
        }}

        var config = {{
            draggable: true,
            position: game.fen(),
            orientation: myTurnColor === 'w' ? 'white' : 'black',
            pieceTheme: 'https://lichess1.org/assets/piece/cburnett/{{piece}}.svg',
            onDragStart: onDragStart,
            onDrop: onDrop,
            onSnapEnd: onSnapEnd
        }};
        board = Chessboard('board', config);

        function onDragStart(source, piece, position, orientation) {{
            if (game.game_over() || gameOver) return false;
            // Разрешаем брать свои фигуры всегда (для премува)
            if (game.turn() === 'w' && piece.search(/^b/) !== -1) return false;
            if (game.turn() === 'b' && piece.search(/^w/) !== -1) return false;
        }}

        function onDrop(source, target) {{
            // Очищаем старую подсветку премува
            if (premoveSquare) {{
                $('.square-' + premoveSquare).removeClass('premove-target');
            }}

            if (game.turn() !== myTurnColor) {{
                // Это ПРЕМУВ (мы не можем сделать ход сейчас)
                // Запоминаем его и подсвечиваем
                premove = {{ from: source, to: target, promotion: 'q' }};
                premoveSquare = target;
                $('.square-' + target).addClass('premove-target');
                return 'snapback'; // Возвращаем фигуру на место
            }}

            // Обычный ход
            var move = game.move({{ from: source, to: target, promotion: 'q' }});
            if (move === null) return 'snapback';
            
            // Не вызываем здесь board.position(), ждем onSnapEnd
            updateStatus();
            updatePGN();
            makeBotMove();
        }}

        function onSnapEnd() {{
            board.position(game.fen());
            $('#fen-output').val(game.fen());
        }}

        function updatePGN() {{
            var history = game.history({{ verbose: true }});
            var html = "<b>Ходы:</b><br>";
            for (var i = 0; i < history.length; i += 2) {{
                var num = i / 2 + 1;
                html += num + ". " + history[i].san + " ";
                if (i + 1 < history.length) {{
                    html += history[i+1].san + " ";
                }}
            }}
            $('#move-list').html(html);
        }}

        function updateStatus() {{
            if (game.game_over()) {{
                var msg = 'Игра окончена: ';
                var res = 'draw';
                if (game.in_checkmate()) {{
                    var winner = game.turn() === 'w' ? 'Чёрные' : 'Белые';
                    msg += 'Мат (' + winner + ')';
                    res = (winner === 'Белые' && myTurnColor === 'w') || (winner === 'Чёрные' && myTurnColor === 'b') ? 'win' : 'loss';
                }}
                else if (game.in_draw()) msg += 'Ничья';
                $status.text(msg);
                endGame(msg, res);
                return;
            }}
            $status.text('Ход: ' + (game.turn() === 'w' ? 'Белые' : 'Чёрные'));
        }}

        function makeBotMove() {{
            if (game.game_over() || game.turn() === myTurnColor) return;
            $status.text('Stockfish думает...');
            setTimeout(function() {{
                if (stockfish) {{
                    stockfish.postMessage('position fen ' + game.fen());
                    stockfish.postMessage('go depth 10');
                }}
            }}, 200);
        }}

        // Загрузка Stockfish
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
                            // Бот делает ход
                            game.move({{ from: bestMove.substring(0,2), to: bestMove.substring(2,4), promotion: 'q' }});
                            board.position(game.fen());
                            updateStatus();
                            updatePGN();
                            
                            // ВЫПОЛНЕНИЕ ПРЕМУВА (если он есть)
                            if (premove) {{
                                $('.premove-target').removeClass('premove-target');
                                var pMove = game.move(premove);
                                if (pMove) {{
                                    board.position(game.fen());
                                    updateStatus();
                                    updatePGN();
                                    makeBotMove(); // Бот должен ответить на премув
                                }} else {{
                                    // Премув оказался нелегальным (например, фигуру съели)
                                    console.log("Премув нелегален");
                                }}
                                premove = null;
                                premoveSquare = null;
                            }}
                        }}
                    }}
                }};
                stockfish.postMessage('uci');
                stockfish.postMessage('setoption name Skill Level value ' + botLevel);
                
                // Инициализация игры
                if (myTurnColor === 'b') {{
                    newGame(); 
                }}
            }}).catch(function() {{
                $status.text('Ошибка загрузки Stockfish');
            }});

        window.copyFen = function() {{
            navigator.clipboard.writeText(game.fen()).then(function() {{
                alert('FEN скопирован!');
            }});
        }};

        // Запуск
        startTimer();
        updateClocks();
        updateStatus();
        board.position(game.fen());
    </script>
</body>
</html>
"""

components.html(html_code, height=board_size + 400, scrolling=False)