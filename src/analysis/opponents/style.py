# ============================================================
# analysis/opponents/style.py — v20.2 (Стиль из БД)
# ============================================================
import os
from .common import _conn, REPORTS_DIR, PLAYER
from _chess_utils import rating_cat
from analysis.common import RATING_BUCKET_LABELS

def report_style_vs_rating():
    conn = _conn(); cur = conn.cursor()
    path = os.path.join(REPORTS_DIR, "style_vs_rating.txt")

    cur.execute("""
        SELECT opp_style, opp_rating, won FROM games
        WHERE is_lag=0 AND is_cheater=0 AND opp_rating > 0 AND opp_style IS NOT NULL
    """)
    rows = cur.fetchall()

    rating_ranges = RATING_BUCKET_LABELS
    style_names = ["aggressive", "tactical", "positional", "universal", "unknown"]
    matrix = {style: {r: {"n": 0, "w": 0} for r in rating_ranges} for style in style_names}

    for style, opp_rating, won in rows:
        if style not in style_names: continue
        rng = rating_cat(opp_rating)
        if rng not in rating_ranges: continue
        matrix[style][rng]["n"] += 1
        if won: matrix[style][rng]["w"] += 1

    with open(path, "w", encoding="utf-8") as f:
        def w(line=""): print(line); f.write(line + "\n")
        w("=" * 60); w(" 🎯 СТИЛЬ СОПЕРНИКА vs РЕЙТИНГ (Аллергия на агрессию)"); w("=" * 60)
        w("Показывает, против какого стиля и рейтинга ты играешь хуже всего."); w()

        for style in style_names:
            if style == "unknown": continue
            has_data = any(matrix[style][r]["n"] > 0 for r in rating_ranges)
            if not has_data: continue
            
            w(f"\n📊 Стиль: {style.upper()}")
            w(f"  {'Рейтинг':<12} {'Партий':<8} {'Винрейт':<10}")
            w("  " + "-" * 32)
            for rng in rating_ranges:
                d = matrix[style][rng]
                if d["n"] >= 3:
                    wr = d["w"] / d["n"] * 100
                    mark = " ⚠️ КРИТИЧНО" if wr < 30 else (" ⚠️ ПЛОХО" if wr < 40 else (" ✅ ХОРОШО" if wr > 60 else ""))
                    w(f"  {rng:<12} {d['n']:<8} {wr:<10.1f}%{mark}")

        w(); w("🎯 ВЕРДИКТ:")
        w("  Ищи строки с винрейтом < 40%. Это твои слабые комбинации (стиль + рейтинг).")
        w("  Если против aggressive 2600+ винрейт < 30% — тебе нужно учиться сушить позиции.")

    conn.close(); print(f"\n✅ {path}")