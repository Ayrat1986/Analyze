# ============================================================
# analysis/middlegame/advantage_speed.py (v19.4)
# Исправлено: base_time из time_control. Окна 1/2/7/30/90.
# ============================================================
from datetime import datetime, timezone, timedelta
from analysis.common import report_context
from core.time_control import parse_time_control
from .common import _conn, get_base_filter, safe_json_load, PLAYER

WINDOWS = [1, 2, 7, 30, 90]

def _window_label(days):
    if days == 1: return "1 ДЕНЬ"
    if days == 2: return "2 ДНЯ"
    return f"{days} ДНЕЙ"


def report_advantage_speed():
    conn = _conn()
    cur = conn.cursor()
    base = get_base_filter()
    now_ts = int(datetime.now(timezone.utc).timestamp())

    with report_context("advantage_speed") as w:
        w.w_separator(title="ADVANTAGE SPEED (Пульс перевеса)")
        w.w("Сравнивает скорость хода при перевесе (+3.0), при равной (0.0), после падения.")
        w.w("⚠️ База времени из time_control (1+0 → 60 сек, 3+2 → 180 сек).")
        w.w("Окна: 1 / 2 / 7 / 30 / 90 дней.")
        w.w()

        for days in WINDOWS:
            cutoff = now_ts - days * 86400
            cur.execute(f"""
                SELECT url, eval_history, clocks, white, max_eval_advantage, won, draw, time_control
                FROM games
                WHERE {base}
                  AND end_time >= ?
                  AND eval_history IS NOT NULL AND eval_history != '[]'
                  AND clocks IS NOT NULL AND clocks != '[]'
                ORDER BY end_time DESC LIMIT 500
            """, (cutoff,))
            rows = cur.fetchall()

            w.w_separator(title=f"ОКНО: {_window_label(days)}")
            if not rows:
                w.w("⚠️ Нет данных.")
                w.w()
                continue

            times_winning, times_equal, times_after_drop = [], [], []
            time_lost_won, time_realized_won = [], []

            for url, evals_raw, clocks_raw, white, max_adv, won, draw, tc in rows:
                evals = safe_json_load(evals_raw)
                clocks = safe_json_load(clocks_raw)
                if not evals or not clocks:
                    continue
                player_is_white = (white or "").lower() == PLAYER.lower()
                base_sec, _ = parse_time_control(tc)

                game_times = []
                for i in range(1, len(evals)):
                    move_num, ev = evals[i]
                    prev_ev = evals[i - 1][1]
                    ply = (move_num - 1) * 2 + (0 if player_is_white else 1)

                    time_spent = None
                    if ply < len(clocks):
                        if ply == 0:
                            time_spent = base_sec - clocks[0]
                        elif ply == 1:
                            if len(clocks) > 1:
                                time_spent = clocks[0] - clocks[1]
                        elif ply >= 2:
                            time_spent = clocks[ply - 2] - clocks[ply]
                        if time_spent is not None and time_spent <= 0:
                            time_spent = None

                    if not time_spent:
                        continue
                    game_times.append(time_spent)

                    if ev > 300:
                        times_winning.append(time_spent)
                    elif abs(ev) < 50:
                        times_equal.append(time_spent)
                    if prev_ev > 300 and ev < 100:
                        times_after_drop.append(time_spent)

                if max_adv and max_adv >= 300 and game_times:
                    avg_time_game = sum(game_times) / len(game_times)
                    if won:
                        time_realized_won.append(avg_time_game)
                    elif draw == 0:
                        time_lost_won.append(avg_time_game)

            # Блок 1: перевес vs равенство
            if times_winning and times_equal:
                avg_winning = sum(times_winning) / len(times_winning)
                avg_equal = sum(times_equal) / len(times_equal)

                w.w(f"  {'Ситуация':<25} {'Ср. время':<12} {'Ходов':<8}")
                w.w("  " + "-" * 48)
                w.w(f"  {'При перевесе (+3.0)':<25} {avg_winning:<12.2f} {len(times_winning):<8}")
                w.w(f"  {'При равной игре (0.0)':<25} {avg_equal:<12.2f} {len(times_equal):<8}")
                if times_after_drop:
                    avg_after_drop = sum(times_after_drop) / len(times_after_drop)
                    w.w(f"  {'После падения (+3.0→0.0)':<25} {avg_after_drop:<12.2f} {len(times_after_drop):<8}")
                w.w()

                diff = avg_winning - avg_equal
                diff_pct = (diff / avg_equal * 100) if avg_equal else 0
                w.w(f"  Разница (перевес − равенство): {diff:+.2f} сек ({diff_pct:+.0f}%)")

                if diff_pct > 15:
                    w.w(f"  ⚠️ При перевесе ты играешь на {diff_pct:.0f}% МЕДЛЕННЕЕ.")
                    w.w("  Риск цейтнота в выигранных партиях.")
                    w.w("  💡 Правило: при +3.0 — держи ритм, не замедляйся без причины.")
                elif diff_pct < -15:
                    w.w(f"  ⚠️ При перевесе ты играешь на {abs(diff_pct):.0f}% БЫСТРЕЕ.")
                    w.w("  Это суета. Ты торопишься добить, но теряешь контроль.")
                else:
                    w.w("  ➡️ Одинаковая скорость. Нейтрально.")
            else:
                w.w("  ⚠️ Недостаточно данных для сравнения перевес/равенство.")

            # Блок 2: время в слитых vs реализованных
            w.w()
            w.w("  📊 ВРЕМЯ В СЛИТЫХ vs РЕАЛИЗОВАННЫХ:")
            if time_lost_won or time_realized_won:
                if time_lost_won:
                    avg_lost = sum(time_lost_won) / len(time_lost_won)
                    w.w(f"    Слитые (проиграл при +3.0):  {avg_lost:.2f} сек ({len(time_lost_won)} партий)")
                if time_realized_won:
                    avg_real = sum(time_realized_won) / len(time_realized_won)
                    w.w(f"    Реализованные (выиграл):      {avg_real:.2f} сек ({len(time_realized_won)} партий)")
                if time_lost_won and time_realized_won:
                    delta = avg_lost - avg_real
                    if delta > 0.1:
                        w.w(f"    ⚠️ В слитых играешь на {delta:.2f} сек МЕДЛЕННЕЕ → цейтнот.")
                    elif delta < -0.1:
                        w.w(f"    ✅ В слитых играешь быстрее на {abs(delta):.2f} сек → суета.")
                    else:
                        w.w("    ➡️ Одинаковое время.")
            else:
                w.w("    ⚠️ Нет партий с перевесом +3.0.")
            w.w()

    conn.close()