# ============================================================
# web_dashboard/pages/11_Trainer.py (v29.2)
# - Серия из 3 правильных ходов для решения тактической задачи.
# - На каждом шаге бот отвечает и рассчитывает лучший ход для проверки следующего шага игрока.
# - Режим Эндшпиля работает без лимита в 3 хода (доигрывание).
# ============================================================
import sys
import os
import pandas as pd
import chess
import json
import streamlit as st
import streamlit.components.v1 as components

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DIR = os.path.join(BASE_DIR, "src")
if BASE_DIR not in sys.path: sys.path.insert(0, BASE_DIR)
if SRC_DIR not in sys.path: sys.path.insert(0, SRC_DIR)

from utils.db import query_df, cutoff_ts
from utils import trainer_db
from analysis.trainer.smart_deck import generate_smart_deck

st.set_page_config(page_title="Тренажёр", page_icon="🎯", layout="wide")
st.title("🎯 Тренажёр (Daily Trainer)")

trainer_db.ensure_table()

REPORTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "reports"))
SMART_DECK_CSV = os.path.join(REPORTS_DIR, "training", "smart_deck.csv")

stats = trainer_db.get_stats()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Всего задач", stats["total"])
c2.metric("✅ Решено", stats["solved"]["n"])
c3.metric("❌ Не решено", stats["failed"]["n"])
c4.metric("⏭ Отложено", stats["skipped"]["n"])
st.divider()

with st.sidebar:
    st.header("⚙️ Настройки")
    board_size = st.slider("Размер доски (px)", 400, 1000, 500, 50)
    target_moves = st.slider("Ходов для решения задачи", 1, 5, 3)

