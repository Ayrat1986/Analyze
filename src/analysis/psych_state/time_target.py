# ============================================================
# analysis/psych_state/time_target.py (v19.4)
# Целевое время на ход: из лучших партий (P10) → целевое.
# Исправлено: base_time из time_control (1+0 или 3+2).
# ============================================================
import json
import statistics
from datetime import datetime, timezone, timedelta

from analysis.common import report_context, WINDOWS, window_label, window_cutoff_ts
from core.time_control import parse_time_control
from .common import _conn, _is_player_white


def _analyze_game_times(evals_raw, clocks_raw, player_is_white, time_control="60"):
    """
    Возвращает dict: opening_times, middlegame_times, endgame_times.
    Использует clocks (остаток времени) и move_num.
    База времени берётся из time_control (60 для 1+0, 180 для 3+2).
    """
    try:
        clocks = json.loads(clocks_raw) if clocks_raw else []
        evals = json.loads(evals_raw) if evals_raw else []
    except Exception:
        return None
    if not clocks or not evals:
        return None

    base_sec, _ = parse_time_control(time_control)
    opening, middlegame, endgame = [], [], []

    for i in range(1, len(evals)):
        move_num, ev = evals[i]
        ply = (move_num - 1) * 2 + (0 if player_is_white else 1)
        
        time_spent = None
        if ply < len(clocks):
            if ply == 0:
                time_spent = base_sec - clocks[0]
            elif ply == 1 and len(clocks) > 1:
                time_spent = clocks[0] - clocks[1]
            elif ply >= 2:
                time_spent = clocks[ply - 2] - clocks[ply]
        
        if time_spent is None or time_spent <= 0 or time_spent > 30:
            continue

        if move_num <= 10:
            opening.append(time_spent)
        elif move_num <= 30:
            middlegame.append(time_spent)
        else:
            endgame.append(time_spent)

    return {
        "opening": opening,
        "middlegame": middlegame,
        "endgame": endgame,
    }


