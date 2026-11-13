# ============================================================
# web_dashboard/pages/6_Analysis.py (v25.0)
# Фикс §SVG: st.image не рендерит SVG. Используем render_board_html.
# ============================================================
import sys
import os


def clear_pycache(start_path):
    import shutil
    for root, dirs, files in os.walk(start_path):
        for d in dirs:
            if d == '__pycache__':
                shutil.rmtree(os.path.join(root, d), ignore_errors=True)


BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DIR = os.path.join(BASE_DIR, "src")
WEB_DIR = os.path.dirname(os.path.abspath(__file__))
clear_pycache(SRC_DIR)
clear_pycache(WEB_DIR)

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import io
import urllib.parse
import chess
import chess.pgn
import streamlit as st
import streamlit.components.v1 as components

import _common
from _chess_utils import parse_clock
from utils.chess_vis import render_board_html

st.set_page_config(page_title="Анализ позиции", page_icon="🔬", layout="wide")
st.title("🔬 Анализ позиции")

with st.sidebar:
    st.header("⚙️ Настройки")
    board_size = st.slider("Размер доски (px)", 300, 800, 500, 50)

# --- Состояние ---
if "analyze_pgn" not in st.session_state:
    st.session_state.analyze_pgn = None
if "analyze_fen" not in st.session_state:
    st.session_state.analyze_fen = chess.STARTING_FEN
if "analysis_input" not in st.session_state:
    st.session_state.analysis_input = (
        st.session_state.analyze_pgn
        if st.session_state.analyze_pgn
        else st.session_state.analyze_fen
    )


def _on_input_change():
    raw = st.session_state.analysis_input
    if not raw:
        return
    if "[" in raw and "]" in raw:
        st.session_state.analyze_pgn = raw
        st.session_state.analyze_fen = None
    elif raw.count("/") >= 7:
        st.session_state.analyze_fen = raw
        st.session_state.analyze_pgn = None
    else:
        st.session_state.analyze_error = "Не удалось распознать FEN или PGN."
    if "move_idx" in st.session_state:
        del st.session_state["move_idx"]


if "analyze_error" not in st.session_state:
    st.session_state.analyze_error = None

st.text_area(
    "Вставь FEN или PGN партии:",
    key="analysis_input",
    height=100,
    on_change=_on_input_change,
)

if st.session_state.analyze_error:
    st.warning(st.session_state.analyze_error)


if st.session_state.analyze_pgn:
    # --- Разбор PGN ---
    try:
        game = chess.pgn.read_game(io.StringIO(st.session_state.analyze_pgn))
        if not game:
            st.error("Не удалось прочитать PGN.")
        else:
            moves = list(game.mainline())
            if not moves:
                st.info("В PGN нет ходов.")
            else:
                clocks = parse_clock(st.session_state.analyze_pgn)
                player_white = game.headers.get("White", "Белые")
                player_black = game.headers.get("Black", "Чёрные")
                res = game.headers.get("Result", "*")

                if "move_idx" not in st.session_state:
                    st.session_state.move_idx = len(moves)

                # --- Перемотка ---
                st.markdown("**Перемотка ходов:**")
                c_prev, c_slider, c_next = st.columns([1, 4, 1])

                with c_prev:
                    if st.button("⬅️", use_container_width=True) and st.session_state.move_idx > 0:
                        st.session_state.move_idx -= 1
                        st.rerun()

                with c_slider:
                    st.session_state.move_idx = st.slider(
                        "Слайдер", 0, len(moves),
                        st.session_state.move_idx,
                        label_visibility="collapsed",
                    )

                with c_next:
                    if st.button("➡️", use_container_width=True) and st.session_state.move_idx < len(moves):
                        st.session_state.move_idx += 1
                        st.rerun()

                # --- Позиция на move_idx ---
                move_idx = st.session_state.move_idx
                board = game.board()
                current_fen = board.fen()
                time_white = "—"
                time_black = "—"
                last_move_san = "Стартовая позиция"
                last_move_uci = None

                if move_idx > 0:
                    for i in range(move_idx):
                        board.push(moves[i].move)
                    current_fen = board.fen()
                    last_move_san = moves[move_idx - 1].san()
                    last_move_uci = moves[move_idx - 1].move.uci()

                    if clocks and len(clocks) >= move_idx:
                        if move_idx >= 1:
                            w_idx = (move_idx - 1) * 2
                            if w_idx < len(clocks):
                                if w_idx == 0:
                                    t_w = 60.0 - clocks[0]
                                else:
                                    t_w = clocks[w_idx - 1] - clocks[w_idx]
                                time_white = f"{t_w:.1f} сек"
                        if move_idx >= 2:
                            b_idx = (move_idx - 2) * 2 + 1
                            if b_idx < len(clocks):
                                if b_idx == 1:
                                    t_b = 60.0 - clocks[1]
                                else:
                                    t_b = clocks[b_idx - 1] - clocks[b_idx]
                                time_black = f"{t_b:.1f} сек"

                c_board, c_info = st.columns([1, 1])

                with c_board:
                    # v25.0 (§SVG): render_board_html + st.markdown
                    # Подсветка последнего хода красной стрелкой
                    html = render_board_html(
                        current_fen,
                        played_uci=last_move_uci,
                        size=board_size,
                    )
                    st.markdown(html, unsafe_allow_html=True)

                with c_info:
                    st.subheader(f"Ход: {last_move_san}")
                    st.markdown(f"**{player_white}** (Белые) | Время: `{time_white}`")
                    st.markdown(f"**{player_black}** (Чёрные) | Время: `{time_black}`")
                    st.markdown(f"Результат: `{res}`")

                    st.divider()
                    st.markdown("**FEN текущей позиции:**")
                    st.code(current_fen, language="text")

                    clean_pgn = game.accept(
                        chess.pgn.StringExporter(
                            headers=False, variations=False, comments=False,
                        )
                    )
                    pgn_encoded = urllib.parse.quote(clean_pgn)
                    lichess_url = f"https://lichess.org/analysis/pgn/{pgn_encoded}"
                    st.markdown(f"[🔗 Открыть партию на Lichess]({lichess_url})")

    except Exception as e:
        st.error(f"Ошибка парсинга PGN: {e}")

else:
    # --- Разбор FEN ---
    fen_value = st.session_state.analyze_fen or chess.STARTING_FEN
    fen_underscored = fen_value.replace(" ", "_")
    lichess_url = f"https://lichess.org/embed/analysis?fen={fen_underscored}&color=white"

    c_board, c_info = st.columns([1, 1])
    with c_board:
        # v25.0 (§SVG): свой рендер доски вместо chess.svg (для консистентности)
        # Lichess-iframe оставляем для интерактивного анализа
        components.iframe(lichess_url, width=board_size, height=board_size + 50, scrolling=False)

    with c_info:
        st.markdown("**FEN текущей позиции:**")
        st.code(fen_value, language="text")

        st.divider()
        st.markdown("**Локальный рендер (base64 SVG):**")
        html = render_board_html(fen_value, size=board_size)
        st.markdown(html, unsafe_allow_html=True)