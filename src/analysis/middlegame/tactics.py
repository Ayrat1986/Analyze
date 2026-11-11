# ============================================================
# analysis/middlegame/tactics.py (v19.0)
# ============================================================
import io
from collections import defaultdict, Counter
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

def report_tactical_motifs():
    conn = _conn()
    cur = conn.cursor()
    base = get_base_filter()

    cur.execute(f"""
        SELECT b.game_url, b.move_num
        FROM blunders b JOIN games g ON g.url=b.game_url
        WHERE {base} AND b.is_berserk=0 AND b.is_instant=0
          AND b.is_my_blunder=1 AND b.loss_cp > 200
          AND b.move_num BETWEEN 11 AND 30
    """)
    blunders = cur.fetchall()
    by_url = defaultdict(list)
    for url, mn in blunders: by_url[url].append(mn)

    cur.execute(f"SELECT url, pgn, white FROM games WHERE {base} AND pgn IS NOT NULL AND pgn != ''")
    games = cur.fetchall()

    motifs = Counter()
    analyzed = failed = 0

    for url, pgn, white in games:
        if url not in by_url: continue
        game = _open_game(pgn)
        if not game:
            failed += 1
            continue
        player_is_white = ((white or "").lower() == PLAYER.lower())
        board = game.board()
        target_moves = set(by_url[url])

        for node in game.mainline():
            move = node.move
            is_white = board.turn
            is_mine = (is_white == player_is_white)
            current_move_num = board.fullmove_number

            if current_move_num in target_moves and is_mine:
                piece = board.piece_at(move.from_square)
                if piece:
                    after = board.copy()
                    after.push(move)
                    targets = after.attacks(move.to_square)
                    heavy = minor = 0
                    for t in targets:
                        tgt = after.piece_at(t)
                        if tgt and tgt.color != piece.color:
                            if tgt.piece_type in (chess.QUEEN, chess.ROOK, chess.KING): heavy += 1
                            elif tgt.piece_type in (chess.KNIGHT, chess.BISHOP): minor += 1
                    if heavy >= 1: motifs["fork_heavy"] += 1
                    elif minor >= 2: motifs["fork_minor"] += 1
                    if after.is_check(): motifs["check"] += 1
            board.push(move)
        analyzed += 1

    with report_context("tactical_motifs") as w:
        w.w_separator(title="TACTICAL MOTIFS (миттельшпиль)")
        w.w(f"Партий: {analyzed}, битых PGN: {failed}")
        w.w()

        if not motifs:
            w.w("⚠️ Мотивы не найдены")
        else:
            w.w("📊 РАСПРЕДЕЛЕНИЕ:")
            for m, c in motifs.most_common(10):
                w.w(f"  {m:<20} {c:>4}")
            w.w()

            top = motifs.most_common(1)[0][0]
            recs = {
                "fork_heavy": "Тренируй вилки на ферзя/ладью/короля.",
                "fork_minor": "Тренируй вилки на коня/слона.",
                "check": "Проверяй: 'есть ли у соперника шах?'",
            }
            w.w(f"🎯 ГЛАВНОЕ: {top}")
            w.w(f"  → {recs.get(top, 'Тренируй тактику.')}")

    conn.close()