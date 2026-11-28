# ============================================================
# analysis/dashboards/index.py — 00_INDEX.txt (v27.7)
# Расширенные пояснения по Δ, ΔGS, ΔAS (превышение / равенство / занижение)
# и разграничение прессинга по времени vs спешки в вердикте дня.
# ============================================================
import os
from datetime import datetime

import _common
from analysis.common import PLAYER
from analysis.dashboard_helpers import (
    DASHBOARD_FILES,
    aggression_by_moves,
    aggression_by_opening,
    aggression_by_phase,
    aggression_by_rating,
    combined_vs_perf,
    full_dynamics,
    key_numbers,
    last_session_vs_windows,
    monitoring_snapshot,
    time_vs_rating,
    top3_weaknesses,
    top_actions,
)


def _fmt_signed(val: int) -> str:
    return f"{val:+d}" if val != 0 else "0"


def build_index(w):
    w.w("#" * 60)
    w.w(f" 📊 DASHBOARD INDEX — {PLAYER} — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    w.w("#" * 60)
    w.w()

    # 1. Ключевые цифры за 90 дней
    w.w("📈 КЛЮЧЕВЫЕ ЦИФРЫ (90 дней):")
    for k, v in key_numbers(90).items():
        w.w(f"  {k:<28} {v}")
    w.w()

    # 1.5. Ключевые цифры за 1 день (текущая сессия дня)
    w.w("⚡ КЛЮЧЕВЫЕ ЦИФРЫ (1 день / текущая сессия дня):")
    for k, v in key_numbers(1).items():
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

    # 3. Полная динамика (4 контура + CombR + дельты)
    w.w("📊 ПОЛНАЯ ДИНАМИКА (Рейтинг, Точность, Скорость, Агрессия, Тильт):")
    w.w(f"  {'Окно':<10} {'Игр':<6} {'Дом':<6} {'Пик':<6} {'Дно':<6} "
        f"{'Win%':<6} {'AvgOpp':<7} {'GameR':<7} {'SpeedR':<7} {'AggrR':<7} {'StateR':<7} {'CombR':<7} "
        f"{'Δ':<6} {'ΔGS':<6} {'ΔAS':<6} {'AvgT':<6} "
        f"{'Perf':<6} {'P10':<6} {'P50':<6} {'P90':<6} {'ACPL':<6}")
    w.w("  " + "-" * 145)
    dynamics = full_dynamics()
    for d in dynamics:
        if d.get("games", 0) == 0:
            w.w(f"  {d.get('window', ''):<10} {'0':<6} {'—':<6} {'—':<6} {'—':<6} "
                f"{'—':<6} {'—':<7} {'—':<7} {'—':<7} {'—':<7} {'—':<7} {'—':<7} "
                f"{'—':<6} {'—':<6} {'—':<6} {'—':<6} "
                f"{'—':<6} {'—':<6} {'—':<6} {'—':<6} {'—':<6}")
            continue

        home = d.get("home", 0)
        gamr = d.get("gamr", 0)
        speedr = d.get("speedr", 0)
        aggr_r = d.get("aggr_r", 0)
        state_r = d.get("state_r", 0)
        combr = d.get("combined_r", 0)

        delta_str = _fmt_signed(d.get("delta", combr - home))
        delta_gs_str = _fmt_signed(d.get("delta_gs", gamr - speedr))
        delta_as_str = _fmt_signed(d.get("delta_as", aggr_r - state_r))

        w.w(f"  {d.get('window', ''):<10} {d.get('games', 0):<6} {home:<6} {d.get('peak', 0):<6} {d.get('bottom', 0):<6} "
            f"{d.get('win_rate', 0):<6} {d.get('avg_opp', 0):<7} {gamr:<7} {speedr:<7} {aggr_r:<7} {state_r:<7} {combr:<7} "
            f"{delta_str:<6} {delta_gs_str:<6} {delta_as_str:<6} {d.get('avg_time', 0):<6.2f} "
            f"{d.get('perf', 0):<6} {d.get('p10', 0):<6} {d.get('p50', 0):<6} {d.get('p90', 0):<6} {d.get('acpl', 0):<6}")

    w.w("  💡 Дом = средний рейтинг, Пик = максимум, Дно = минимум. AvgOpp = средний рейтинг соперников, AvgT = время на ход (сек).")
    w.w("  💡 GameR = точность, SpeedR = скорость, AggrR = агрессия, StateR = тильт/реализация, CombR = общий потенциал.")
    w.w("  💡 Δ = CombR − Дом (потенциал vs текущий рейтинг):")
    w.w("     • Δ > +20 (превышение) — играешь сильнее своего рейтинга, скоро пойдёт рост;")
    w.w("     • Δ ∈ [−20; +20] (равенство) — играешь ровно на свой рейтинг (на 90 и 365 днях Δ ≈ 0 — эталон калибровки);")
    w.w("     • Δ < −20 (занижение) — текущая форма ниже рейтинга, высок риск просадки (нужен стоп-лосс или пауза).")
    w.w("  💡 ΔGS = GameR − SpeedR (баланс точности и темпа):")
    w.w("     • ΔGS > +30 (превышение) — перекос в счёт: играешь точно, но медлишь (риск флага в концовке);")
    w.w("     • ΔGS ∈ [−30; +30] (равенство) — оптимальный ритм «точность = скорость»;")
    w.w("     • ΔGS < −30 (занижение) — перекос в скорость: при Win% > 55% это прессинг по времени, при низком Win% — спешка и зевки.")
    w.w("  💡 ΔAS = AggrR − StateR (баланс напора и устойчивости):")
    w.w("     • ΔAS > +40 (превышение) — агрессивный перекос: активно атакуешь, но теряешь перевес (+3.0) или сыплешься каскадом;")
    w.w("     • ΔAS ∈ [−30; +30] (равенство) — гармония инициативы и выдержки (создаёшь столько угроз, сколько способен удержать);")
    w.w("     • ΔAS < −40 (занижение) — «режим Бухгалтера»: железная реализация без тильта, но дефицит инициативы (игра вторым номером).")
    w.w()

    # 3.5. Мониторинг динамики (снапшоты)
    snapshots = monitoring_snapshot()
    if snapshots:
        w.w("🎯 МОНИТОРИНГ ДИНАМИКИ (Снапшоты - 1/7/30/90 дней):")
        w.w(f"  {'Окно':<10} {'Дата':<12} {'CombR':<7} {'Δ':<6} {'StdDev':<7} {'Агрессия':<9} {'Охотник%'}")
        w.w("  " + "-" * 60)
        for s in snapshots:
            mark = "🔥" if s["window"] == "Сегодня" else "  "
            delta_val = int(s.get("delta")) if s.get("delta") is not None else 0
            delta_str = _fmt_signed(delta_val)
            combr = s.get("combined_r") or 0
            stddev = s.get("stddev_acpl") or 0
            agg = s.get("aggression") or 0
            hunter = s.get("hunter_pct") or 0
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
            name = a["opening"][:30] + ".." if len(a["opening"]) > 30 else a["opening"]
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
    w.w("🎯 ВЕРДИКТ (CombR vs Дом, ΔGS и Perf):")
    day90 = next((d for d in dynamics if d.get("window") == "90 дней"), None)
    day1 = next((d for d in dynamics if d.get("window") == "1 день"), None)

    if day90:
        d_90 = day90.get("delta", 0)
        d_gs_90 = day90.get("delta_gs", 0)
        w.w(f"  📌 90 дней: CombR = {day90.get('combined_r', 0)} vs Дом = {day90.get('home', 0)} (Δ {_fmt_signed(d_90)}).")
        if abs(d_gs_90) < 30:
            w.w(f"  ✅ Баланс темпа (90д): идеальный коридор (ΔGS {_fmt_signed(d_gs_90)}).")
        elif d_gs_90 > 30:
            w.w(f"  ⚠️ Баланс темпа (90д): перекос в точность (ΔGS {_fmt_signed(d_gs_90)}). Ты играешь слишком медленно.")
        else:
            w.w(f"  ⚠️ Баланс темпа (90д): перекос в скорость (ΔGS {_fmt_signed(d_gs_90)}). Ты играешь слишком быстро.")

    if day1 and day90:
        d_1 = day1.get("delta", 0)
        d_gs_1 = day1.get("delta_gs", 0)
        win_1 = day1.get("win_rate", 0)
        acpl_1 = day1.get("acpl", 0)
        acpl_90 = day90.get("acpl", 57.4)
        w.w(f"  🔥 Сегодня: CombR = {day1.get('combined_r', 0)} (Δ {_fmt_signed(d_1)} к дому дня, Perf = {day1.get('perf', 0)}).")
        if d_gs_1 > 50:
            w.w(f"     ⚠️ Замедление темпа (ΔGS {_fmt_signed(d_gs_1)}): ускорься ближе к {day90.get('avg_time', 1.15):.2f} сек/ход.")
        elif d_gs_1 < -30:
            if win_1 > 55.0 and acpl_1 <= acpl_90 + 6.0:
                w.w(f"     ⚡ Прессинг по времени (ΔGS {_fmt_signed(d_gs_1)}): высокий темп при Win% {win_1:.1f}% — соперники не успевают за ритмом.")
            else:
                w.w(f"     ⚠️ Спешка (ΔGS {_fmt_signed(d_gs_1)}): точность просела (ACPL {acpl_1:.1f} против {acpl_90:.1f} за 90д) — сделай паузу 15 мин.")
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
            print(line)
            f.write(str(line) + "\n")
        build_index(type("W", (), {"w": staticmethod(w)})())
    print(f"\n✅ {path}")