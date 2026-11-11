# ============================================================
# analysis/openings/planner_output.py — Вывод planner (v19.1)
# run_opening_planner() — весь вывод через report_context
# ============================================================
import os
import sqlite3
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from analysis.common import report_context
from .common import REPORTS_DIR, PLAYER
from .planner import (
    FenCache, EnginePool, analyze_opening, load_codex_rules,
    STOCKFISH_PATH, STOCKFISH_CACHE, DB_FILE, NUM_ENGINES, NUM_WORKERS,
)
from .advice import generate_advice, build_summary

try:
    from core.стили import get_opponent_style_map
except ImportError:
    def get_opponent_style_map(conn, player):
        return {}

try:
    from tqdm import tqdm
    HAVE_TQDM = True
except ImportError:
    HAVE_TQDM = False

TRAINING_DIR = os.path.join(REPORTS_DIR, "opening_training")


def run_opening_planner():
    if not PLAYER:
        print("⚠️ В config.json не указан 'player' — planner пропущен.")
        return

    # Импортируем глобалы из planner для записи
    from . import planner as P

    P.FEN_CACHE = FenCache(STOCKFISH_CACHE)
    if os.path.exists(STOCKFISH_PATH):
        P.ENGINE_POOL = EnginePool(NUM_ENGINES)
        print(f"✅ Stockfish: {len(P.ENGINE_POOL.engines)} копий")
    else:
        P.ENGINE_POOL = None
        print("⚠️ Stockfish отключён")

    conn = sqlite3.connect(DB_FILE)
    codex_rules = load_codex_rules()
    style_map = get_opponent_style_map(conn, PLAYER)
    print(f"🎭 Стилей соперников: {len(style_map)}")

    cur = conn.cursor()
    cur.execute("""
        SELECT substr(eco, 1, 3) as eco3, COUNT(*) as cnt
        FROM games WHERE is_lag=0 AND is_cheater=0 AND eco IS NOT NULL
        GROUP BY eco3 HAVING cnt >= 10 ORDER BY cnt DESC
    """)
    ecos = [r[0] for r in cur.fetchall()]
    conn.close()

    if not ecos:
        print("❌ Нет дебютов с >= 10 партиями.")
        return

    results = []
    print(f"🚀 Параллельный анализ ({NUM_WORKERS} потоков)...")
    try:
        with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
            futures = {
                executor.submit(analyze_opening, eco, codex_rules, style_map): eco
                for eco in ecos
            }
            iterator = as_completed(futures)
            if HAVE_TQDM:
                iterator = tqdm(iterator, total=len(ecos), desc="Дебюты")
            for future in iterator:
                eco = futures[future]
                try:
                    r = future.result()
                    if r:
                        results.append(r)
                except Exception as e:
                    print(f"  ❌ {eco}: {e}")
    except KeyboardInterrupt:
        print("\n⚠️ Прервано пользователем")
    finally:
        if P.ENGINE_POOL:
            P.ENGINE_POOL.close()
            print("🔒 Stockfish закрыт")
        if P.FEN_CACHE:
            P.FEN_CACHE.save()

    results.sort(key=lambda x: x["eco"])

    with report_context("opening_planner") as w:
        w.w_separator(title="🎯 OPENING PLANNER v4.9 — ФИНАЛ")
        w.w(f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        w.w(f"Игрок: {PLAYER}")
        w.w(f"Stockfish: {'✅ ' + str(len(P.ENGINE_POOL.engines)) + ' копий' if P.ENGINE_POOL else '❌ Отключён'}")
        w.w(f"Потоков: {NUM_WORKERS}")
        w.w(f"FEN-кэш: {len(P.FEN_CACHE.data) if P.FEN_CACHE else 0} позиций")
        w.w("")

        for r in results:
            w.w_separator(title=f"♟️ {r['eco']} ({r['total']} партий, {r['winrate']:.1f}% побед)")

            # ACPL
            w.w(f"  ACPL: дебют {r['acpl_op']:.0f} | мит {r['acpl_mid']:.0f} | энд {r['acpl_end']:.0f}")
            if r.get('stddev'):
                w.w(f"  StdDev: {r['stddev']:.0f}")
            w.w(f"  Eval после дебюта: {r['eval_after_opening']:+.1f}")

            # Проблемная фаза
            worst_phase = "дебют"
            worst_val = r['acpl_op']
            if r['acpl_mid'] > worst_val:
                worst_phase = "миттельшпиль"
                worst_val = r['acpl_mid']
            if r['acpl_end'] > worst_val:
                worst_phase = "эндшпиль"
                worst_val = r['acpl_end']
            w.w(f"  ⚠️ Проблемная фаза: {worst_phase} (ACPL {worst_val:.0f})")

            # ACPL миттельшпиля
            if r.get('acpl_win_mid') or r.get('acpl_loss_mid'):
                w.w(f"\n  📊 ACPL миттельшпиля: победы {r['acpl_win_mid']:.0f} / "
                    f"поражения {r['acpl_loss_mid']:.0f} "
                    f"(Δ {r['acpl_loss_mid'] - r['acpl_win_mid']:+.0f})")

            # Доминирование
            if r.get("dominance"):
                w.w(f"\n  🥊 Доминирование: белые {r['dominance'].get('Белые', 0):.1f}, "
                    f"чёрные {r['dominance'].get('Чёрные', 0):.1f}")

            # По цвету
            if r.get("by_color"):
                w.w(f"\n  ♔ По цвету:")
                for color, cnt, wins_c, acpl_c in r["by_color"]:
                    wr_c = (wins_c or 0) / cnt * 100 if cnt else 0
                    w.w(f"     {color:<10}: {cnt} партий, {wr_c:.0f}% побед, ACPL {acpl_c or 0:.0f}")

            # Проблемные ходы
            if r.get('bad_moves'):
                w.w(f"\n  🔴 Проблемные ходы:")
                for move_num, cnt, avg_loss in r['bad_moves']:
                    w.w(f"     Ход {move_num}: {cnt} раз, потеря {avg_loss:.0f} CP")

            # Окно уязвимости
            if r.get("vulnerability_window"):
                w.w(f"\n  🎯 Окно уязвимости:")
                for window, cnt in r["vulnerability_window"]:
                    w.w(f"     {window:<10}: {cnt} зевков")

            # Линия-убийца
            if r.get("killer_line"):
                line, cnt = r["killer_line"]
                w.w(f"\n  💀 Линия-убийца: {line[:60]} ({cnt} зевков)")

            # Топ-3 линии по сливу
            if r.get("sliv_lines"):
                w.w(f"\n  💸 Топ-3 линии по сливу +3.0:")
                for line, total_l, lost in r["sliv_lines"]:
                    pct = lost / total_l * 100 if total_l else 0
                    w.w(f"     {line[:50]:<52} {lost}/{total_l} ({pct:.0f}%)")

            # Точка невозврата
            if r.get("point_of_no_return"):
                w.w(f"\n  🚫 Точка невозврата:")
                for move_num, blunders, loss_rate in r["point_of_no_return"]:
                    w.w(f"     После {move_num}-го хода: {loss_rate:.0f}% поражений ({blunders} зевков)")

            # Паттерны
            if r.get('patterns'):
                w.w(f"\n  🧩 Паттерны:")
                for tag, cnt, wr in r['patterns']:
                    w.w(f"     {tag:<15}: {cnt} раз, winrate {wr or 0:.0f}%")

            # По рейтингу
            if r.get("by_rating"):
                w.w(f"\n  👥 По рейтингу:")
                for rng, cnt, wins_r, acpl_r in r['by_rating']:
                    wr_r = (wins_r or 0) / cnt * 100 if cnt else 0
                    w.w(f"     {rng:<12}: {cnt} партий, {wr_r:.0f}% побед, ACPL {acpl_r or 0:.0f}")

            # Слив +3.0
            sliv = r.get("sliv")
            if sliv and sliv[0] > 0:
                sliv_pct = (sliv[1] or 0) / sliv[0] * 100
                w.w(f"\n  💸 Слив +3.0: {sliv[1]} из {sliv[0]} ({sliv_pct:.0f}%)")

            # Тренд
            if r.get('weekly'):
                w.w(f"\n  📈 Тренд:")
                prev_wr = None
                for week, cnt, wins_w in r['weekly']:
                    wr_w = wins_w / cnt * 100 if cnt else 0
                    mark = ""
                    if prev_wr is not None:
                        d = wr_w - prev_wr
                        mark = " ↑" if d > 5 else (" ↓" if d < -5 else " →")
                    w.w(f"     {week}: {cnt}п, {wr_w:.0f}%{mark}")
                    prev_wr = wr_w

            # Просрочки
            if r.get('timeouts', 0) > 0:
                w.w(f"\n  ⏰ Просрочки: {r['timeouts']} ({r['timeout_pct']:.1f}%)")

            # Лучшая/худшая партия
            if r.get("peak_best"):
                w.w(f"\n  🏆 Лучшая партия: перф {r['peak_best'][2]} (сопер {r['peak_best'][1]})")
                w.w(f"     {r['peak_best'][0]}")
            if r.get("peak_worst"):
                w.w(f"  🥀 Худшая партия: перф {r['peak_worst'][2]} (сопер {r['peak_worst'][1]})")
                w.w(f"     {r['peak_worst'][0]}")

            # По стилю
            if r.get("by_style"):
                w.w(f"\n  🎭 По стилю:")
                for style, d in r["by_style"]:
                    wr_s = d["w"] / d["n"] * 100
                    w.w(f"     {style:<12}: {d['n']} партий, {wr_s:.0f}% побед")

            # Деревья
            for color_label, tree in [("За белых", r.get("tree_white")),
                                       ("За чёрных", r.get("tree_black"))]:
                if tree:
                    w.w(f"\n  🌳 Дерево {color_label} (топ-5):")
                    for key, stats in sorted(tree.items(), key=lambda x: -x[1]["n"])[:5]:
                        wr_t = stats["w"] / stats["n"] * 100 if stats["n"] else 0
                        w.w(f"     {key[:45]:<47} {stats['n']}п, {wr_t:.0f}%")

            # Проблемные позиции
            if r.get("bad_positions"):
                w.w(f"\n  🎯 Проблемные позиции (топ-5):")
                for i, pos in enumerate(r['bad_positions'], 1):
                    w.w(f"     #{i}. {pos['white']} vs {pos['black']} ({pos['date']})")
                    w.w(f"         Ход {pos['move_num']}, потеря {pos['loss_cp']} CP")
                    w.w(f"         FEN: {pos['fen']}")
                    if pos['best_move']:
                        w.w(f"         💡 Лучший ход: {pos['best_move']}")
                    w.w(f"         Ссылка на партию: {pos['url']}")
                    w.w(f"         Тренируй: https://lichess.org/analysis/standard/{pos['fen'].replace(' ', '_')}")

            # Совет Кодекса
            if r.get("codex_advice"):
                w.w(f"\n  📖 Совет Кодекса:")
                for rule in r['codex_advice']:
                    w.w(f"     [{rule.get('tag')}] {rule.get('name')}")
                    w.w(f"     💡 {rule.get('advice')}")
                    if rule.get('mantra'):
                        w.w(f"     🗣️ «{rule['mantra']}»")

            # Рекомендации тренера
            advice = generate_advice(r)
            if advice:
                w.w(f"\n  💡 РЕКОМЕНДАЦИИ ТРЕНЕРА:")
                for a in advice:
                    w.w(f"     • {a}")

            # Домашка
            if r.get("bad_positions"):
                hw_file = os.path.join(TRAINING_DIR, f"{r['eco']}.txt")
                with open(hw_file, "w", encoding="utf-8") as hw:
                    hw.write(f"# Домашняя работа: {r['eco']}\n")
                    hw.write(f"# Winrate: {r['winrate']:.1f}%\n")
                    hw.write(f"# ACPL: деб {r['acpl_op']:.0f} / мит {r['acpl_mid']:.0f} / энд {r['acpl_end']:.0f}\n")
                    hw.write(f"# Eval после дебюта: {r['eval_after_opening']:+.1f}\n")
                    if r.get("killer_line"):
                        line, cnt = r["killer_line"]
                        hw.write(f"# Линия-убийца: {line} ({cnt} зевков)\n")
                    if r.get("vulnerability_window"):
                        worst = max(r["vulnerability_window"], key=lambda x: x[1])
                        hw.write(f"# Окно уязвимости: {worst[0]} ({worst[1]} зевков)\n")
                    if r.get("point_of_no_return"):
                        move_num, blunders, loss_rate = r["point_of_no_return"][0]
                        hw.write(f"# Точка невозврата: после {move_num}-го хода ({loss_rate:.0f}% поражений)\n")
                    hw.write("\n")
                    for i, pos in enumerate(r["bad_positions"], 1):
                        hw.write(f"# Позиция {i}: Ход {pos['move_num']}, потеря {pos['loss_cp']} CP\n")
                        hw.write(f"FEN: {pos['fen']}\n")
                        if pos['best_move']:
                            hw.write(f"Лучший ход (Stockfish): {pos['best_move']}\n")
                        hw.write(f"Ссылка: https://lichess.org/analysis/standard/{pos['fen'].replace(' ', '_')}\n\n")

        # Резюме
        w.w(build_summary(results))

    print(f"\n✅ Planner: {os.path.join(REPORTS_DIR, 'opening_planner.txt')}")
    print(f"✅ Домашняя работа: {TRAINING_DIR}/")
    if P.FEN_CACHE:
        print(f"✅ FEN-кэш: {STOCKFISH_CACHE} ({len(P.FEN_CACHE.data)} позиций)")