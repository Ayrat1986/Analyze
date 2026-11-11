# web_dashboard/utils/chess_vis.py — Рендер SVG-доски и извлечение FEN из PGN
import base64
import io
import os
import gzip
import json
from typing import Optional

import chess
import chess.pgn
import chess.svg

# --- FEN-кэш из stockfish_positions_cache.json.gz ---
_FEN_CACHE = None


def _load_fen_cache() -> dict:
    global _FEN_CACHE
    if _FEN_CACHE is not None:
        return _FEN_CACHE
    _FEN_CACHE = {}
    path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..", "data",
        "stockfish_positions_cache.json.gz"
    ))
    if not os.path.exists(path):
        return _FEN_CACHE
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            raw = json.load(f)
        _FEN_CACHE = raw.get("positions", {}) or {}
    except Exception:
        _FEN_CACHE = {}
    return _FEN_CACHE


def get_best_move_san(fen: str) -> Optional[str]:
    """Возвращает SAN лучшего хода из FEN-кэша, если есть."""
    cache = _load_fen_cache()
    return cache.get(fen)


def fen_before_move(pgn: str, move_num: int, player_is_white: bool) -> Optional[str]:
    """
    FEN позиции ПЕРЕД ходом move_num игрока.
    move_num — номер полного хода (как в games.fullmove_number до хода).
    """
    try:
        game = chess.pgn.read_game(io.StringIO(pgn))
        if not game:
            return None
        ply = (move_num - 1) * 2 + (0 if player_is_white else 1)
        board = game.board()
        for i, node in enumerate(game.mainline()):
            if i == ply:
                return board.fen()
            board.push(node.move)
        return None
    except Exception:
        return None


def render_board_html(
    fen: str,
    played_uci: Optional[str] = None,
    best_uci: Optional[str] = None,
    size: int = 420,
) -> str:
    """
    Возвращает HTML <img> с SVG-доской.
    played_uci — красная стрелка (твой ход).
    best_uci   — зелёная стрелка (лучший ход Stockfish).
    """
    board = chess.Board(fen)
    arrows = []

    def _try_arrow(uci: str, color: str):
        try:
            mv = chess.Move.from_uci(uci)
            if mv.from_square != mv.to_square:
                arrows.append(chess.svg.Arrow(mv.from_square, mv.to_square, color=color))
        except Exception:
            pass

    if played_uci:
        _try_arrow(played_uci, "#dc3545")
    if best_uci:
        _try_arrow(best_uci, "#28a745")

    try:
        svg = chess.svg.board(board, size=size, arrows=arrows, coordinates=True)
    except Exception:
        svg = chess.svg.board(board, size=size, coordinates=True)

    b64 = base64.b64encode(svg.encode("utf-8")).decode("utf-8")
    return f'<img src="data:image/svg+xml;base64,{b64}" width="{size}"/>'