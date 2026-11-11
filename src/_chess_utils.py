# src/_chess_utils.py
"""Общие утилиты для работы с шахматными данными (PGN, clocks, стиль)."""
import io
import re
import json
from collections import defaultdict


def parse_clock(pgn):
    """Извлекает шахматные часы из PGN."""
    clocks = re.findall(r'\[%clk (\d+):(\d+):(\d+\.?\d*)\]', pgn)
    if clocks:
        return [int(h) * 3600 + int(m) * 60 + float(s) for h, m, s in clocks]
    clocks = re.findall(r'\[%clk (\d+):(\d+\.?\d*)\]', pgn)
    if clocks:
        return [int(m) * 60 + float(s) for m, s in clocks]
    return []


def get_opponent_rating(game_data, player):
    white, black = game_data.get("white", {}), game_data.get("black", {})
    return black.get("rating", 0) if white.get("username") == player else white.get("rating", 0)


def get_my_rating(game_data, player):
    white, black = game_data.get("white", {}), game_data.get("black", {})
    return white.get("rating", 0) if white.get("username") == player else black.get("rating", 0)


def get_opponent_username(game_data, player):
    white, black = game_data.get("white", {}), game_data.get("black", {})
    return black.get("username", "?").lower() if white.get("username") == player else white.get("username", "?").lower()


def classify_opponent_style(pgn, player_is_white):
    """Стиль соперника по PGN: aggressive / tactical / positional / universal / unknown."""
    import chess, chess.pgn
    game = chess.pgn.read_game(io.StringIO(pgn))
    if not game:
        return "unknown"
    checks = captures = moves_count = 0
    board = game.board()
    for node in game.mainline():
        is_opp_move = (board.turn and not player_is_white) or (not board.turn and player_is_white)
        if is_opp_move:
            moves_count += 1
            if board.is_capture(node.move):
                captures += 1
            board.push(node.move)
            if board.is_check():
                checks += 1
        else:
            board.push(node.move)
    if moves_count == 0:
        return "unknown"
    cr = checks / moves_count
    capr = captures / moves_count
    if cr > 0.15:
        return "aggressive"
    if capr > 0.3:
        return "tactical"
    if cr < 0.05 and capr < 0.2:
        return "positional"
    return "universal"


def build_opponent_style_map(conn, player):
    """{opp_username: style} по всем соперникам в БД."""
    import chess, chess.pgn
    cur = conn.cursor()
    cur.execute("""
        SELECT white, black, pgn, opp_username FROM games
        WHERE is_lag=0 AND is_cheater=0
          AND pgn IS NOT NULL AND pgn != ''
          AND opp_username IS NOT NULL
    """)
    opp_stats = defaultdict(lambda: {"checks": 0, "captures": 0, "moves": 0})
    for white, black, pgn, opp in cur.fetchall():
        if not opp:
            continue
        try:
            game = chess.pgn.read_game(io.StringIO(pgn))
            if not game:
                continue
            player_is_white = (white or "").lower() == player.lower()
            board = game.board()
            for node in game.mainline():
                is_opp_move = (board.turn and not player_is_white) or (not board.turn and player_is_white)
                if is_opp_move:
                    s = opp_stats[opp]
                    s["moves"] += 1
                    if board.is_capture(node.move):
                        s["captures"] += 1
                    board.push(node.move)
                    if board.is_check():
                        s["checks"] += 1
                else:
                    board.push(node.move)
        except Exception:
            continue
    result = {}
    for opp, s in opp_stats.items():
        if s["moves"] == 0:
            result[opp] = "unknown"
            continue
        cr = s["checks"] / s["moves"]
        capr = s["captures"] / s["moves"]
        if cr > 0.15:
            result[opp] = "aggressive"
        elif capr > 0.3:
            result[opp] = "tactical"
        elif cr < 0.05 and capr < 0.2:
            result[opp] = "positional"
        else:
            result[opp] = "universal"
    return result


# ============================================================
# ЧИТЕРЫ
# ============================================================
_HARDCODED_CHEATERS = [
    "rohith-p", "pandathewhiteghost11", "badboy_zx", "pollosman410",
    "genadeterminism", "chessminator_ccg", "nidohorsey",
    "red_crystal_castles", "zephyrfinal", "hakuowl", "xx1027", "gm_gbc",
    "shanghai67", "rottveil", "n0nex1stence", "bibenbiallahbiliyo",
    "hasanoov1994", "sheraya_11", "mothersegg",
]


def load_known_cheaters() -> list:
    import os
    import _common
    path = str(_common.BASE_DIR / "data" / "cheaters.txt")
    if not os.path.exists(path):
        return list(_HARDCODED_CHEATERS)
    result = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.split("#")[0].strip().lower()
            if not s:
                continue
            if s.startswith("=") or "найденные" in s or "читеров не" in s:
                continue
            result.append(s)
    return result or list(_HARDCODED_CHEATERS)


# ============================================================
# НОВЫЕ ХЕЛПЕРЫ (ДЛЯ КОНСИСТЕНТНОСТИ)
# ============================================================
def rating_cat(r):
    """
    Рейтинговый бакет. ДЕЛЕГИРУЕТ в analysis.common.rating_bucket().
    Fallback — если analysis.common недоступен.
    """
    try:
        from analysis.common import rating_bucket
        return rating_bucket(r)
    except Exception:
        if not r or r == 0:
            return "unknown"
        if r < 2400: return "< 2400"
        if r < 2500: return "2400-2499"
        if r < 2600: return "2500-2599"
        if r < 2700: return "2600-2699"
        if r < 2800: return "2700-2799"
        return "2800+"


def load_clocks_evals(clocks_raw, evals_raw):
    """Безопасный парсинг clocks и eval_history из БД."""
    try:
        clocks = json.loads(clocks_raw) if clocks_raw else []
        evals = json.loads(evals_raw) if evals_raw else []
        return clocks, evals
    except Exception:
        return [], []


def is_player_white(white: str, player: str) -> bool:
    """True если player играл белыми в этой партии."""
    return (white or "").lower() == (player or "").lower()


def parse_time_spent(clocks, player_is_white, max_diff_sec=120.0, first_base=60.0):
    """
    Возвращает список времени, потраченного на каждый свой ход.
    Игнорирует аномалии (отрицательные или > max_diff_sec).
    """
    if not clocks:
        return []
    our_idx = list(range(0, len(clocks), 2)) if player_is_white else list(range(1, len(clocks), 2))
    times = []
    if our_idx:
        first_c = clocks[our_idx[0]]
        first_diff = first_base - first_c
        if 0 < first_diff < max_diff_sec:
            times.append(first_diff)
    for i in range(1, len(our_idx)):
        prev_c = clocks[our_idx[i - 1]]
        curr_c = clocks[our_idx[i]]
        diff = prev_c - curr_c
        if 0 < diff < max_diff_sec:
            times.append(diff)
    return times


def get_clock_at_move(clocks, player_is_white, move_num):
    """Остаток времени игрока ПЕРЕД его move_num-м ходом (1-based)."""
    if not clocks:
        return None
    our_idx = list(range(0, len(clocks), 2)) if player_is_white else list(range(1, len(clocks), 2))
    if move_num - 1 < len(our_idx):
        idx = our_idx[move_num - 1]
        if idx > 0:
            return clocks[idx - 1]
        return None
    return None