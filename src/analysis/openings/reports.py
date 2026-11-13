# ============================================================
# analysis/openings/reports.py (v25.0)
# §28: удалены report_openings, openings_winrate_trend,
#      opening_performance, weak_spots_matrix, rating_by_opening.
# Оставлена только report_repertoire.
# ============================================================
import os
import sys
import sqlite3
from collections import defaultdict

import _common
from analysis.common import report_context

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import REPORTS_DIR, PLAYER

DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")


def _conn():
    return sqlite3.connect(DB_FILE)


def report_repertoire():
    conn = _conn(); cur = conn.cursor()
    cur.execute("""
        SELECT white, won, eco, opening_line FROM games
        WHERE is_lag=0 AND is_cheater=0 AND opening_line != ''
    """)
    rows = cur.fetchall()

    by_color = {"white": defaultdict(lambda: {"n": 0, "w": 0}),
                "black": defaultdict(lambda: {"n": 0, "w": 0})}
    lines = {"white": defaultdict(lambda: {"n": 0, "w": 0}),
             "black": defaultdict(lambda: {"n": 0, "w": 0})}

    for white, won, eco, ol in rows:
        piw = (white.lower() == PLAYER.lower())
        color = "white" if piw else "black"
        eco3 = (eco or "?")[:3]
        by_color[color][eco3]["n"] += 1
        if won:
            by_color[color][eco3]["w"] += 1
        parts = ol.split()[:6]
        if len(parts) >= 4:
            key = " ".join(parts)
            lines[color][key]["n"] += 1
            if won:
                lines[color][key]["w"] += 1

    with report_context("opening_repertoire") as w:
        w.w_separator(title="OPENING REPERTOIRE")
        w.w(f"Всего партий: {len(rows)}")
        w.w()
        for color in ["white", "black"]:
            label = "ЗА БЕЛЫХ" if color == "white" else "ЗА ЧЁРНЫХ"
            w.w(f"♟️ {label}:")
            w.w(f"  {'ECO':<6} {'Партий':<8} {'Побед':<8} {'Win%':<8}")
            for eco3, d in sorted(by_color[color].items(), key=lambda x: -x[1]["n"])[:10]:
                if d["n"] >= 3:
                    w.w(f"  {eco3:<6} {d['n']:<8} {d['w']:<8} {d['w']/d['n']*100:<8.1f}")
            w.w()
            w.w("  🔝 ТОП-5 ЛИНИЙ:")
            for ln, d in sorted(lines[color].items(), key=lambda x: -x[1]["n"])[:5]:
                if d["n"] >= 3:
                    w.w(f"    {ln:<30} {d['n']}п, {d['w']/d['n']*100:.0f}%")
            w.w()
    conn.close()