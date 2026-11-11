# web_dashboard/pages/6_Analysis.py
import streamlit as st
import streamlit.components.v1 as components
import chess
import chess.pgn
import io

st.set_page_config(page_title="Анализ позиции", page_icon="🔬", layout="wide")
st.title("🔬 Анализ позиции")

with st.sidebar:
    st.header("⚙️ Размер окна")
    iframe_width = st.slider("Ширина (px)", 400, 1400, 850, 50)
    iframe_height = st.slider("Высота (px)", 600, 1500, 950, 50)

# FIX: state инициализируется один раз, без st.rerun() в цикле
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
    """Колбэк: разбирает ввод, обновляет state без st.rerun()."""
    raw = st.session_state.analysis_input
    if not raw:
        return
    if "[" in raw and "]" in raw:
        st.session_state.analyze_pgn = raw
        st.session_state.analyze_fen = None
    elif raw.count('/') >= 7:
        st.session_state.analyze_fen = raw
        st.session_state.analyze_pgn = None
    else:
        st.session_state.analyze_error = (
            "Не удалось распознать FEN или PGN. Проверь формат."
        )


if "analyze_error" not in st.session_state:
    st.session_state.analyze_error = None

st.text_area(
    "Вставь FEN или PGN партии:",
    key="analysis_input",
    height=150,
    on_change=_on_input_change,
)

if st.session_state.analyze_error:
    st.warning(st.session_state.analyze_error)

# Формируем URL для Lichess
if st.session_state.analyze_pgn:
    try:
        game = chess.pgn.read_game(io.StringIO(st.session_state.analyze_pgn))
        if game:
            start_fen = game.board().fen()
            exporter = chess.pgn.StringExporter(
                headers=False, variations=False, comments=False,
            )
            clean_pgn = game.accept(exporter)
            fen_underscored = start_fen.replace(" ", "_")
            lichess_url = (
                f"https://lichess.org/embed/analysis?"
                f"fen={fen_underscored}&color=white"
            )
            st.info("💡 Загружена партия (PGN). Начальная позиция передана на доску.")
            with st.expander("Показать PGN партии (для копирования)",
                             expanded=False):
                st.code(clean_pgn, language="text")
        else:
            st.error("Не удалось прочитать PGN.")
            lichess_url = (
                "https://lichess.org/embed/analysis?"
                f"fen={chess.STARTING_FEN.replace(' ', '_')}&color=white"
            )
    except Exception as e:
        st.error(f"Ошибка парсинга PGN: {e}")
        lichess_url = (
            "https://lichess.org/embed/analysis?"
            f"fen={chess.STARTING_FEN.replace(' ', '_')}&color=white"
        )
else:
    fen_underscored = (st.session_state.analyze_fen or chess.STARTING_FEN).replace(" ", "_")
    lichess_url = f"https://lichess.org/embed/analysis?fen={fen_underscored}&color=white"

# FIX: кнопка «Копировать FEN» рядом с доской
current_fen = (
    st.session_state.analyze_fen
    if not st.session_state.analyze_pgn
    else None
)
if current_fen:
    st.code(current_fen, language="text")
    st.caption("Скопируй FEN выше — можно вставить в Lichess, Chess.com или любой движок.")

components.iframe(lichess_url, width=iframe_width,
                  height=iframe_height, scrolling=True)