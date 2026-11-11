# ============================================================
# analysis/dashboards/index.py — 00_INDEX.txt (v20.3 — Fix Float Delta)
# ============================================================
import os
from datetime import datetime

import _common
from analysis.common import PLAYER
from analysis.dashboard_helpers import (
    key_numbers, full_dynamics, last_session_vs_windows,
    time_vs_rating, combined_vs_perf, aggression_by_rating, aggression_by_opening,
    aggression_by_phase, aggression_by_moves, top3_weaknesses, top_actions, DASHBOARD_FILES,
    monitoring_snapshot
)


def build_index(w):
    w.w("#" * 60)
    w.w(f" 📊 DASHBOARD INDEX — {PLAYER} — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    w.w("#" * 60)
    w.w()

    # 1. Ключевые цифры
    w.w("📈 КЛЮЧЕВЫЕ ЦИФРЫ (90 дней):")
    for k, v in key_numbers().items():
        w.w(f"  {k:<28} {v}")
    w.w()

    # 2. Тренд последней сессии
    w.w("🔥 ТРЕНД ПОСЛЕДНЕЙ СЕССИИ vs ОКНА (2/7/30/90/365):")
    w.w(f"  {'Окно':<18} {'Игр':<5} {'Win%':<7} {'ACPL':<7} {'GameR':<7} {'Рейт.':<6} {'P90'}")
    w.w("  " + "-" * 65)
    for row in last_session_vs_windows():
        if row["games"] == 0:
            w.w(f"  {row['label']:<18} {'0':<5} {'—':<7} {'—':<7} {'—':<7} {'—':<6} {'—'}")
            continue
        w.w(f"  {row['label']:<18} {row['games']:<5} {row['win_rate']:<7} "
            f"{row['acpl']:<7} {row['gamr']:<7} {row['my_rating']:<6} {row['p90']}")
    w.w()

    # 3. Полная динамика (ВСЕ КОЛОНКИ + Защита от KeyError)
    w.w("📊 ПОЛНАЯ ДИНАМИКА (Рейтинг, Скорость, Точность, Соперники):")
    w.w(f"  {'Окно':<10} {'Игр':<6} {'Дом':<6} {'Пик':<6} {'Дно':<6} "
        f"{'Win%':<6} {'AvgOpp':<7} {'GameR':<7} {'SpeedR':<7} {'CombR':<7} {'Δ':<6} {'AvgT':<6} "
        f"{'Perf':<6} {'P10':<6} {'P50':<6} {'P90':<6} {'ACPL':<6}")
    w.w("  " + "-" * 130)
    for d in full_dynamics():
        if d.get("games", 0) == 0:
            w.w(f"  {d.get('window', ''):<10} {'0':<6} {'—':<6} {'—':<6} {'—':<6} "
                f"{'—':<6} {'—':<7} {'—':<7} {'—':<7} {'—':<7} {'—':<6} {'—':<6} "
                f"{'—':<6} {'—':<6} {'—':<6} {'—':<6} {'—':<6}")
            continue
        
        gamr = d.get('gamr', 0)
        speedr = d.get('speedr', 0)
        delta = gamr - speedr
        delta_str = f"{delta:+d}" if delta != 0 else "0"
        
        w.w(f"  {d.get('window', ''):<10} {d.get('games', 0):<6} {d.get('home', 0):<6} {d.get('peak', 0):<6} {d.get('bottom', 0):<6} "
            f"{d.get('win_rate', 0):<6} {d.get('avg_opp', 0):<7} {gamr:<7} {speedr:<7} {d.get('combined_r', 0):<7} {delta_str:<6} {d.get('avg_time', 0):<6.2f} "
            f"{d.get('perf', 0):<6} {d.get('p10', 0):<6} {d.get('p50', 0):<6} {d.get('p90', 0):<6} {d.get('acpl', 0):<6}")
            
    w.w("  💡 Дом = средний рейтинг, Пик = максимум, Дно = минимум.")
    w.w("  💡 GameR = по точности, SpeedR = по скорости, CombR = общий потенциал.")
    w.w("  💡 AvgOpp = средний рейтинг соперников, Win% = винрейт.")
    w.w("  💡 Δ = GameR − SpeedR. Если Δ > +30 — ты медлишь, если Δ < -30 — спешишь.")
    w.w("  💡 AvgT = среднее время на ход (в секундах).")
    w.w()

    # 3.5. НОВЫЙ БЛОК: МОНИТОРИНГ (СНАПШОТЫ)
    snapshots = monitoring_snapshot()
    if snapshots:
        w.w("🎯 МОНИТОРИНГ ДИНАМИКИ (Снапшоты - 1/7/30/90 дней):")
        w.w(f"  {'Окно':<10} {'Дата':<12} {'CombR':<7} {'Δ':<6} {'StdDev':<7} {'Агрессия':<9} {'Охотник%'}")
        w.w("  " + "-" * 60)
        for s in snapshots:
            mark = "🔥" if s['window'] == "Сегодня" else "  "
            
            # Защита от float при форматировании delta
            delta_val = int(s.get('delta')) if s.get('delta') is not None else 0
            delta_str = f"{delta_val:+d}"
            
            combr = s.get('combined_r') or 0
            stddev = s.get('stddev_acpl') or 0
            agg = s.get('aggression') or 0
            hunter = s.get('hunter_pct') or 0
            
            w.w(f"  {mark}{s['window']:<8} {s['date']:<12} {combr:<7.0f} {delta_str:<6} {stddev:<7.1f} {agg:<9.1f} {hunter:.0f}%")
        w.w("  💡 StdDev — цель < 15. Агрессия > 8.0 = Охотник, < 8.0 = Защитник.")
        w.w()

    # 4. Агрессия по рейтингам
    w.w("🥊 АГРЕССИЯ ПО РЕЙТИНГАМ (взятия + шахи на ход):")
    agg = aggression_by_rating()
    if agg:
        w.w(f"  {'Рейтинг':<12} {'Игр':<6} {'Win%':<7} {'Агрессия'}")
        w.w("  " + "-" * 40)
        for a in agg:
            w.w(f"  {a['rating']:<12} {a['games']:<6} {a['win_rate']:<7} {a['aggression']}")
        w.w("  💡 Агрессия = % ходов, где ты берешь фигуру или ставишь шах.")
    else:
        w.w("  ⚠️ Нет данных (нужны PGN).")
    w.w()

    # 5. Агрессия по дебютам
    w.w("🥊 АГРЕССИЯ ПО ДЕБЮТАМ (Топ-15 по частоте):")
    agg_open = aggression_by_opening()
    if agg_open:
        w.w(f"  {'ECO':<5} {'Дебют':<32} {'Игр':<5} {'Win%':<7} {'Агр.':<7} {'AvgT'}")
        w.w("  " + "-" * 65)
        for a in agg_open:
            name = a['opening'][:30] + ".." if len(a['opening']) > 30 else a['opening']
            w.w(f"  {a['eco']:<5} {name:<32} {a['games']:<5} {a['win_rate']:<7} {a['aggression']:<7} {a['avg_time']}")
        w.w("  💡 AvgT = среднее время на ход (сек).")
    else:
        w.w("  ⚠️ Нет данных.")
    w.w()

    # 6. Агрессия по фазам
    w.w("📊 АГРЕССИЯ И ВРЕМЯ ПО ФАЗАМ:")
    agg_phase = aggression_by_phase()
    if agg_phase:
        w.w(f"  {'Фаза':<24} {'Игр':<5} {'Win%':<7} {'Агрессия':<10} {'AvgT'}")
        w.w("  " + "-" * 55)
        for p in agg_phase:
            w.w(f"  {p['phase']:<24} {p['games']:<5} {p['win_rate']:<7} {p['aggression']:<10} {p['avg_time']}")
        w.w("  💡 Если AvgT растёт от фазы к фазе, а Агрессия падает — ты сжимаешься.")
    else:
        w.w("  ⚠️ Нет данных.")
    w.w()

    # 7. Походовый разбор
    w.w("⚔️ ПОХОДОВЫЙ РАЗБОР МИТТЕЛЬШПИЛЯ (поиск 'часа X'):")
    agg_moves = aggression_by_moves()
    if agg_moves:
        w.w(f"  {'Ходы':<10} {'Игр':<5} {'Win%':<7} {'Агрессия':<10} {'AvgT'}")
        w.w("  " + "-" * 55)
        for m in agg_moves:
            w.w(f"  {m['range']:<10} {m['games']:<5} {m['win_rate']:<7} {m['aggression']:<10} {m['avg_time']}")
        w.w("  💡 Ищи отрезок с высоким AvgT и низкой агрессией — там ты 'сгораешь'.")
    else:
        w.w("  ⚠️ Нет данных.")
    w.w()

    # 8. Вердикт
    w.w("🎯 ВЕРДИКТ (GameR vs SpeedR vs Perf):")
    dynamics = full_dynamics()
    day90 = next((d for d in dynamics if d.get("window") == "90 дней"), None)
    day1 = next((d for d in dynamics if d.get("window") == "1 день"), None)
    
    if day90 and day1:
        delta_90 = day90.get('gamr', 0) - day90.get('speedr', 0)
        delta_1 = day1.get('gamr', 0) - day1.get('speedr', 0)
        
        if abs(delta_90) < 30:
            w.w(f"  ✅ 90 дней: Идеальный баланс (Δ {delta_90:+d}). Ты играешь ровно на свой рейтинг.")
        elif delta_90 > 30:
            w.w(f"  ⚠️ 90 дней: Перекос в точность (Δ {delta_90:+d}). Ты играешь слишком медленно.")
        else:
            w.w(f"  ⚠️ 90 дней: Перекос в скорость (Δ {delta_90:+d}). Ты играешь слишком быстро.")
            
        if delta_1 > 50:
            w.w(f"  🔥 1 день: Вчера ты сильно замедлился (Δ {delta_1:+d}).")
            w.w(f"     GameR вырос до {day1.get('gamr', 0)}, но Perf упал до {day1.get('perf', 0)} — ты сгорел в цейтноте.")
            w.w(f"     👉 Решение: ускорься до {day90.get('avg_time', 1.17):.2f} сек/ход.")
    w.w()

    # 9. Топ-3 слабости
    w.w("🎯 ТОП-3 СЛАБОСТИ:")
    for i, (name, detail, ref) in enumerate(top3_weaknesses(), 1):
        w.w(f"  {i}. {name} — {detail}")
        w.w(f"     → {ref}")
    w.w()

    # 10. Действия
    w.w("🎯 ЧТО ДЕЛАТЬ СЕГОДНЯ:")
    for i, action in enumerate(top_actions(), 1):
        w.w(f"  {i}. {action}")
    w.w()

    w.w("📦 АРХИВ: dashboard_FINAL.txt (в корне) — полный текст всех отчётов.")
    w.w()


def write_index():
    path = os.path.join(str(_common.BASE_DIR), "00_INDEX.txt")
    with open(path, "w", encoding="utf-8") as f:
        def w(line=""):
            print(line); f.write(str(line) + "\n")
        build_index(type("W", (), {"w": staticmethod(w)})())
    print(f"\n✅ {path}")