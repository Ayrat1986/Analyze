# ============================================================
# analysis/middlegame/positional_weaknesses.py (v19.0)
# ============================================================
import io
import os
import json
import chess
import chess.pgn
from analysis.common import report_context
from .common import _conn, get_base_filter, REPORTS_DIR, PLAYER

def _open_game(pgn):
    if not pgn: return None
    try:
        return chess.pgn.read_game(io.StringIO(pgn))
    except Exception:
        return None

def _analyze_positional(game, my_color):
    board = game.board()
    has_isolated = has_doubled = False
    castled_move = None
    exposed_at_30 = uncastled_at_30 = False
    player_is_white = (my_color == chess.WHITE)
    castling_targets = {chess.G1, chess.C1} if player_is_white else {chess.G8, chess.C8}

    for node in game.mainline():
        move = node.move
        is_mine = (board.turn == my_color)
        fullmove = board.fullmove_number

        if is_mine and fullmove <= 12 and board.is_castling(move):
            if castled_move is None: castled_move = fullmove

        if fullmove == 20:
            for file_idx in range(8):
                fmask = chess.BB_FILES[file_idx]
                my_pawns_here = board.pieces(chess.PAWN, my_color) & fmask
                if my_pawns_here:
                    left = (chess.BB_FILES[file_idx - 1]) if file_idx > 0 else 0
                    right = (chess.BB_FILES[file_idx + 1]) if file_idx < 7 else 0
                    has_left = left and (board.pieces(chess.PAWN, my_color) & left)
                    has_right = right and (board.pieces(chess.PAWN, my_color) & right)
                    if not has_left and not has_right: has_isolated = True
                if len(board.pieces(chess.PAWN, my_color) & fmask) >= 2: has_doubled = True

        if 28 <= fullmove <= 32 and is_mine:
            ks = board.king(my_color)
            if ks is not None:
                if ks in (chess.E1, chess.E8): uncastled_at_30 = True
                elif ks not in castling_targets: exposed_at_30 = True
        board.push(move)

    return {
        "pawn_isolated": has_isolated, "pawn_doubled": has_doubled,
        "castled_move": castled_move, "exposed_at_30": exposed_at_30, "uncastled_at_30": uncastled_at_30,
    }

