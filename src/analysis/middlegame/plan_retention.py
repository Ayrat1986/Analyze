# ============================================================
# analysis/middlegame/plan_retention.py (v19.0)
# ============================================================
from analysis.common import report_context
from .common import _conn, get_base_filter, safe_json_load

def report_plan_retention():
    conn = _conn()
    cur = conn.cursor()
    base = get_base_filter()

    cur.execute(f"SELECT url, white, eval_history FROM games WHERE {base} AND eval_history IS NOT NULL AND eval_history != '[]'")
    rows = cur.fetchall()

    buckets = {"peak_opening": [], "peak_middlegame": [], "peak_endgame": []}
    total_analyzed = skipped_no_peak = skipped_no_drop = 0

    for url, white, evals_raw in rows:
        hist = safe_json_load(evals_raw)
        if not hist or len(hist) < 5: continue
        vals = [(int(h[0]), float(h[1])) for h in hist]
        peak_val = max(v[1] for v in vals)
        if peak_val < 150: skipped_no_peak += 1; continue
        peak_idx = next(i for i, v in enumerate(vals) if v[1] == peak_val)
        peak_move = vals[peak_idx][0]

        retention = None
        for mv, ev in vals[peak_idx + 1:]:
            if ev < peak_val - 50:
                retention = mv - peak_move; break
        if retention is None or retention <= 0: skipped_no_drop += 1; continue

        key = "peak_opening" if peak_move <= 10 else ("peak_middlegame" if peak_move <= 30 else "peak_endgame")
        buckets[key].append(retention); total_analyzed += 1

    with report_context("plan_retention") as w:
        w.w_separator(title="PLAN RETENTION: сколько ходов держится план")
        w.w("Для каждой партии: пик eval >= +1.5, потом падение на 50+ CP.")
        w.w(f"Проанализировано: {total_analyzed}")
        w.w(f"Пропущено (пик < 1.5): {skipped_no_peak}")
        w.w(f"Пропущено (не упало): {skipped_no_drop}")
        w.w()

        w.w(f"  {'Фаза пика':<20} {'Партий':<8} {'Медиана (ходов)':<18} {'Среднее':<10}")
        w.w("  " + "-" * 60)

        worst_phase = None; worst_median = 999
        for key, label in [("peak_opening", "Пик в дебюте"), ("peak_middlegame", "Пик в миттельшпиле"), ("peak_endgame", "Пик в эндшпиле")]:
            vals = buckets[key]
            if not vals: continue
            vals_sorted = sorted(vals)
            med = vals_sorted[len(vals_sorted) // 2]
            mean = sum(vals) / len(vals)
            if med < worst_median: worst_median = med; worst_phase = label
            w.w(f"  {label:<20} {len(vals):<8} {med:<18} {mean:<10.1f}")
        w.w()

        w.w("🎯 ВЕРДИКТ:")
        if worst_phase == "Пик в миттельшпиле" and worst_median < 5:
            w.w(f"  ⚠️ КРИТИЧНО: пик в миттельшпиле держится {worst_median} ходов.")
            w.w("  💡 Правило: на ходу +1.5 — СТОП, пересмотри цель.")
            w.w("  💡 Меняй ферзей при +3.0 (Бухгалтер) — план станет проще.")
        elif worst_median < 5:
            w.w(f"  ⚠️ Худшая фаза: {worst_phase} ({worst_median} ходов).")
        else:
            w.w(f"  ✅ План держится ≥ 5 ходов во всех фазах.")
        w.w()
        w.w("💡 Ориентир: у сильных игроков медиана 6-10 ходов. < 5 ходов = «слепота».")
    conn.close()