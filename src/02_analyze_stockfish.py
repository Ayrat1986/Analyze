# ============================================================
# 02_analyze_stockfish.py — v25.5 (Clean: No hacks, no autosync)
# ============================================================
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from importlib import import_module

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, SRC_DIR)

import _common
from analysis.constants import DEPTH
from analysis.cache import (
    load_cache, save_cache, game_cache_ok, cache_needs_recalc, CACHE_SCHEMA_VERSION
)
from analysis.game import analyze_game
from analysis.engine_pool import EnginePool

fetch_api = import_module("01_fetch_chess_api")

STOCKFISH_CACHE_FILE = str(_common.BASE_DIR / "data" / "stockfish_cache.json")
STOCKFISH_PATH = _common.CONFIG.get("stockfish_path", "")

NUM_ENGINES = 4
THREADS_PER_ENGINE = 1
HASH_MB = 32
SAVE_EVERY = 5


def _analyze_one(pool: EnginePool, game_data: dict, player: str):
    url = game_data.get("url", "")
    engine = pool.get(timeout=30.0)
    if engine is None:
        return (url, None, "Не удалось взять движок из пула (таймаут)")
    
    try:
        result = analyze_game(game_data, engine, player)
        pool.mark_processed()
        return (url, result, None)
    except Exception as e:
        return (url, None, str(e))
    finally:
        pool.put(engine)


def main():
    print("=" * 60)
    print(" 02_analyze_stockfish.py — Stockfish-анализ (v25.5)")
    print("=" * 60)

    if not os.path.exists(STOCKFISH_PATH):
        print(f"❌ Stockfish не найден: {STOCKFISH_PATH}")
        return

    if not fetch_api.PLAYER:
        print("❌ В config.json не указан 'player'.")
        return

    cache = load_cache(STOCKFISH_CACHE_FILE)
    print(f"📂 В кэше Stockfish уже: {len(cache)} партий")

    force_recalc = cache_needs_recalc(cache)
    if cache.get("_schema_version") != CACHE_SCHEMA_VERSION:
        force_recalc = True
        print(f"🔄 Версия схемы кэша изменилась ({cache.get('_schema_version')} -> {CACHE_SCHEMA_VERSION}).")
        
    if force_recalc:
        print("🔄 Кэш требует пересчёта — будут пересчитаны ВСЕ партии.")

    # Получаем ВСЕ партии (с PGN и без), чтобы честно посчитать отсев
    games_all = fetch_api.get_games_from_cache(
        player=fetch_api.PLAYER,
        days=fetch_api.DAYS_TO_FETCH,
        time_class=fetch_api.TIME_CLASS,
        max_base=fetch_api.MAX_BULLET_BASE_TIME,
        require_pgn=False,
    )
    
    games_no_pgn = [g for g in games_all if not g.get("pgn")]
    games_with_pgn = [g for g in games_all if g.get("pgn")]

    print(f"📥 Загружено из API-кэша: {len(games_all)} партий")
    if games_no_pgn:
        print(f"⚠️  Из них БЕЗ PGN: {len(games_no_pgn)} партий (они не будут проанализированы).")
        print(f"   Пример URL без PGN: {games_no_pgn[0].get('url')}")
    print(f"✅ С PGN: {len(games_with_pgn)} партий")

    to_analyze = []
    skipped_ok = 0
    
    for g in games_with_pgn:
        url = g.get("url", "")
        if not url:
            continue
        if not force_recalc and url in cache and game_cache_ok(cache[url]):
            skipped_ok += 1
            continue
        to_analyze.append(g)

    print(f"🎯 К анализу: {len(to_analyze)} партий")
    print(f"⏩ Уже в кэше (пропущено): {skipped_ok} партий")

    if not to_analyze:
        print("✅ Все партии с PGN уже в кэше Stockfish. Нечего делать.")
        return

    print(f"\n🚀 Запуск {NUM_ENGINES} движков Stockfish (Hash {HASH_MB}MB)...")
    try:
        pool = EnginePool(
            STOCKFISH_PATH,
            size=NUM_ENGINES,
            threads_per_engine=THREADS_PER_ENGINE,
            hash_mb=HASH_MB,
        )
    except RuntimeError as e:
        print(f"❌ {e}")
        return

    new_count = 0
    errors = 0
    total = len(to_analyze)
    start_time = time.time()
    last_save = 0

    try:
        with ThreadPoolExecutor(max_workers=NUM_ENGINES) as executor:
            futures = {
                executor.submit(_analyze_one, pool, g, fetch_api.PLAYER): g
                for g in to_analyze
            }

            for i, future in enumerate(as_completed(futures), 1):
                url, result, error = future.result()

                if error:
                    errors += 1
                    print(f"  {i}/{total}: ❌ {url[-20:]} — {error}")
                    continue

                cache[url] = result
                new_count += 1

                acpl_val = result.get('acpl', 0)
                elapsed = time.time() - start_time
                avg_per_game = elapsed / i
                eta = avg_per_game * (total - i)
                print(f"  {i}/{total}: ✅ ACPL {acpl_val:.0f} | "
                      f"ETA {eta/60:.1f} мин (ср. {avg_per_game:.1f} сек/партия)")

                if i - last_save >= SAVE_EVERY:
                    cache["_schema_version"] = CACHE_SCHEMA_VERSION
                    save_cache(STOCKFISH_CACHE_FILE, cache)
                    last_save = i

    except KeyboardInterrupt:
        print("\n⚠️ Прервано пользователем. Сохраняю что есть...")
    finally:
        cache["_schema_version"] = CACHE_SCHEMA_VERSION
        save_cache(STOCKFISH_CACHE_FILE, cache)
        pool.close()

    elapsed_total = time.time() - start_time
    print(f"\n✅ Готово за {elapsed_total/60:.1f} мин. Кэш: {STOCKFISH_CACHE_FILE}")
    print(f"   Новых проанализировано: {new_count}, ошибок: {errors}")
    if to_analyze:
        print(f"   Средняя скорость: {elapsed_total/len(to_analyze):.2f} сек/партия")


if __name__ == "__main__":
    main()