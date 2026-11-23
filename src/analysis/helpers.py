# ============================================================
# analysis/helpers.py (v25.3)
# FIX v25.3:
#   - describe_blunder() строго разделяет missed_own_mate и allowed_opponent_mate.
#   - Точная проверка точки зрения движка (score.white() vs my_color).
#   - Корректная обработка потери материала и позиционных ошибок.
# ============================================================

import math
import chess
import chess.pgn

PIECE_NAMES_RU = {
    chess.QUEEN: "ферзь",
    chess.ROOK: "ладья",
    chess.BISHOP: "слон",
    chess.KNIGHT: "конь",
    chess.PAWN: "пешка",
    chess.KING: "король",
}

PIECE_VALUES = {
    chess.QUEEN: 900,
    chess.ROOK: 500,
    chess.BISHOP: 300,
    chess.KNIGHT: 300,
    chess.PAWN: 100,
    chess.KING: 10000,
}


def get_opening_name(game: chess.pgn.Game) -> str:
    eco = game.headers.get("ECO", "")
    eco_url = game.headers.get("ECOUrl", "")
    if eco_url:
        name = eco_url.split("/")[-1].replace("-", " ")
        return f"{eco} {name}"
    return eco if eco else "Unknown"


def get_result_info(game, player_is_white: bool):
    result = game.headers.get("Result", "?")
    termination = game.headers.get("Termination", "?").lower()
    won = (result == "1-0") if player_is_white else (result == "0-1")
    draw = (result == "1/2-1/2")
    if draw:
        return {"won": False, "draw": True, "reason": "ничья", "termination": termination}
    if "time" in termination or "timeout" in termination:
        reason = "просрочка"
    elif "checkmate" in termination or "mate" in termination:
        reason = "мат"
    elif "resign" in termination:
        reason = "сдача"
    elif "abandon" in termination:
        reason = "отключение"
    else:
        reason = termination or "unknown"
    return {"won": won, "draw": False, "reason": reason, "termination": termination}


def material(board: chess.Board, color: bool) -> int:
    return sum(len(board.pieces(pt, color)) * val for pt, val in PIECE_VALUES.items())


def calculate_accuracy(avg_cp_loss) -> float:
    if avg_cp_loss is None or avg_cp_loss < 0:
        return 0.0
    return max(0.0, min(100.0, 100.0 * math.exp(-0.002 * avg_cp_loss)))


def describe_blunder(
    board_before: chess.Board,
    board_after_response: chess.Board,
    my_color: bool,
    loss: int,
    eval_before: int,
    eval_after: int,
    score_after,
    score_after_response=None,
):
    """
    Определяет паттерн зевка.
    Возвращает (описание, тег).
    Теги:
      missed_own_mate       — упущен форсированный мат за игрока
      allowed_opponent_mate — допущен форсированный мат соперника
      lost_queen / lost_piece / positional / blunder
    """
    # 1. Матовые признаки
    # score_after берется от лица белых: mate() > 0 => мат ставят белые
    def check_mate(score):
        if score is None or not score.is_mate():
            return None
        m = score.mate()
        if m is None:
            return None
        is_my_mate = (m > 0) if my_color == chess.WHITE else (m < 0)
        return is_my_mate, abs(m)

    m_after = check_mate(score_after)
    if m_after is not None:
        is_my_mate, moves_count = m_after
        if is_my_mate:
            return f"упущен мат в {moves_count}", "missed_own_mate"
        else:
            return f"допущен мат в {moves_count}", "allowed_opponent_mate"

    m_resp = check_mate(score_after_response)
    if m_resp is not None:
        is_my_mate, moves_count = m_resp
        if is_my_mate:
            return f"упущен мат в {moves_count}", "missed_own_mate"
        else:
            return f"допущен мат в {moves_count}", "allowed_opponent_mate"

    # 2. Потеря материала
    mat_before = material(board_before, my_color)
    mat_after = material(board_after_response, my_color)
    diff = mat_before - mat_after
    if diff > 0 and loss > 300:
        lost_pieces = []
        for pt, val in PIECE_VALUES.items():
            before_count = len(board_before.pieces(pt, my_color))
            after_count = len(board_after_response.pieces(pt, my_color))
            if after_count < before_count:
                lost_pieces.append((pt, before_count - after_count, val))
        if lost_pieces:
            lost_pieces.sort(key=lambda x: x[2], reverse=True)
            pt, count, val = lost_pieces[0]
            piece_name = PIECE_NAMES_RU.get(pt, "фигура")
            tag = "lost_queen" if pt == chess.QUEEN else "lost_piece"
            if count > 1:
                return f"потеря {count} {piece_name}ов", tag
            return f"потеря {piece_name}", tag

    # 3. Позиционные ошибки
    if loss > 500:
        return "позиционный провал", "positional"
    if loss > 300:
        return "позиционная ошибка", "positional"
    return "зевок", "blunder"
