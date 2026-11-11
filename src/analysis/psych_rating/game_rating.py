# ============================================================
# analysis/psych_rating/game_rating.py
# ============================================================
import os
from analysis.common import _conn, REPORTS_DIR
from core.метрики import game_rating as calc_gr

def report_game_rating_vs_perf():
    conn = _conn(); cur = conn.cursor(); path = os.path.join(REPORTS_DIR, "game_rating_vs_perf.txt")
    cur.execute("SELECT opp_rating, won, draw, acpl, accuracy FROM games WHERE is_lag=0 AND is_cheater=0 AND opp_rating > 0 AND acpl > 0")
    rows = cur.fetchall()
    buckets = {
        "< 2500": {"n": 0, "w": 0, "d": 0, "acpl_sum": 0, "gr_sum": 0, "acc_sum": 0, "opp_sum": 0},
        "2500-2599": {"n": 0, "w": 0, "d": 0, "acpl_sum": 0, "gr_sum": 0, "acc_sum": 0, "opp_sum": 0},
        "2600-2699": {"n": 0, "w": 0, "d": 0, "acpl_sum": 0, "gr_sum": 0, "acc_sum": 0, "opp_sum": 0},
        "2700+": {"n": 0, "w": 0, "d": 0, "acpl_sum": 0, "gr_sum": 0, "acc_sum": 0, "opp_sum": 0},
    }
    for opp_rating, won, draw, acpl, acc in rows:
        r = opp_rating
        if r < 2500: k = "< 2500"
        elif r < 2600: k = "2500-2599"
        elif r < 2700: k = "2600-2699"
        else: k = "2700+"
        b = buckets[k]; b["n"] += 1
        if won: b["w"] += 1
        if draw: b["d"] += 1
        b["acpl_sum"] += acpl or 0; b["gr_sum"] += calc_gr(acpl); b["acc_sum"] += acc or 0; b["opp_sum"] += opp_rating

    with open(path, "w", encoding="utf-8") as f:
        def w(line=""): print(line); f.write(line + "\n")
        w("=" * 70); w(" 🚀 GAME RATING vs PERFORMANCE ПО РЕЙТИНГАМ"); w("=" * 70)
        w("Game Rating — потенциал (качество ходов, по ACPL).")
        w("Performance — результат (по винрейту и среднему сопернику).")
        w("Если GameR > Perf — ты недобираешь результат. Если Perf > GameR — оверперформер."); w()
        w(f"  {'Рейтинг':<12} {'Игр':<5} {'Win%':<6} {'ACPL':<6} {'Точн':<6} {'GameR':<7} {'Perf':<7} {'Δ(Perf−GameR)'}")
        w("  " + "-" * 75)
        total_n = 0; total_gr_sum = 0; total_perf_weighted = 0
        for k in ["< 2500", "2500-2599", "2600-2699", "2700+"]:
            d = buckets[k]
            if d["n"] == 0: continue
            n = d["n"]; wr = (d["w"] + 0.5 * d["d"]) / n * 100; avg_acpl = d["acpl_sum"] / n
            avg_gr = d["gr_sum"] / n; avg_acc = d["acc_sum"] / n; avg_opp = d["opp_sum"] / n
            perf = avg_opp + (wr / 100 - 0.5) * 800; delta = perf - avg_gr
            mark = " ⚠️ Оверперф" if delta > 100 else (" ⚠️ Недобираешь" if delta < -100 else (" ✅" if delta > 30 else (" ⚠" if delta < -30 else "")))
            w(f"  {k:<12} {n:<5} {wr:<6.1f} {avg_acpl:<6.1f} {avg_acc:<6.1f} {avg_gr:<7.0f} {perf:<7.0f} {delta:+7.0f}{mark}")
            total_n += n; total_gr_sum += avg_gr * n; total_perf_weighted += perf * n
        w()
        if total_n > 0:
            avg_gr_overall = total_gr_sum / total_n; avg_perf_overall = total_perf_weighted / total_n; delta_overall = avg_perf_overall - avg_gr_overall
            w(f"  ВСЕГО: {total_n} партий"); w(f"  Средний GameR: {avg_gr_overall:.0f}"); w(f"  Средний Perf:  {avg_perf_overall:.0f}"); w(f"  Δ:             {delta_overall:+.0f}"); w()
            w("🎯 ВЕРДИКТ:")
            if delta_overall > 100:
                w(f"  ⚠️ Ты ОВЕРПЕРФОРМЕР на {delta_overall:.0f} п. Результат ВЫШЕ качества игры.")
                w("  💡 Стратегия: не гонись за рейтингом тактикой — учи технику.")
            elif delta_overall < -100:
                w(f"  ⚠️ Ты НЕДОБИРАЕШЬ {abs(delta_overall):.0f} п. Качество ВЫШЕ результата.")
                w("  💡 Стратегия: не учи тактику. Работай над контролем времени.")
            else:
                w(f"  ✅ Баланс: GameR ≈ Perf (Δ {delta_overall:+.0f}). Расти — через качество (ACPL).")
        else: w("  ⚠️ Нет данных.")
    conn.close(); print(f"\n✅ {path}")