def render_smart_board(fen: str, best_move_uci: str = None, size: int = 500, max_moves: int = 3, is_endgame: bool = False) -> str:
    fen_json = json.dumps(fen)
    
    valid_best_move = None
    try:
        b = chess.Board(fen)
        if best_move_uci:
            if chess.Move.from_uci(best_move_uci) in b.legal_moves:
                valid_best_move = best_move_uci
    except Exception:
        pass
        
    best_move_js = json.dumps(valid_best_move) if valid_best_move else "null"
    turn = fen.split()[1] if len(fen.split()) > 1 else 'w'
    orientation = 'white' if turn == 'w' else 'black'
    is_endgame_js = "true" if is_endgame else "false"
    
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
            body {{ text-align: center; font-family: sans-serif; margin: 0; padding: 0; background-color: transparent; }}
            #board-container {{ width: {size}px; margin: 0 auto; }}
            .status {{ font-size: 16px; font-weight: bold; margin-top: 10px; min-height: 28px; }}
            .correct {{ color: #2ecc71; }}
            .wrong {{ color: #e74c3c; }}
            .task-complete {{ color: #fff; background-color: #2ecc71; padding: 6px 12px; border-radius: 5px; display: inline-block; }}
            .controls {{ margin-top: 10px; display: flex; flex-wrap: wrap; justify-content: center; gap: 5px; }}
            button {{ padding: 6px 12px; font-size: 14px; cursor: pointer; border-radius: 4px; border: 1px solid #ccc; background: #f8f9fa; }}
            button:hover {{ background: #e2e6ea; }}
        </style>
    </head>
    <body>
        <div id="board-container"></div>
        <div class="controls">
            <button onclick="board.flip()">↕️ Перевернуть</button>
            <button onclick="undoMove()">↩️ Отменить ход</button>
            <button onclick="showHint()" style="background: #ffeeba; border-color: #ffdf7e;">💡 Подсказка</button>
            <button onclick="showBest()" style="background: #d4edda; border-color: #c3e6cb;">✅ Показать лучший</button>
        </div>
        <div class="status" id="status">Загрузка движка...</div>
        
        <script>
            var game = new Chess({fen_json});
            var dbBestMove = {best_move_js};
            var board = null;
            var stockfish = null;
            
            var originalTurn = game.turn();
            var userMovesCount = 0;
            var targetMoves = {max_moves};
            var isEndgame = {is_endgame_js};
            var taskSolved = false;
            
            // Режимы работы движка: 'idle' | 'eval_player_turn' | 'bot_reply' | 'check_alt'
            var sfState = 'idle';
            var engineBestMove = null;
            var bestEvalBefore = null;
            var altEvalAfter = null;
            
            $(document).ready(function() {{
                board = Chessboard('board-container', {{
                    draggable: true,
                    position: game.fen(),
                    orientation: '{orientation}',
                    pieceTheme: 'https://lichess1.org/assets/piece/cburnett/{{piece}}.svg',
                    onDragStart: function(source, piece, position, orientation) {{
                        if (game.game_over() || sfState === 'bot_reply' || sfState === 'check_alt' || taskSolved) return false;
                        if ((game.turn() === 'w' && piece.search(/^b/) !== -1) || (game.turn() === 'b' && piece.search(/^w/) !== -1)) {{
                            return false;
                        }}
                    }},
                    onDrop: onDrop,
                    onSnapEnd: function() {{
                        board.position(game.fen());
                    }}
                }});
                
                fetch('https://cdnjs.cloudflare.com/ajax/libs/stockfish.js/10.0.2/stockfish.js')
                    .then(response => response.blob())
                    .then(blob => {{
                        const blobUrl = URL.createObjectURL(blob);
                        stockfish = new Worker(blobUrl);
                        stockfish.onmessage = function(event) {{
                            var msg = event.data;
                            if (typeof msg !== 'string') return;
                            
                            // Читаем оценку и лучшую линию
                            if (msg.indexOf('info depth') !== -1) {{
                                var scoreCpMatch = msg.match(/score cp (-?\\d+)/);
                                var scoreMateMatch = msg.match(/score mate (-?\\d+)/);
                                var pvMatch = msg.match(/ pv (.*)/);
                                
                                var score = null;
                                if (scoreCpMatch) score = parseInt(scoreCpMatch[1]);
                                else if (scoreMateMatch) {{
                                    var m = parseInt(scoreMateMatch[1]);
                                    score = (m > 0 ? 10000 - m : -10000 - m);
                                }}
                                
                                if (sfState === 'eval_player_turn') {{
                                    if (score !== null) bestEvalBefore = score;
                                    if (pvMatch) engineBestMove = pvMatch[1].trim().split(' ')[0];
                                }} else if (sfState === 'check_alt') {{
                                    if (score !== null) altEvalAfter = score;
                                }}
                            }}
                            
                            // Завершение расчета движка
                            if (msg.indexOf('bestmove') === 0) {{
                                var bm = msg.split(' ')[1];
                                
                                if (sfState === 'eval_player_turn') {{
                                    if (!engineBestMove && bm && bm !== '(none)') {{
                                        engineBestMove = bm;
                                    }}
                                    sfState = 'idle';
                                }} 
                                else if (sfState === 'check_alt') {{
                                    // Сравниваем оценку до хода (bestEvalBefore) и после хода соперника (-altEvalAfter)
                                    var playerEvalAfter = (altEvalAfter !== null) ? -altEvalAfter : null;
                                    // Допускаем потерю до 60 сантипешек для альтернативного хода
                                    var isGoodAlt = (bestEvalBefore !== null && playerEvalAfter !== null && (bestEvalBefore - playerEvalAfter) <= 60);
                                    
                                    if (isGoodAlt) {{
                                        acceptPlayerMove('✅ Хороший ход!');
                                    }} else {{
                                        sfState = 'idle';
                                        $('#status').text('❌ Ошибка. Есть ход намного сильнее. Пробуй еще.').removeClass('correct').addClass('wrong');
                                        game.undo();
                                        board.position(game.fen());
                                        startPlayerTurnEval();
                                    }}
                                }} 
                                else if (sfState === 'bot_reply') {{
                                    if (bm && bm !== '(none)') {{
                                        game.move({{ from: bm.substring(0,2), to: bm.substring(2,4), promotion: 'q' }});
                                        board.position(game.fen());
                                    }}
                                    
                                    if (game.game_over()) {{
                                        taskSolved = true;
                                        sfState = 'idle';
                                        $('#status').html('<span class="task-complete">🎉 Партия окончена! Жми зеленую кнопку "Решено".</span>');
                                    }} else {{
                                        $('#status').text('Твой ход (' + (userMovesCount + 1) + ' из ' + targetMoves + ')').removeClass('correct wrong');
                                        startPlayerTurnEval();
                                    }}
                                }}
                            }}
                        }};
                        stockfish.postMessage('uci');
                        $('#status').text(isEndgame ? 'Эндшпиль: твой ход' : 'Сделай ход (1 из ' + targetMoves + ')').removeClass('correct wrong');
                        startPlayerTurnEval();
                    }}).catch(e => console.log('Ошибка движка:', e));
            }});

            function startPlayerTurnEval() {{
                if (!stockfish || taskSolved) return;
                sfState = 'eval_player_turn';
                engineBestMove = null;
                bestEvalBefore = null;
                stockfish.postMessage('stop');
                stockfish.postMessage('position fen ' + game.fen());
                stockfish.postMessage('go depth 12');
            }}

            function acceptPlayerMove(msgText) {{
                userMovesCount++;
                
                // На 2-м и 3-м ходу старый ход из БД больше не актуален
                dbBestMove = null; 
                
                if (!isEndgame && (userMovesCount >= targetMoves || game.game_over())) {{
                    taskSolved = true;
                    sfState = 'idle';
                    $('#status').html('<span class="task-complete">🎉 Задача решена (' + userMovesCount + '/' + targetMoves + ')! Жми "Решено" справа.</span>');
                    return;
                }}
                
                $('#status').text(msgText + ' Бот отвечает... (' + userMovesCount + '/' + (isEndgame ? '∞' : targetMoves) + ')').removeClass('wrong').addClass('correct');
                sfState = 'bot_reply';
                if (stockfish) {{
                    stockfish.postMessage('stop');
                    stockfish.postMessage('position fen ' + game.fen());
                    stockfish.postMessage('go depth 10');
                }}
            }}

            function onDrop(source, target) {{
                if (sfState === 'bot_reply' || sfState === 'check_alt' || taskSolved) return 'snapback';
                var move = game.move({{ from: source, to: target, promotion: 'q' }});
                if (move === null) return 'snapback';
                
                var moveUci = move.from + move.to + (move.promotion || '');
                
                if (isEndgame) {{
                    acceptPlayerMove('Ход сделан.');
                    return;
                }}
                
                // 1. Проверяем совпадение с БД (только на 1-м ходу) или с лучшим ходом движка
                var activeBest = (userMovesCount === 0 && dbBestMove) ? dbBestMove : engineBestMove;
                
                if ((activeBest && moveUci === activeBest) || (engineBestMove && moveUci === engineBestMove)) {{
                    acceptPlayerMove('✅ Отлично!');
                }} else if (stockfish) {{
                    // Проверяем альтернативный ход по оценке (если есть несколько равных ходов, как при шахе)
                    $('#status').text('Проверка хода...').removeClass('correct wrong');
                    sfState = 'check_alt';
                    altEvalAfter = null;
                    stockfish.postMessage('stop');
                    stockfish.postMessage('position fen ' + game.fen());
                    stockfish.postMessage('go depth 10');
                }} else {{
                    $('#status').text('❌ Ошибка. Пробуй еще.').removeClass('correct').addClass('wrong');
                    setTimeout(function() {{ game.undo(); board.position(game.fen()); }}, 800);
                }}
            }}

            function undoMove() {{
                if (taskSolved) return;
                if (game.history().length === 0) return;
                
                game.undo(); 
                if (game.turn() !== originalTurn && game.history().length > 0) {{
                    game.undo();
                }}
                if (userMovesCount > 0) userMovesCount--;
                if (userMovesCount === 0) dbBestMove = {best_move_js};
                
                board.position(game.fen());
                $('#status').text('Сделай ход (' + (userMovesCount + 1) + ' из ' + targetMoves + ')').removeClass('correct wrong task-complete');
                startPlayerTurnEval();
            }}

            function showHint() {{
                if (taskSolved) return;
                var best = (userMovesCount === 0 && dbBestMove) ? dbBestMove : engineBestMove;
                if (best) {{
                    var from = best.substring(0, 2);
                    $('#status').text('💡 Подсказка: посмотри на фигуру на поле ' + from).addClass('correct').removeClass('wrong');
                    $('.square-' + from).css('box-shadow', 'inset 0 0 0 4px #ffeb3b');
                    setTimeout(function() {{ $('.square-' + from).css('box-shadow', ''); }}, 2000);
                }} else {{
                    $('#status').text('⏳ Движок еще считает лучший ход, подожди секунду...').addClass('wrong').removeClass('correct');
                }}
            }}

            function showBest() {{
                if (taskSolved) return;
                var best = (userMovesCount === 0 && dbBestMove) ? dbBestMove : engineBestMove;
                if (best) {{
                    var from = best.substring(0, 2);
                    var to = best.substring(2, 4);
                    var move = game.move({{ from: from, to: to, promotion: 'q' }});
                    if (move) {{
                        board.position(game.fen());
                        acceptPlayerMove('✅ Лучший ход: ' + from + ' → ' + to + '.');
                    }} else {{
                        // Если ход из БД оказался битым, берем ход от движка
                        if (engineBestMove && engineBestMove !== best) {{
                            var f2 = engineBestMove.substring(0, 2);
                            var t2 = engineBestMove.substring(2, 4);
                            var m2 = game.move({{ from: f2, to: t2, promotion: 'q' }});
                            if (m2) {{
                                board.position(game.fen());
                                acceptPlayerMove('✅ Лучший ход: ' + f2 + ' → ' + t2 + '.');
                                return;
                            }}
                        }}
                        $('#status').text('⚠️ Подожди секунду, движок уточняет ход...').addClass('wrong');
                        startPlayerTurnEval();
                    }}
                }} else {{
                    $('#status').text('⏳ Движок еще думает, нажми через секунду.').addClass('wrong');
                }}
            }}
        </script>
    </body>
    </html>
    """
    return html

def render_single_task(task_type: str, fen: str, title: str, subtitle: str, best_move: str = None, is_endgame: bool = False):
    h = trainer_db.task_hash(task_type, fen)
    st.markdown(f"### {title}")
    st.caption(subtitle)
    
    c1, c2 = st.columns([1, 1])
    with c1:
        best_uci = None
        if best_move:
            try:
                b = chess.Board(fen)
                try:
                    best_uci = b.parse_san(str(best_move)).uci()
                except ValueError:
                    if chess.Move.from_uci(str(best_move)) in b.legal_moves:
                        best_uci = str(best_move)
            except Exception:
                best_uci = None 
                
        components.html(render_smart_board(fen, best_uci, size=board_size, max_moves=target_moves, is_endgame=is_endgame), height=board_size + 120)
        
    with c2:
        if is_endgame:
            st.info("💡 Режим Эндшпиля: разыграй позицию против движка без ограничения по ходам.")
        else:
            st.info(f"💡 Цель — сделать серию из **{target_moves}** сильных ходов подряд против Stockfish.")
        st.code(fen, language="text")
        
        if st.button("🔬 Открыть позицию в Анализаторе", key=f"open_{h}", use_container_width=True):
            st.session_state["analyze_fen"] = fen
            st.session_state["analyze_pgn"] = None
            st.session_state["input_value"] = fen
            st.switch_page("pages/6_Analysis.py")
            
        st.divider()
        c_solved, c_failed, c_skip = st.columns(3)
        with c_solved:
            if st.button("✅ Решено", key=f"solved_{h}", use_container_width=True, type="primary"):
                trainer_db.mark_solved(task_type, fen)
                st.rerun()
        with c_failed:
            if st.button("❌ Не решил", key=f"failed_{h}", use_container_width=True):
                trainer_db.mark_failed(task_type, fen, retry_days=3)
                st.rerun()
        with c_skip:
            if st.button("⏭ Пропустить", key=f"skip_{h}", use_container_width=True):
                trainer_db.mark_skipped(task_type, fen)
                st.rerun()

# --- ВКЛАДКИ ---
tab1, tab2, tab3, tab4 = st.tabs([
    "📚 Умная Колода", "🔥 Худшие зевки", "🛡️ Эндшпиль", "🗄️ Архив"
])

with tab1:
    if not os.path.exists(SMART_DECK_CSV):
        st.warning("Колода ещё не сгенерирована.")
        if st.button("🔄 Сгенерировать колоду сейчас"):
            with st.spinner("Анализируем базу..."): generate_smart_deck()
            st.rerun()
    else:
        df = pd.read_csv(SMART_DECK_CSV)
        if df.empty: st.success("🎉 Нет грубых зевков.")
        else:
            visible = df[~df["fen"].isin(trainer_db.get_active_fens("smart_deck"))]
            if visible.empty: st.success("✅ Все задачи решены!")
            else:
                r = visible.iloc[0]
                st.markdown(f"**Осталось: {len(visible)} из {len(df)}**")
                render_single_task("smart_deck", r["fen"], f"{r['white'][:15]} vs {r['black'][:15]}", f"Ход {r['move_num']}, потеря {r['loss_cp']} CP", best_move=r["best_move"])

with tab2:
    ts = cutoff_ts(365)
    worst = query_df(f"SELECT b.fen_before, b.move_num, b.loss_cp, b.best_move_uci, b.pattern_tag, g.white, g.black FROM blunders b JOIN games g ON g.url = b.game_url WHERE g.is_lag=0 AND g.is_cheater=0 AND b.is_my_blunder=1 AND b.is_berserk=0 AND b.is_instant=0 AND b.fen_before IS NOT NULL AND b.fen_before != '' AND g.end_time >= ? ORDER BY b.loss_cp DESC LIMIT 50", (ts,))
    if worst.empty: st.info("Нет зевков.")
    else:
        visible = worst[~worst["fen_before"].isin(trainer_db.get_active_fens("worst"))]
        if visible.empty: st.success("✅ Все решены!")
        else:
            r = visible.iloc[0]
            st.markdown(f"**Осталось: {len(visible)} из {len(worst)}**")
            render_single_task("worst", r["fen_before"], f"{r['white'][:15]} vs {r['black'][:15]}", f"Ход {r['move_num']}, потеря {r['loss_cp']} CP", best_move=r["best_move_uci"])

with tab3:
    endgame_path = os.path.join(REPORTS_DIR, "training", "endgame_positions.csv")
    if os.path.exists(endgame_path):
        eg_df = pd.read_csv(endgame_path)
        if not eg_df.empty:
            visible = eg_df[~eg_df["fen"].isin(trainer_db.get_active_fens("endgame"))]
            if visible.empty: st.success("✅ Все решены!")
            else:
                r = visible.iloc[0]
                match_names = query_df("SELECT white, black FROM games WHERE url=?", (r['url'],))
                match_str = f"{match_names.iloc[0]['white']} vs {match_names.iloc[0]['black']}" if not match_names.empty else "Партия"
                st.markdown(f"**Осталось: {len(visible)} из {len(eg_df)}**")
                render_single_task("endgame", r["fen"], match_str, f"ACPL {r['acpl_endgame']:.0f}", best_move=None, is_endgame=True)
    else: st.warning("Файл эндшпиля не найден.")

with tab4:
    st.subheader("🗄️ Архив решённых задач")
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