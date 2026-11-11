# ============================================================
# analysis/helpers.py — хелперы для Stockfish-анализа
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


def get_result_info(game, player_is_white):
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
    if avg_cp_loss is None:
        return 0.0
    return max(0.0, min(100.0, 100 * math.exp(-0.002 * avg_cp_loss)))


def describe_blunder(board_before, board_after_response, my_color, loss,
                     eval_before, eval_after, score_after, score_after_response=None):
    """Определяет паттерн зевка (потеря ферзя, зевок мата и т.д.)"""

    # 1. Пропущенный мат (сначала проверяем ответ соперника)
    if score_after_response is not None:
        try:
            if score_after_response.is_mate():
                mate_n = score_after_response.mate()
                if mate_n is not None and mate_n > 0:
                    return f"зевок мата в {mate_n}", "missed_mate"
        except Exception:
            pass

    try:
        if score_after.is_mate():
            mate_n = score_after.mate()
            if mate_n is not None and mate_n > 0:
                return f"зевок мата в {mate_n}", "missed_mate"
    except Exception:
        pass

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