def report_time_target():
    conn = _conn()
    cur = conn.cursor()

    with report_context("time_target") as w:
        w.w_separator(title="ЦЕЛЕВОЕ ВРЕМЯ НА ХОД")
        w.w("Логика: в лучших 10% партий (по ACPL) у тебя было X сек/ход.")
        w.w("Это и есть целевое время.")
        w.w("⚠️ Базовое время берётся из time_control (1+0 → 60 сек).")
        w.w()

        for days in WINDOWS:
            cutoff = window_cutoff_ts(days)
            cur.execute("""
                SELECT acpl, eval_history, clocks, white, time_control
                FROM games
                WHERE is_lag=0 AND is_cheater=0 AND end_time >= ?
                  AND acpl > 0 AND eval_history IS NOT NULL AND eval_history != '[]'
                  AND clocks IS NOT NULL AND clocks != '[]'
            """, (cutoff,))
            rows = cur.fetchall()

            w.w_separator(title=f"ОКНО: {window_label(days)}")
            if not rows:
                w.w("⚠️ Нет данных.")
                w.w()
                continue

            all_data = []
            for acpl, evals_raw, clocks_raw, white, tc in rows:
                player_is_white = _is_player_white(white)
                times = _analyze_game_times(evals_raw, clocks_raw, player_is_white, tc)
                if not times:
                    continue
                all_data.append({
                    "acpl": acpl,
                    "opening": times["opening"],
                    "middlegame": times["middlegame"],
                    "endgame": times["endgame"],
                })

            if len(all_data) < 10:
                w.w(f"⚠️ Мало данных ({len(all_data)} партий, нужно 10+).")
                w.w()
                continue

            all_data.sort(key=lambda x: x["acpl"])
            n = len(all_data)
            p10_idx = int(n * 0.1)
            p50_idx = int(n * 0.5)
            p90_idx = int(n * 0.9)

            def _avg_time(data_slice, phase):
                times = []
                for d in data_slice:
                    times.extend(d[phase])
                return statistics.mean(times) if times else 0

            p10_slice = all_data[:p10_idx] if p10_idx > 0 else all_data[:1]
            p50_slice = all_data[p50_idx:p50_idx+1] if p50_idx < n else all_data[-1:]
            p90_slice = all_data[p90_idx:] if p90_idx < n else all_data[-1:]

            w.w(f"  {'Группа':<20} {'Дебют':<10} {'Миттельшпиль':<15} {'Эндшпиль':<10}")
            w.w("  " + "-" * 58)
            
            p10_op = _avg_time(p10_slice, "opening")
            p10_mid = _avg_time(p10_slice, "middlegame")
            p10_end = _avg_time(p10_slice, "endgame")
            w.w(f"  {'P10 (лучшие 10%)':<20} {p10_op:<10.2f} {p10_mid:<15.2f} {p10_end:<10.2f}")
            
            p50_op = _avg_time(p50_slice, "opening")
            p50_mid = _avg_time(p50_slice, "middlegame")
            p50_end = _avg_time(p50_slice, "endgame")
            w.w(f"  {'P50 (медиана)':<20} {p50_op:<10.2f} {p50_mid:<15.2f} {p50_end:<10.2f}")
            
            p90_op = _avg_time(p90_slice, "opening")
            p90_mid = _avg_time(p90_slice, "middlegame")
            p90_end = _avg_time(p90_slice, "endgame")
            w.w(f"  {'P90 (худшие 10%)':<20} {p90_op:<10.2f} {p90_mid:<15.2f} {p90_end:<10.2f}")
            w.w()

            w.w("  🎯 ЦЕЛЕВОЕ ВРЕМЯ (из лучших 10% партий):")
            w.w(f"     Дебют:        {p10_op:.2f} сек/ход")
            w.w(f"     Миттельшпиль: {p10_mid:.2f} сек/ход")
            w.w(f"     Эндшпиль:     {p10_end:.2f} сек/ход")
            w.w()

            current_op = statistics.mean([t for d in all_data for t in d["opening"]]) if any(d["opening"] for d in all_data) else 0
            current_mid = statistics.mean([t for d in all_data for t in d["middlegame"]]) if any(d["middlegame"] for d in all_data) else 0
            current_end = statistics.mean([t for d in all_data for t in d["endgame"]]) if any(d["endgame"] for d in all_data) else 0

            w.w("  📊 СРАВНЕНИЕ (сейчас vs целевое):")
            w.w(f"     Дебют:        {current_op:.2f} → {p10_op:.2f} (Δ {p10_op - current_op:+.2f})")
            w.w(f"     Миттельшпиль: {current_mid:.2f} → {p10_mid:.2f} (Δ {p10_mid - current_mid:+.2f})")
            w.w(f"     Эндшпиль:     {current_end:.2f} → {p10_end:.2f} (Δ {p10_end - current_end:+.2f})")
            w.w()

            if p10_mid > current_mid:
                w.w(f"  ⚠️ В миттельшпиле ты играешь БЫСТРЕЕ, чем в лучших партиях.")
                w.w(f"     Цель: замедлиться до {p10_mid:.2f} сек/ход (+{p10_mid - current_mid:.2f} сек).")
            else:
                w.w(f"  ✅ В миттельшпиле ты играешь медленнее или равно лучшим партиям.")
            w.w()

        # Рейтинговые бакеты (только 90 дней)
        w.w_separator(title="ПО РЕЙТИНГОВЫМ БАКЕТАМ (90 дней)")
        from analysis.common import rating_bucket, RATING_BUCKET_LABELS
        
        cutoff = window_cutoff_ts(90)
        cur.execute("""
            SELECT acpl, eval_history, clocks, white, opp_rating, time_control
            FROM games
            WHERE is_lag=0 AND is_cheater=0 AND end_time >= ?
              AND acpl > 0 AND eval_history IS NOT NULL AND eval_history != '[]'
              AND clocks IS NOT NULL AND clocks != '[]' AND opp_rating > 0
        """, (cutoff,))
        rows = cur.fetchall()

        by_bucket = {label: {"times": [], "acpls": []} for label in RATING_BUCKET_LABELS}
        for acpl, evals_raw, clocks_raw, white, opp_rating, tc in rows:
            player_is_white = _is_player_white(white)
            times = _analyze_game_times(evals_raw, clocks_raw, player_is_white, tc)
            if not times:
                continue
            bucket = rating_bucket(opp_rating)
            if bucket in by_bucket:
                by_bucket[bucket]["times"].extend(times["middlegame"])
                by_bucket[bucket]["acpls"].append(acpl)

        w.w(f"  {'Бакет':<15} {'Игр':<6} {'ACPL':<8} {'Ср. время (мит)':<18} {'Вывод'}")
        w.w("  " + "-" * 70)
        for label in RATING_BUCKET_LABELS:
            d = by_bucket[label]
            if len(d["acpls"]) >= 5 and d["times"]:
                avg_acpl = statistics.mean(d["acpls"])
                avg_time = statistics.mean(d["times"])
                if avg_acpl < 70:
                    verdict = "✅ Хорошо (ACPL < 70)"
                elif avg_time < 1.0:
                    verdict = "⚠️ Слишком быстро"
                elif avg_time > 2.0:
                    verdict = "⚠️ Слишком медленно"
                else:
                    verdict = "➡️ Средне"
                w.w(f"  {label:<15} {len(d['acpls']):<6} {avg_acpl:<8.1f} {avg_time:<18.2f} {verdict}")
            else:
                w.w(f"  {label:<15} —      —        —                  нет данных")

    conn.close()