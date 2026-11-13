# ============================================================
# analysis/openings/common.py (v25.0)
# §28: удалены _openings_csv и AI_LATEST (использовались только
#      report_openings). Оставлены _uci_to_san и PLAYER.
# ============================================================
import chess
import _common

REPORTS_DIR = str(_common.REPORTS_DIR)
PLAYER = _common.CONFIG.get("player", "")


def _uci_to_san(uci_line, max_moves=20):
    if not uci_line:
        return uci_line or "?"
    try:
        b = chess.Board()
        san_parts = []
        for u in uci_line.split()[:max_moves]:
            try:
                move = chess.Move.from_uci(u)
                san_parts.append(b.san(move))
                b.push(move)
            except Exception:
                break
        return " ".join(san_parts) if san_parts else uci_line
    except Exception:
        return uci_line