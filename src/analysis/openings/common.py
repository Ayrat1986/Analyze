import os
import csv
import chess
import _common

REPORTS_DIR = str(_common.REPORTS_DIR)
AI_LATEST = os.path.join(REPORTS_DIR, "ai_export", "latest")
PLAYER = _common.CONFIG.get("player", "")

def _openings_csv():
    path = os.path.join(AI_LATEST, "openings_stats.csv")
    if not os.path.exists(path):
        return None
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                rows.append({
                    "opening": r.get("opening", "?"),
                    "eco": r.get("eco", "?"),
                    "games": int(r.get("games", 0)),
                    "wins": int(r.get("wins", 0)),
                    "win_rate": float(str(r.get("win_rate", "0")).replace("%", "")),
                    "acpl": float(r.get("acpl", 0) or 0),
                    "opp_acpl": float(r.get("opp_acpl", 0) or 0),
                    "eval_after_opening": float(r.get("eval_after_opening", 0) or 0),
                })
            except (ValueError, TypeError):
                continue
    return rows

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