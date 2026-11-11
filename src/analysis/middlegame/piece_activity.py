# ============================================================
# analysis/middlegame/piece_activity.py (v19.0)
# ============================================================
import io
from collections import Counter
import chess
import chess.pgn
from analysis.common import report_context
from .common import _conn, get_base_filter, PLAYER

def _open_game(pgn):
    if not pgn: return None
    try:
        return chess.pgn.read_game(io.StringIO(pgn))
    except Exception:
        return None

def _starting_squares(color):
    return {chess.B1, chess.G1, chess.C1, chess.F1, chess.A1, chess.H1, chess.D1} if color == chess.WHITE else \
           {chess.B8, chess.G8, chess.C8, chess.F8, chess.A8, chess.H8, chess.D8}

def report_piece_activity():
    conn = _conn()
    cur = conn.cursor()
    base = get_base_filter()

    cur.execute(f"SELECT url, white, won, pgn, acpl_middlegame FROM games WHERE {base} AND pgn IS NOT NULL AND pgn != '' AND game_length >= 30")
    rows = cur.fetchall()

    buckets = {"0": {"n": 0, "wins": 0, "acpl_sum": 0}, "1": {"n": 0, "wins": 0, "acpl_sum": 0}, "2+": {"n": 0, "wins": 0, "acpl_sum": 0}}
    sleeping_pieces = Counter()
    total_analyzed = 0

    for url, white, won, pgn, acpl_mid in rows:
        game = _open_game(pgn)
        if not game: continue
        my_color = chess.WHITE if (white or "").lower() == PLAYER.lower() else chess.BLACK
        starting = _starting_squares(my_color)
        board = game.board()
        moved_from = set()
        for ply, node in enumerate(game.mainline()):
            if ply >= 40: break
            if board.turn == my_color and node.move.from_square in starting:
                moved_from.add(node.move.from_square)
            board.push(node.move)

        sleeping = 7 - len(moved_from)
        key = "0" if sleeping == 0 else ("1" if sleeping == 1 else "2+")
        buckets[key]["n"] += 1
        if won: buckets[key]["wins"] += 1
        buckets[key]["acpl_sum"] += (acpl_mid or 0)

        for sq in starting:
            if sq not in moved_from: sleeping_pieces[chess.square_name(sq)] += 1
        total_analyzed += 1

    with report_context("piece_activity") as w:
        w.w_separator(title="PIECE ACTIVITY: активность фигур к 20-му ходу")
        w.w("«Спящая» = фигура не ушла со стартовой позиции (Q, 2R, 2B, 2N).")
        w.w(f"Проанализировано партий: {total_analyzed}")
        w.w()

        w.w(f"  {'Спящих':<10} {'Партий':<8} {'Win%':<8} {'ACPL мит':<10}")
        w.w("  " + "-" * 40)
        for key in ["0", "1", "2+"]:
            d = buckets[key]
            if d["n"] > 0:
                w.w(f"  {key:<10} {d['n']:<8} {d['wins']/d['n']*100:<8.1f} {d['acpl_sum']/d['n']:<10.0f}")
        w.w()

        w.w("📊 ТОП-5 «СПЯЩИХ» КВАДРАТОВ:")
        for sq, cnt in sleeping_pieces.most_common(5):
            w.w(f"  {sq}: {cnt} партий ({(cnt/max(1,total_analyzed))*100:.1f}%)")
        w.w()

        w.w("🎯 ВЕРДИКТ:")
        wr_0 = buckets["0"]["wins"] / buckets["0"]["n"] * 100 if buckets["0"]["n"] else 0
        wr_2 = buckets["2+"]["wins"] / buckets["2+"]["n"] * 100 if buckets["2+"]["n"] else 0
        if wr_0 > 0 and wr_2 > 0:
            diff = wr_0 - wr_2
            if diff > 10:
                w.w(f"  ⚠️ {diff:.0f}% разницы winrate между «все активны» и «2+ спят».")
                w.w("  💡 Если ферзь/ладья не двигались к 20-му — активируй ДО миттельшпиля.")
            elif diff > 0: w.w(f"  ➡️ Активность даёт +{diff:.0f}% winrate. Не критично, но следи.")
            else: w.w("  ✅ Спящие фигуры не коррелируют с проигрышем. Не проблема.")
        else: w.w("  Недостаточно данных для сравнения.")
    conn.close()