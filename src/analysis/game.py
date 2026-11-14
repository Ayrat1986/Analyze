# ============================================================
# analysis/game.py — анализ одной шахматной партии (v25.1)
# §32: ACPL в зоне берсерка (<10 сек) НЕ СЧИТАЕТСЯ.
#      moves_normal = только ходы с >10 сек на часах.
#      blunders всё равно сохраняются (для тренажера).
# FIX v25.1: Убран несуществующий аргумент timeout=30.0 из
#            engine.analyse(). Вместо него добавлен time=30.0
#            внутрь chess.engine.Limit() (соблюдает §19).
# ============================================================
import io
import chess
import chess.pgn
import chess.engine
from datetime import datetime, timezone

from .constants import (
    DEPTH, BLUNDER_THRESHOLD,
    NORMAL_TIME, BERSERK_TIME, INSTANT_TIME,
    TRUE_BERSERK_CLOCK, TRUE_BERSERK_MIN_MOVES, TIME_THRESHOLDS_VERSION
)
from .helpers import get_opening_name, get_result_info, describe_blunder, calculate_accuracy


def analyze_game(game_data: dict, engine: chess.engine.SimpleEngine, player: str) -> dict:
    pgn = game_data["pgn"]
    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None:
        raise ValueError(f"Битый PGN: {game_data.get('url', '?')}")

    board = game.board()

    from _chess_utils import (
        parse_clock, get_opponent_rating, get_my_rating,
        get_opponent_username, load_known_cheaters,
        classify_opponent_style
    )
    clocks = parse_clock(pgn)

    player_is_white = game.headers.get("White", "") == player
    my_color = chess.WHITE if player_is_white else chess.BLACK

    opponent_rating = get_opponent_rating(game_data, player)
    my_rating = get_my_rating(game_data, player)
    opp_username = get_opponent_username(game_data, player)
    is_cheater = opp_username in load_known_cheaters()

    eco = game.headers.get("ECO", "")
    opening = get_opening_name(game)
    res_info = get_result_info(game, player_is_white)
    won, draw, reason = res_info["won"], res_info["draw"], res_info["reason"]
    time_control = game_data.get("time_control", "unknown")

    blunders = []
    total_loss = 0
    our_moves = 0
    move_num = 1
    last_move_num = 0

    loss_berserk = 0; moves_berserk = 0
    loss_op = 0; moves_op = 0
    loss_mid = 0; moves_mid = 0
    loss_end = 0; moves_end = 0
    opp_total_loss = 0; opp_total_moves = 0; opp_blunders_count = 0

    berserk_move_enter = None
    moves = list(game.mainline())
    eval_history = []
    eval_history_peak = []
    opening_line = []

    eval_after_opening = 0
    moves_in_winning_position = 0
    momentum_after_blunder = []
    critical_moments = 0
    prev_eval = None
    our_move_indices = []
    eval_by_move = {}

    timeout_at_move = None
    timeout_with_clock = None

    for i, node in enumerate(moves):
        move = node.move
        is_white = board.turn
        move_num = board.fullmove_number
        last_move_num = move_num

        my_time_before = None; opp_time_before = None
        if i < len(clocks):
            if player_is_white:
                if i % 2 == 0:
                    my_time_before = clocks[i - 1] if i > 0 else 60.0
                else:
                    opp_time_before = clocks[i - 1] if i > 0 else 60.0
            else:
                if i % 2 == 1:
                    my_time_before = clocks[i - 1] if i > 0 else 60.0
                else:
                    opp_time_before = clocks[i - 1] if i > 0 else 60.0

        if move_num <= 10:
            opening_line.append(move.uci())

        # FIX: time=30.0 внутри Limit вместо несуществующего timeout
        info_before = engine.analyse(board, chess.engine.Limit(depth=DEPTH, time=30.0))
        score_before = info_before["score"].white()

        board_before_fen = board.fen()

        board.push(move)
        # FIX: time=30.0 внутри Limit
        info_after = engine.analyse(board, chess.engine.Limit(depth=DEPTH, time=30.0))
        score_after = info_after["score"].white()

        if score_before.is_mate() or score_after.is_mate():
            continue

        eval_before = score_before.score()
        eval_after = score_after.score()
        if abs(eval_before) > 2000 or abs(eval_after) > 2000:
            continue

        if is_white == player_is_white:
            eval_by_move[move_num] = eval_before

        if move_num == 10 and is_white == player_is_white:
            eval_after_opening = eval_after if player_is_white else -eval_after

        if is_white == player_is_white:
            eval_player = eval_before if player_is_white else -eval_before
            eval_history.append((move_num, eval_player))
            eval_history_peak.append(eval_player)

            if prev_eval is not None:
                if abs(eval_player - prev_eval) >= 200:
                    critical_moments += 1
            prev_eval = eval_player

            if eval_player > 300:
                moves_in_winning_position += 1

            our_move_indices.append(i)

        if is_white:
            loss = eval_before - eval_after
        else:
            loss = eval_after - eval_before
        our_move = (is_white == player_is_white)

        if our_move:
            our_moves += 1
            time_spent = 0.0
            if i < len(clocks):
                if player_is_white and i % 2 == 0:
                    curr_clock = clocks[i]
                    prev_clock = clocks[i - 2] if i >= 2 else 60.0
                elif not player_is_white and i % 2 == 1:
                    curr_clock = clocks[i]
                    prev_clock = clocks[i - 2] if i >= 2 else 60.0
                else:
                    curr_clock = clocks[i]
                    prev_clock = clocks[i - 1] if i > 0 else 60.0
                if prev_clock is not None:
                    time_spent = prev_clock - curr_clock

            is_berserk = (my_time_before is not None and my_time_before < BERSERK_TIME) or \
                         (opp_time_before is not None and opp_time_before < BERSERK_TIME)
            is_normal = (my_time_before is not None and my_time_before > NORMAL_TIME) and \
                        (opp_time_before is not None and opp_time_before > NORMAL_TIME)
            is_instant = (time_spent < INSTANT_TIME and my_time_before is not None and my_time_before > NORMAL_TIME)

            # §32: зона берсерка по часам (менее 10 сек)
            is_true_berserk_clock = (my_time_before is not None and my_time_before < TRUE_BERSERK_CLOCK)

            if my_time_before is not None and my_time_before < BERSERK_TIME and berserk_move_enter is None:
                berserk_move_enter = move_num

            # Считаем потери только если это НЕ берсерк по часам
            if is_true_berserk_clock:
                moves_berserk += 1
                if loss > 0: loss_berserk += loss
            else:
                if move_num <= 10:
                    moves_op += 1
                    if loss > 0: loss_op += loss
                elif move_num <= 30:
                    moves_mid += 1
                    if loss > 0: loss_mid += loss
                else:
                    moves_end += 1
                    if loss > 0: loss_end += loss

                if loss > 0:
                    total_loss += loss

            if loss > BLUNDER_THRESHOLD and abs(eval_before) < 1000:
                board_before = chess.Board(board_before_fen)
                board_after_response = board.copy()
                score_after_response = None
                if i + 1 < len(moves):
                    board_after_response.push(moves[i + 1].move)
                    try:
                        # FIX: time=30.0 внутри Limit
                        info_resp = engine.analyse(board_after_response, chess.engine.Limit(depth=DEPTH, time=30.0))
                        score_after_response = info_resp["score"].white()
                    except Exception:
                        pass

                what_happened, pattern_tag = describe_blunder(
                    board_before, board_after_response, my_color, loss,
                    eval_before, eval_after, score_after, score_after_response,
                )

                tag = " [берсерк]" if is_berserk else (" [мгновенный ход]" if is_instant else (" [пограничное]" if not is_normal else ""))
                eval_swing = (eval_after - eval_before) / 100.0
                ply_val = (move_num - 1) * 2 + (0 if player_is_white else 1)

                best_uci = None
                try:
                    pv = info_before.get("pv")
                    if pv:
                        best_uci = pv[0].uci()
                except Exception:
                    pass

                missed_threat = 0
                if i + 1 < len(moves) and loss >= 300:
                    next_move = moves[i + 1].move
                    if next_move in board.legal_moves:
                        if board.is_capture(next_move):
                            missed_threat = 1
                        else:
                            try:
                                b_after = board.copy()
                                b_after.push(next_move)
                                if b_after.is_checkmate():
                                    missed_threat = 1
                            except Exception:
                                pass

                blunders.append({
                    "move_num": move_num, "move": move.uci(), "loss": loss,
                    "eval_before": eval_before, "eval_after": eval_after,
                    "eval_swing": eval_swing,
                    "what": what_happened + tag, "pattern_tag": pattern_tag,
                    "is_berserk": is_berserk, "is_normal": is_normal, "is_instant": is_instant,
                    "time_spent": round(time_spent, 1), "player_is_white": player_is_white,
                    "is_my_blunder": True,
                    "next_move_time": None,
                    "is_next_move_blunder": False,
                    "ply": ply_val,
                    "fen_before": board_before_fen,
                    "best_move_uci": best_uci,
                    "missed_threat": missed_threat,
                })

                future_losses = []
                for next_mn in range(move_num + 1, move_num + 6):
                    if next_mn in eval_by_move:
                        current_eval = eval_by_move.get(move_num, 0)
                        next_eval = eval_by_move[next_mn]
                        if player_is_white:
                            l_temp = current_eval - next_eval
                        else:
                            l_temp = next_eval - current_eval
                        if l_temp > 0:
                            future_losses.append(l_temp)
                if future_losses:
                    momentum_after_blunder.append(sum(future_losses) / len(future_losses))

        else:
            opp_total_moves += 1
            if loss > 0:
                opp_total_loss += loss
            if loss > BLUNDER_THRESHOLD and abs(eval_before) < 1000:
                opp_blunders_count += 1

    for b in blunders:
        ply = b["ply"]
        try:
            pos = our_move_indices.index(ply)
        except ValueError:
            continue
        if pos + 1 >= len(our_move_indices):
            continue
        next_ply = our_move_indices[pos + 1]
        if next_ply < len(clocks) and next_ply >= 2:
            curr_clock = clocks[next_ply]
            prev_clock = clocks[next_ply - 2]
            if prev_clock is not None and curr_clock is not None and prev_clock > curr_clock:
                b["next_move_time"] = round(prev_clock - curr_clock, 1)

    for idx in range(len(blunders) - 1):
        if blunders[idx + 1]["move_num"] - blunders[idx]["move_num"] <= 5:
            blunders[idx]["is_next_move_blunder"] = True

    is_lag = False
    if reason in ("просрочка", "отключение") and not won:
        if reason == "просрочка":
            timeout_at_move = last_move_num
            our_idx = (list(range(0, len(clocks), 2)) if player_is_white else list(range(1, len(clocks), 2)))
            if our_idx:
                timeout_with_clock = clocks[our_idx[-1]]
                if timeout_with_clock is not None and timeout_with_clock > 10.0:
                    is_lag = True
        else:
            is_lag = True

    flag_result = None
    my_clock_at_timeout = None
    opp_clock_at_timeout = None

    if reason == "просрочка":
        if draw:
            flag_result = "draw"
        elif won:
            flag_result = "win"
        else:
            flag_result = "loss"

        for idx, c in enumerate(clocks):
            if c is not None:
                is_white_idx = (idx % 2 == 0)
                if is_white_idx == player_is_white:
                    my_clock_at_timeout = c
                else:
                    opp_clock_at_timeout = c

    # §32: Считаем ACPL ТОЛЬКО по нормальным ходам (не берсерк)
    # Если нормальных ходов 0, ставим 0
    acpl = total_loss / (our_moves - moves_berserk) if (our_moves - moves_berserk) > 0 else 0
    acpl_berserk = loss_berserk / moves_berserk if moves_berserk > 0 else 0
    accuracy = calculate_accuracy(acpl) if (our_moves - moves_berserk) > 0 else 0.0
    
    acpl_opponent_total = opp_total_loss / opp_total_moves if opp_total_moves > 0 else 0
    accuracy_opponent = calculate_accuracy(acpl_opponent_total) if opp_total_moves > 0 else 0.0

    end_berserk = False
    if len(clocks) >= 2:
        if any(t < BERSERK_TIME for t in clocks[-2:]):
            end_berserk = True

    game_length = len(moves)
    if berserk_move_enter is not None:
        berserk_moves_count = game_length - berserk_move_enter + 1
        is_true_berserk = (berserk_moves_count >= TRUE_BERSERK_MIN_MOVES)
    else:
        berserk_moves_count = 0
        is_true_berserk = False

    eval_final = (eval_after if player_is_white else -eval_after) if moves else 0
    max_eval_advantage = max(eval_history_peak) if eval_history_peak else 0
    min_eval_advantage = min(eval_history_peak) if eval_history_peak else 0
    
    acpl_op = loss_op / moves_op if moves_op > 0 else 0
    acpl_mid = loss_mid / moves_mid if moves_mid > 0 else 0
    acpl_end = loss_end / moves_end if moves_end > 0 else 0
    
    avg_momentum = sum(momentum_after_blunder) / len(momentum_after_blunder) if momentum_after_blunder else 0

    try:
        opp_style = classify_opponent_style(pgn, player_is_white)
    except Exception:
        opp_style = "unknown"

    return {
        "url": game_data.get("url", ""),
        "white": game.headers.get("White", "?"),
        "black": game.headers.get("Black", "?"),
        "acpl": acpl, "acpl_normal": acpl, "acpl_berserk": acpl_berserk,
        "acpl_opening": acpl_op, "acpl_middlegame": acpl_mid, "acpl_endgame": acpl_end,
        "accuracy": accuracy, "moves_normal": our_moves - moves_berserk, "moves_berserk": moves_berserk,
        "acpl_opponent_normal": acpl_opponent_total,
        "acpl_opponent_total": acpl_opponent_total,
        "accuracy_opponent": accuracy_opponent,
        "opp_blunders_total": opp_blunders_count,
        "game_length": game_length,
        "won": won, "draw": draw, "reason": reason,
        "end_berserk": end_berserk, "blunders": blunders,
        "eval_final": eval_final,
        "max_eval_advantage": max_eval_advantage,
        "min_eval_advantage": min_eval_advantage,
        "berserk_move_enter": berserk_move_enter,
        "berserk_moves_count": berserk_moves_count,
        "is_true_berserk": is_true_berserk,
        "opening": opening, "eco": eco,
        "time_thresholds_version": TIME_THRESHOLDS_VERSION,
        "opponent_rating": opponent_rating, "my_rating": my_rating,
        "opponent_username": opp_username,
        "is_cheater": is_cheater, "is_lag": is_lag,
        "end_time": game_data.get("end_time", 0),
        "depth": DEPTH,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "timeout_at_move": timeout_at_move,
        "timeout_with_clock": timeout_with_clock,
        "eval_after_opening": eval_after_opening,
        "moves_in_winning_position": moves_in_winning_position,
        "momentum_after_blunder": avg_momentum,
        "opening_line": " ".join(opening_line),
        "pgn": pgn,
        "clocks": clocks,
        "eval_history": eval_history,
        "critical_moments": critical_moments,
        "time_control": time_control,
        "flag_result": flag_result,
        "my_clock_at_timeout": my_clock_at_timeout,
        "opp_clock_at_timeout": opp_clock_at_timeout,
        "opp_style": opp_style,
    }