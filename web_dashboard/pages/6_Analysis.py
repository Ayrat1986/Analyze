# web_dashboard/pages/6_Analysis.py
import streamlit as st
import streamlit.components.v1 as components
import chess
import chess.pgn
import io
import urllib.parse
import _common
from _chess_utils import parse_clock

st.set_page_config(page_title="Анализ позиции", page_icon="🔬", layout="wide")
st.title("🔬 Анализ позиции")

with st.sidebar:
    st.header("⚙️ Настройки")
    board_size = st.slider("Размер доски (px)", 300, 800, 500, 50)

if "analyze_pgn" not in st.session_state:
    st.session_state.analyze_pgn = None
if "analyze_fen" not in st.session_state:
    st.session_state.analyze_fen = chess.STARTING_FEN
if "analysis_input" not in st.session_state:
    st.session_state.analysis_input = (
        st.session_state.analyze_pgn if st.session_state.analyze_pgn else st.session_state.analyze_fen
    )

def _on_input_change():
    raw = st.session_state.analysis_input
    if not raw: return
    if "[" in raw and "]" in raw:
        st.session_state.analyze_pgn = raw
        st.session_state.analyze_fen = None
    elif raw.count('/') >= 7:
        st.session_state.analyze_fen = raw
        st.session_state.analyze_pgn = None
    else:
        st.session_state.analyze_error = "Не удалось распознать FEN или PGN."
    
    # Сбрасываем ползунок при загрузке новой партии
    if "move_idx" in st.session_state:
        del st.session_state["move_idx"]

if "analyze_error" not in st.session_state:
    st.session_state.analyze_error = None

st.text_area("Вставь FEN или PGN партии:", key="analysis_input", height=100, on_change=_on_input_change)

if st.session_state.analyze_error:
    st.warning(st.session_state.analyze_error)

if st.session_state.analyze_pgn:
    try:
        game = chess.pgn.read_game(io.StringIO(st.session_state.analyze_pgn))
        if game:
            moves = list(game.mainline())
            if not moves:
                st.info("В PGN нет ходов.")
            else:
                clocks = parse_clock(st.session_state.analyze_pgn)
                player_white = game.headers.get("White", "Белые")
                player_black = game.headers.get("Black", "Чёрные")
                res = game.headers.get("Result", "*")
                
                # Инициализация состояния для перемотки
                if "move_idx" not in st.session_state:
                    st.session_state.move_idx = len(moves)

                # --- БЛОК УПРАВЛЕНИЯ ПЕРЕМОТКОЙ ---
                st.markdown("**Перемотка ходов:**")
                c_prev, c_slider, c_next = st.columns([1, 4, 1])
                
                with c_prev:
                    if st.button("⬅️", use_container_width=True) and st.session_state.move_idx > 0:
                        st.session_state.move_idx -= 1
                        st.rerun()
                        
                with c_slider:
                    # Слайдер привязан к move_idx
                    st.session_state.move_idx = st.slider(
                        "Слайдер", 0, len(moves), st.session_state.move_idx, label_visibility="collapsed"
                    )
                    
                with c_next:
                    if st.button("➡️", use_container_width=True) and st.session_state.move_idx < len(moves):
                        st.session_state.move_idx += 1
                        st.rerun()

                # --- РЕНДЕРИНГ ПОЗИЦИИ ---
                move_idx = st.session_state.move_idx
                board = game.board()
                current_fen = board.fen()
                time_white = "—"
                time_black = "—"
                last_move_san = "Стартовая позиция"
                
                if move_idx > 0:
                    for i in range(move_idx):
                        board.push(moves[i].move)
                    current_fen = board.fen()
                    last_move_san = f"{moves[move_idx-1].san()}"
                    
                    # Вычисляем потраченное время
                    if clocks and len(clocks) >= move_idx:
                        if move_idx >= 1:
                            w_idx = (move_idx - 1) * 2
                            if w_idx < len(clocks):
                                if w_idx == 0: t_w = 60.0 - clocks[0]
                                else: t_w = clocks[w_idx-1] - clocks[w_idx]
                                time_white = f"{t_w:.1f} сек"
                                
                        if move_idx >= 2:
                            b_idx = (move_idx - 2) * 2 + 1
                            if b_idx < len(clocks):
                                if b_idx == 1: t_b = 60.0 - clocks[1]
                                else: t_b = clocks[b_idx-1] - clocks[b_idx]
                                time_black = f"{t_b:.1f} сек"

                c_board, c_info = st.columns([1, 1])
                
                with c_board:
                    import chess.svg
                    svg = chess.svg.board(chess.Board(current_fen), size=board_size, colors={"square light": "#f0d9b5", "square dark": "#b58863"})
                    st.image(svg)
                    
                with c_info:
                    st.subheader(f"Ход: {last_move_san}")
                    st.markdown(f"**{player_white}** (Белые) | Время: `{time_white}`")
                    st.markdown(f"**{player_black}** (Чёрные) | Время: `{time_black}`")
                    st.markdown(f"Результат: `{res}`")
                    
                    st.divider()
                    st.markdown("**FEN текущей позиции:**")
                    st.code(current_fen, language="text")
                    
                    # --- ССЫЛКА НА LICHESS С PGN ---
                    # Используем текущий PGN, но без заголовков для чистоты, чтобы Lichess подхватил все ходы
                    clean_pgn = game.accept(chess.pgn.StringExporter(headers=False, variations=False, comments=False))
                    pgn_encoded = urllib.parse.quote(clean_pgn)
                    lichess_url = f"https://lichess.org/analysis/pgn/{pgn_encoded}"
                    
                    st.markdown(f"[🔗 Открыть партию на Lichess]({lichess_url})")
                
        else:
            st.error("Не удалось прочитать PGN.")
    except Exception as e:
        st.error(f"Ошибка парсинга PGN: {e}")
else:
    fen_underscored = (st.session_state.analyze_fen or chess.STARTING_FEN).replace(" ", "_")
    lichess_url = f"https://lichess.org/embed/analysis?fen={fen_underscored}&color=white"
    components.iframe(lichess_url, width=board_size, height=board_size+50, scrolling=False)
    st.markdown("**FEN текущей позиции:**")
    st.code(st.session_state.analyze_fen or chess.STARTING_FEN, language="text")