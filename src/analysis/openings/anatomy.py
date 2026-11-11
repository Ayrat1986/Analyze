# ============================================================
# analysis/openings/anatomy.py — Анатомия дебютов (v19.0)
# ============================================================
import os
import sys
import sqlite3
from collections import defaultdict

import _common
from analysis.common import report_context

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import REPORTS_DIR, PLAYER, _uci_to_san

DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")


def _format_san_with_moves(san_str: str) -> str:
    """Добавляет нумерацию ходов к SAN-строке (1. d4 d5 2. c4 e6)."""
    if not san_str:
        return ""
    parts = san_str.split()
    result = []
    move_num = 1
    for i, move in enumerate(parts):
        if i % 2 == 0:
            result.append(f"{move_num}. {move}")
            move_num += 1
        else:
            result.append(move)
    return " ".join(result)


def report_line_anatomy():
    conn = sqlite3.connect(DB_FILE); cur = conn.cursor()

    cur.execute("""
        SELECT opening, opening_line, won, draw, acpl, acpl_middlegame, opp_rating
        FROM games
        WHERE is_lag=0 AND is_cheater=0 AND opening_line IS NOT NULL AND opening_line != ''
    """)
    rows = cur.fetchall()

    with report_context("line_anatomy") as w:
        w.w_separator(title="АНАТОМИЯ ДЕБЮТОВ ПО ЛИНИЯМ (топ-6 ходов)")
        
        if not rows:
            w.w("⚠️ Нет данных opening_line.")
            conn.close()
            return

        # Группируем по первым 6 ходам (12 полуходов)
        lines = defaultdict(lambda: {
            "opening": "", "n": 0, "w": 0, "d": 0,
            "acpl_sum": 0, "acpl_mid_sum": 0, "opp_sum": 0, "full_line": ""
        })
        
        for opening, line, won, draw, acpl, acpl_mid, opp_rating in rows:
            parts = line.split()
            if len(parts) < 4:
                continue
            key = " ".join(parts[:12])
            d = lines[key]
            d["opening"] = opening or "Unknown"
            d["full_line"] = line
            d["n"] += 1
            if won: d["w"] += 1
            if draw: d["d"] += 1
            d["acpl_sum"] += acpl or 0
            d["acpl_mid_sum"] += acpl_mid or 0
            d["opp_sum"] += opp_rating or 0

        filtered = []
        for key, d in lines.items():
            if d["n"] >= 3:
                winrate = (d["w"] + 0.5 * d["d"]) / d["n"] * 100
                perf = (d["opp_sum"] / d["n"]) + (winrate / 100 - 0.5) * 800
                filtered.append({
                    "opening": d["opening"], "line": d["full_line"], "n": d["n"],
                    "winrate": winrate, "acpl": d["acpl_sum"] / d["n"],
                    "acpl_mid": d["acpl_mid_sum"] / d["n"], "perf": perf,
                })

        if not filtered:
            w.w("⚠️ Нет линий с n >= 3 даже после группировки.")
            conn.close()
            return

        best = sorted([l for l in filtered if l["winrate"] >= 60 and l["n"] >= 5], key=lambda x: -x["winrate"])[:10]
        worst = sorted([l for l in filtered if l["winrate"] <= 40 and l["n"] >= 5], key=lambda x: x["winrate"])[:10]

        w.w(f"Всего линий (n >= 3): {len(filtered)}")
        w.w()

        if best:
            w.w("📈 ЛИНИИ-КОЗЫРИ (winrate >= 60%, n >= 5):")
            for l in best:
                san = _uci_to_san(l["line"])
                san_fmt = _format_san_with_moves(san)
                w.w(f"  {l['opening'][:35]:<37} | {l['n']}п, {l['winrate']:.0f}%, ACPL {l['acpl']:.0f}")
                w.w(f"    └─ {san_fmt[:75]}...")
                w.w()
        else:
            w.w("  ⚠️ Нет линий с winrate >= 60% и n >= 5.")
            w.w()

        if worst:
            w.w("📉 ЛИНИИ-УБИЙЦЫ (winrate <= 40%, n >= 5):")
            for l in worst:
                san = _uci_to_san(l["line"])
                san_fmt = _format_san_with_moves(san)
                w.w(f"  {l['opening'][:35]:<37} | {l['n']}п, {l['winrate']:.0f}%, ACPL {l['acpl']:.0f}")
                w.w(f"    └─ {san_fmt[:75]}...")
                w.w()
        else:
            w.w("  ⚠️ Нет линий с winrate <= 40% и n >= 5.")
            w.w()

    conn.close()