def report_positional_weaknesses():
    conn = _conn()
    cur = conn.cursor()
    base = get_base_filter()

    cur.execute(f"SELECT url, white, won, pgn, acpl_middlegame FROM games WHERE {base} AND pgn IS NOT NULL AND pgn != ''")
    rows = cur.fetchall()

    pawn_stats = {"isolated": {"n": 0, "acpl_sum": 0}, "doubled": {"n": 0, "acpl_sum": 0}, "none": {"n": 0, "acpl_sum": 0}}
    king_stats = {
        "early": {"n": 0, "acpl_sum": 0, "wins": 0}, "late": {"n": 0, "acpl_sum": 0, "wins": 0},
        "none": {"n": 0, "acpl_sum": 0, "wins": 0}, "exposed": {"n": 0, "acpl_sum": 0, "wins": 0},
        "uncastled": {"n": 0, "acpl_sum": 0, "wins": 0},
    }
    total_games = 0

    for url, white, won, pgn, acpl_mid in rows:
        game = _open_game(pgn)
        if not game: continue
        my_color = chess.WHITE if (white or "").lower() == PLAYER.lower() else chess.BLACK
        res = _analyze_positional(game, my_color)
        if not res: continue
        total_games += 1
        acpl_mid = acpl_mid or 0

        if res["pawn_isolated"]:
            pawn_stats["isolated"]["n"] += 1; pawn_stats["isolated"]["acpl_sum"] += acpl_mid
        elif res["pawn_doubled"]:
            pawn_stats["doubled"]["n"] += 1; pawn_stats["doubled"]["acpl_sum"] += acpl_mid
        else:
            pawn_stats["none"]["n"] += 1; pawn_stats["none"]["acpl_sum"] += acpl_mid

        cm = res["castled_move"]
        key = "early" if (cm is not None and cm <= 12) else ("late" if cm is not None else "none")
        king_stats[key]["n"] += 1; king_stats[key]["acpl_sum"] += acpl_mid
        if won: king_stats[key]["wins"] += 1

        if res["exposed_at_30"]:
            king_stats["exposed"]["n"] += 1; king_stats["exposed"]["acpl_sum"] += acpl_mid
            if won: king_stats["exposed"]["wins"] += 1
        if res["uncastled_at_30"]:
            king_stats["uncastled"]["n"] += 1; king_stats["uncastled"]["acpl_sum"] += acpl_mid
            if won: king_stats["uncastled"]["wins"] += 1

    with report_context("positional_weaknesses") as w:
        w.w_separator(title="ПОЗИЦИОННЫЕ СЛАБОСТИ (миттельшпиль)")
        w.w(f"Всего проанализировано: {total_games}")
        w.w()

        w.w("📊 СЕКЦИЯ 1: СТРУКТУРА ПЕШЕК (ход 20)")
        total_p = sum(d["n"] for d in pawn_stats.values()) or 1
        for k, label in [("isolated", "Изолированная пешка"), ("doubled", "Сдвоенные пешки"), ("none", "Без слабостей")]:
            d = pawn_stats[k]
            if d["n"] > 0:
                w.w(f"  {label:<25}: {d['n']:>4} ({d['n']/total_p*100:>4.1f}%), ACPL {d['acpl_sum']/d['n']:>4.0f}")
        w.w()

        w.w("📊 СЕКЦИЯ 2: БЕЗОПАСНОСТЬ КОРОЛЯ")
        for k, label in [("early", "Ранняя рокировка (до 12)"), ("late", "Поздняя рокировка"), ("none", "Без рокировки")]:
            d = king_stats[k]
            if d["n"] > 0:
                w.w(f"  {label:<30}: {d['n']:>4} партий, ACPL {d['acpl_sum']/d['n']:>4.0f}, винрейт {d['wins']/d['n']*100:>5.1f}%")
        for k, label in [("uncastled", "Не рокирован к 28"), ("exposed", "Ушёл/опасно")]:
            d = king_stats[k]
            if d["n"] > 0:
                w.w(f"\n  {label:<30}: {d['n']} партий, ACPL {d['acpl_sum']/d['n']:.0f}, винрейт {d['wins']/d['n']*100:.1f}%")
        w.w()

        w.w("🎯 ВЕРДИКТ:")
        if pawn_stats["isolated"]["n"] > 0 and pawn_stats["none"]["n"] > 0:
            a_iso = pawn_stats["isolated"]["acpl_sum"] / pawn_stats["isolated"]["n"]
            a_none = pawn_stats["none"]["acpl_sum"] / pawn_stats["none"]["n"]
            if a_iso > a_none + 5: w.w(f"  ⚠️ Изолированная пешка → ACPL +{a_iso - a_none:.0f} CP. Избегай.")
        if king_stats["none"]["n"] > 0 and king_stats["late"]["n"] > 0:
            a_none = king_stats["none"]["acpl_sum"] / king_stats["none"]["n"]
            a_late = king_stats["late"]["acpl_sum"] / king_stats["late"]["n"]
            if a_none > a_late + 10: w.w(f"  ⚠️ Без рокировки → ACPL +{a_none - a_late:.0f} CP. Рокируйся.")

    # metrics.json
    try:
        metrics_path = os.path.join(REPORTS_DIR, "metrics.json")
        open_king_n = king_stats["exposed"]["n"] + king_stats["uncastled"]["n"]
        open_king_pct = (open_king_n / total_games * 100) if total_games else None
        iso_n = pawn_stats["isolated"]["n"]
        iso_acpl = pawn_stats["isolated"]["acpl_sum"] / iso_n if iso_n else None
        with open(metrics_path, "w", encoding="utf-8") as mf:
            json.dump({"open_king_percent": open_king_pct, "isolated_pawn_acpl": iso_acpl}, mf)
        print("  📝 metrics.json обновлён для codex_coach")
    except Exception as e:
        print(f"  ⚠️ Не удалось обновить metrics.json: {e}")

    conn.close()