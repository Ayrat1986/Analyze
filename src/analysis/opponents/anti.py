# ============================================================
# analysis/opponents/anti.py — v20.3 (Исправлен синтаксис)
# ============================================================
import os, io, json
import chess, chess.pgn
from .common import _conn, REPORTS_DIR, PLAYER
from _chess_utils import is_player_white as _is_player_white
from analysis.common import RATING_BUCKET_LABELS, rating_bucket

def report_anti_aggressor():
    conn = _conn(); cur = conn.cursor()
    path = os.path.join(REPORTS_DIR, "anti_aggressor.txt")

    # Берем стиль из БД
    cur.execute("""
        SELECT white, won, pgn, acpl_opening, acpl_middlegame, acpl_endgame, clocks, opp_rating, opp_style
        FROM games WHERE is_lag=0 AND is_cheater=0 AND pgn IS NOT NULL AND pgn != '' AND opp_style IS NOT NULL
    """)
    rows = cur.fetchall()

    def analyze_anti_agg(pgn, player_is_white):
        game = chess.pgn.read_game(io.StringIO(pgn))
        if not game: return None
        board = game.board()
        checks = captures = moves_count = 0
        castled_early = False
        queen_traded = False
        q_on = (len(board.pieces(chess.QUEEN, chess.WHITE)) + len(board.pieces(chess.QUEEN, chess.BLACK)))

        for node in game.mainline():
            is_white = board.turn
            is_mine = (is_white and player_is_white) or (not is_white and not player_is_white)
            move = node.move
            if is_mine and board.fullmove_number <= 12 and board.is_castling(move): castled_early = True
            if not is_mine:
                moves_count += 1
                if board.is_capture(move): captures += 1
                board.push(move)
                if board.is_check(): checks += 1
            else: board.push(move)
            if not queen_traded:
                new_q = (len(board.pieces(chess.QUEEN, chess.WHITE)) + len(board.pieces(chess.QUEEN, chess.BLACK)))
                if new_q < q_on: queen_traded = True

        if moves_count == 0: return None
        cr = checks / moves_count; capr = captures / moves_count
        style = "aggressive" if cr > 0.15 else ("tactical" if capr > 0.3 else ("positional" if (cr < 0.05 and capr < 0.2) else "universal"))
        return style, castled_early, queen_traded

    rating_ranges = RATING_BUCKET_LABELS
    stats = {style: {rng: {"n": 0, "w": 0, "c_w": 0, "c_n": 0, "nc_w": 0, "nc_n": 0, "qt_w": 0, "qt_n": 0, "nqt_w": 0, "nqt_n": 0, "op": 0, "mid": 0, "end": 0, "time": 0, "moves": 0} for rng in rating_ranges} for style in ["aggressive", "tactical"]}
    all_stats = {"time": 0, "moves": 0}

    # ИСПРАВЛЕНИЕ: Переменная называется opp_style_from_db
    for white, won, pgn, op, mid, end, clocks_raw, opp_rating, opp_style_from_db in rows:
        if opp_style_from_db not in ("aggressive", "tactical"): continue
        player_is_white = _is_player_white(white, PLAYER)
        res = analyze_anti_agg(pgn, player_is_white)
        if not res: continue
        _, castled_early, queen_traded = res

        rng = rating_bucket(opp_rating)
        if rng not in rating_ranges: continue

        time_spent = 0; my_moves = 0
        if clocks_raw:
            try:
                clocks = json.loads(clocks_raw)
                our_idx = (list(range(0, len(clocks), 2)) if player_is_white else list(range(1, len(clocks), 2)))
                prev = 60.0
                for idx in our_idx:
                    curr = clocks[idx]; diff = prev - curr
                    if 0 < diff < 60: time_spent += diff; my_moves += 1
                    prev = clocks[max(0, idx-1)] if idx > 0 else 60.0
            except Exception: pass
        all_stats["time"] += time_spent; all_stats["moves"] += my_moves

        st = stats[opp_style_from_db][rng]
        st["n"] += 1
        if won: st["w"] += 1
        if castled_early: st["c_n"] += 1; st["c_w"] += (1 if won else 0)
        else: st["nc_n"] += 1; st["nc_w"] += (1 if won else 0)
        if queen_traded: st["qt_n"] += 1; st["qt_w"] += (1 if won else 0)
        else: st["nqt_n"] += 1; st["nqt_w"] += (1 if won else 0)
        st["op"] += (op or 0); st["mid"] += (mid or 0); st["end"] += (end or 0)
        st["time"] += time_spent; st["moves"] += my_moves

    with open(path, "w", encoding="utf-8") as f:
        def w(line=""): print(line); f.write(line + "\n")
        w("=" * 60); w(" 🛡️ АНТИ-АГРЕССОР: ГЛУБОКИЙ РАЗБОР СЛАБОСТЕЙ"); w("=" * 60)
        w("Как ты играешь против 'aggressive' и 'tactical' стилей по рейтингам.\n")

        avg_time_all = all_stats["time"] / all_stats["moves"] if all_stats["moves"] else 0

        for style in ["aggressive", "tactical"]:
            w(f"🎯 СТИЛЬ: {style.upper()}")
            for rng in rating_ranges:
                st = stats[style][rng]
                if st["n"] < 3: continue
                w(f"\n  📊 Рейтинг: {rng} ({st['n']} партий, винрейт {st['w']/st['n']*100:.1f}%)")
                wr_c = st["c_w"] / st["c_n"] * 100 if st["c_n"] else 0
                wr_nc = st["nc_w"] / st["nc_n"] * 100 if st["nc_n"] else 0
                w(f"    1. Рокировка до 12: с рокировкой {wr_c:.1f}% ({st['c_n']}п), без {wr_nc:.1f}% ({st['nc_n']}п)")
                if wr_c > wr_nc + 10: w("       ✅ Рокировка помогает!")

                wr_qt = st["qt_w"] / st["qt_n"] * 100 if st["qt_n"] else 0
                wr_nqt = st["nqt_w"] / st["nqt_n"] * 100 if st["nqt_n"] else 0
                w(f"    2. Размен ферзей: разменяны {wr_qt:.1f}% ({st['qt_n']}п), нет {wr_nqt:.1f}% ({st['nqt_n']}п)")
                if wr_qt > wr_nqt + 10: w("       ✅ Размен ферзей помогает!")

                w(f"    3. ACPL: дебют {st['op']/st['n']:.1f}, мит {st['mid']/st['n']:.1f}, энд {st['end']/st['n']:.1f}")
                avg_time = st["time"] / st["moves"] if st["moves"] else 0
                w(f"    4. Время на ход: {avg_time:.2f} сек (в среднем {avg_time_all:.2f})")
                if avg_time > avg_time_all * 1.2: w("       ⚠️ Ты тратишь слишком много времени, попадая в цейтнот.")
            w("\n" + "-" * 60 + "\n")

    print(f"\n✅ {path}")