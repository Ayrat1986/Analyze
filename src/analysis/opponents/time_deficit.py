# ============================================================
# analysis/opponents/time_deficit.py — v20.4 (opp_style из БД)
# ============================================================
import json
import os
import statistics
from collections import defaultdict
from .common import _conn, REPORTS_DIR, PLAYER
from _chess_utils import rating_cat, is_player_white, parse_time_spent
from analysis.common import RATING_BUCKET_LABELS


def get_clocks_before_move(clocks, player_is_white, move_num):
    if not clocks:
        return None, None
    my_ply = (move_num - 2) * 2 + (0 if player_is_white else 1)
    opp_ply = my_ply + 1
    my_clock = clocks[my_ply] if 0 <= my_ply < len(clocks) else None
    opp_clock = clocks[opp_ply] if 0 <= opp_ply < len(clocks) else None
    return my_clock, opp_clock


def report_style_time_deficit():
    conn = _conn()
    path = os.path.join(REPORTS_DIR, "style_time_deficit.txt")

    cur = conn.cursor()
    cur.execute("""
        SELECT url, white, black, won, draw, opp_rating, acpl, acpl_middlegame,
               eco, clocks, opp_style
        FROM games WHERE is_lag=0 AND is_cheater=0 AND clocks IS NOT NULL AND clocks != '[]'
          AND opp_style IS NOT NULL
    """)
    rows = cur.fetchall()
    conn.close()

    stats = defaultdict(lambda: defaultdict(lambda: {
        "games": 0, "wins": 0, "acpls": [], "times": [], "deficits": []
    }))
    deb_stats = defaultdict(lambda: defaultdict(lambda: {
        "games": 0, "wins": 0, "acpls": [], "deficits": []
    }))
    total_times = []

    for row in rows:
        url, white, black, won, draw, opp_rating, acpl, acpl_mid, eco, clocks_raw, style = row
        if not clocks_raw or not style:
            continue
        if style == "unknown":
            continue

        try:
            clocks = json.loads(clocks_raw)
        except Exception:
            continue
        if not clocks:
            continue

        player_is_white = is_player_white(white, PLAYER)
        r_cat = rating_cat(opp_rating)

        my_times = parse_time_spent(clocks, player_is_white)
        avg_time = statistics.mean(my_times) if my_times else 0
        total_times.extend(my_times)

        my_clock_30, opp_clock_30 = get_clocks_before_move(clocks, player_is_white, 30)
        deficit = (my_clock_30 - opp_clock_30) if (my_clock_30 is not None and opp_clock_30 is not None) else None

        s = stats[style][r_cat]
        s["games"] += 1
        if won:
            s["wins"] += 1
        s["acpls"].append(acpl or 0)
        s["times"].append(avg_time)
        if deficit is not None:
            s["deficits"].append(deficit)

        if style in ("aggressive", "tactical"):
            eco3 = (eco or "?")[:3]
            d = deb_stats[style][eco3]
            d["games"] += 1
            if won:
                d["wins"] += 1
            d["acpls"].append(acpl or 0)
            if deficit is not None:
                d["deficits"].append(deficit)

    with open(path, "w", encoding="utf-8") as f:
        def w(line=""):
            print(line)
            f.write(line + "\n")

        w("=" * 70)
        w(" 🎭 СТИЛЬ СОПЕРНИКА × ВРЕМЯ × ДЕФИЦИТ")
        w("=" * 70)
        if total_times:
            w(f"Среднее время на ход: {statistics.mean(total_times):.2f} сек")
            w(f"Медиана: {statistics.median(total_times):.2f} сек")
        w()

        rating_buckets = RATING_BUCKET_LABELS

        for style in ["aggressive", "tactical", "positional", "universal"]:
            if style not in stats:
                continue
            w(f"📊 Стиль: {style.upper()}")
            w(f"  {'Рейтинг':<12} {'Игр':<5} {'Win%':<7} {'ACPL':<6} {'Ср.время':<9} {'Ср.дефицит':<11} {'Медиана деф.'}")
            w("  " + "-" * 80)
            for r_cat in rating_buckets:
                if r_cat not in stats[style]:
                    continue
                s = stats[style][r_cat]
                n = s["games"]
                if n < 3:
                    continue
                wr = s["wins"] / n * 100
                avg_acpl = statistics.mean(s["acpls"]) if s["acpls"] else 0
                avg_time = statistics.mean(s["times"]) if s["times"] else 0
                if s["deficits"]:
                    avg_def = statistics.mean(s["deficits"])
                    med_def = statistics.median(s["deficits"])
                else:
                    avg_def = med_def = None
                def_str = f"{avg_def:+.1f}" if avg_def is not None else "—"
                med_str = f"{med_def:+.1f}" if med_def is not None else "—"
                w(f"  {r_cat:<12} {n:<5} {wr:>5.1f}% {avg_acpl:>5.0f} {avg_time:>7.2f}  {def_str:>9}  {med_str:>9}")
            w()

        w("=" * 70)
        w(" 🎯 ДЕБЮТЫ ПРОТИВ АГРЕССИВНЫХ И ТАКТИЧЕСКИХ")
        w("=" * 70)
        for style in ["aggressive", "tactical"]:
            if style not in deb_stats:
                continue
            w(f"\n📊 Стиль: {style.upper()}")
            w(f"  {'ECO':<6} {'Игр':<5} {'Win%':<7} {'ACPL':<6} {'Ср.дефицит':<11}")
            w("  " + "-" * 42)
            for eco3, d in sorted(deb_stats[style].items(), key=lambda x: -x[1]["games"])[:15]:
                n = d["games"]
                if n < 3:
                    continue
                wr = d["wins"] / n * 100
                avg_acpl = statistics.mean(d["acpls"]) if d["acpls"] else 0
                avg_def = statistics.mean(d["deficits"]) if d["deficits"] else None
                def_str = f"{avg_def:+.1f}" if avg_def is not None else "—"
                w(f"  {eco3:<6} {n:<5} {wr:>5.1f}% {avg_acpl:>5.0f} {def_str:>9}")
        w()

    print(f"\n✅ {path}")