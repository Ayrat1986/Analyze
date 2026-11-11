# ============================================================
# analysis/middlegame/long_vs_short.py (v19.0)
# ============================================================
from analysis.common import report_context
from .common import _conn, get_base_filter

def report_long_vs_short():
    conn = _conn()
    cur = conn.cursor()
    base = get_base_filter()

    cur.execute(f"""
        SELECT game_length, won, draw, acpl, acpl_opening, acpl_middlegame,
               acpl_endgame, opp_rating, my_rating, reason
        FROM games WHERE {base} AND game_length IS NOT NULL AND game_length > 0 AND acpl > 0
    """)
    rows = cur.fetchall()

    with report_context("long_vs_short") as w:
        w.w_separator(title="КОРОТКИЕ vs СРЕДНИЕ vs ДЛИННЫЕ (длина партии → исход)")
        
        if not rows:
            w.w("⚠️ Нет данных.")
            conn.close()
            return

        buckets = {
            "short": {"label": "Короткие (< 40)", "n": 0, "w": 0, "d": 0, "acpl": 0, "op": 0, "mid": 0, "end": 0, "opp": 0, "my": 0, "timeout": 0, "mat": 0},
            "medium": {"label": "Средние (40–60)", "n": 0, "w": 0, "d": 0, "acpl": 0, "op": 0, "mid": 0, "end": 0, "opp": 0, "my": 0, "timeout": 0, "mat": 0},
            "long": {"label": "Длинные (> 60)", "n": 0, "w": 0, "d": 0, "acpl": 0, "op": 0, "mid": 0, "end": 0, "opp": 0, "my": 0, "timeout": 0, "mat": 0},
        }

        for length, won, draw, acpl, acpl_op, acpl_mid, acpl_end, opp, my, reason in rows:
            k = "short" if length < 40 else ("medium" if length <= 60 else "long")
            b = buckets[k]
            b["n"] += 1
            if won: b["w"] += 1
            if draw: b["d"] += 1
            b["acpl"] += acpl or 0; b["op"] += acpl_op or 0; b["mid"] += acpl_mid or 0
            b["end"] += acpl_end or 0; b["opp"] += opp or 0; b["my"] += my or 0
            if reason == "просрочка": b["timeout"] += 1
            if reason == "мат": b["mat"] += 1

        w.w(f"  {'Категория':<22} {'Партий':<7} {'Win%':<7} {'ACPL':<6} {'Деб':<6} {'Мит':<6} {'Энд':<6} {'Просроч':<8} {'Мат'}")
        w.w("  " + "-" * 85)

        total_n = sum(b["n"] for b in buckets.values())
        for k in ["short", "medium", "long"]:
            d = buckets[k]
            if d["n"] == 0: continue
            n = d["n"]
            score = (d["w"] + 0.5 * d["d"]) / n * 100
            w.w(f"  {d['label']:<22} {n:<7} {score:<7.1f} {d['acpl']/n:<6.0f} {d['op']/n:<6.0f} {d['mid']/n:<6.0f} {d['end']/n:<6.0f} {d['timeout']:<8} {d['mat']}")

        w.w()
        w.w(f"Всего партий: {total_n}")
        w.w()
        w.w("🎯 ВЕРДИКТ:")

        short = buckets["short"]; long_ = buckets["long"]
        if short["n"] >= 10 and long_["n"] >= 10:
            short_wr = (short["w"] + 0.5 * short["d"]) / short["n"] * 100
            long_wr = (long_["w"] + 0.5 * long_["d"]) / long_["n"] * 100
            short_acpl = short["acpl"] / short["n"]; long_acpl = long_["acpl"] / long_["n"]
            delta_wr = short_wr - long_wr

            if delta_wr > 10:
                w.w(f"  ⚠️ В коротких партиях ты играешь ЛУЧШЕ (+{delta_wr:.0f}% очков).")
                w.w(f"     ACPL: короткие {short_acpl:.0f} vs длинные {long_acpl:.0f}.")
                w.w("     💡 Теряешь концентрацию в длинных партиях.")
            elif delta_wr < -10:
                w.w(f"  ✅ В длинных партиях ты играешь ЛУЧШЕ (на {abs(delta_wr):.0f}% очков).")
            else:
                w.w(f"  ➡️ Длина не влияет на результат (Δ {delta_wr:+.0f}% очков).")

            if long_["n"] > 0 and long_["timeout"] / long_["n"] > 0.3:
                w.w(f"  ⚠️ В длинных партиях {long_['timeout']/long_['n']*100:.0f}% просрочек.")
    conn.close()