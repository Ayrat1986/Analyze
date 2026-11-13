# ============================================================
# 02_analyze_stockfish.py — v25.0
# P2: HASH_MB=32 (было 64) — 4 движка × 32 = 128MB (безопасно для Windows).
# P2: SAVE_EVERY=5 (было 20) — потеря при крэше ≤4 партии, не 19.
# A1: pool.mark_processed() после успешного анализа.
# ============================================================
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from importlib import import_module

# Добавляем корень проекта и папку src в пути
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, SRC_DIR)

import _common
from analysis.constants import DEPTH
from analysis.cache import load_cache, save_cache, game_cache_ok, cache_needs_recalc
from analysis.game import analyze_game
from analysis.engine_pool import EnginePool

fetch_api = import_module("01_fetch_chess_api")

STOCKFISH_CACHE_FILE = str(_common.BASE_DIR / "data" / "stockfish_cache.json")
STOCKFISH_PATH = _common.CONFIG.get("stockfish_path", "")

# Настройки параллелизации
NUM_ENGINES = 4          # 4 движка × 1 поток = 4 CPU
THREADS_PER_ENGINE = 1   # 1 поток на движок
HASH_MB = 32             # P2: было 64, теперь 32MB (4×32 = 128MB)
SAVE_EVERY = 5           # P2: было 20, теперь каждые 5 партий


def _analyze_one(pool: EnginePool, game_data: dict, player: str):
    """
    Анализ одной партии с автоматическим возвратом движка в пул.
    Возвращает (url, result_or_None, error_str_or_None).
    """
    url = game_data.get("url", "")
    engine = pool.get(timeout=30.0)
    if engine is None:
        return (url, None, "Не удалось взять движок из пула (таймаут)")
    
    try:
        result = analyze_game(game_data, engine, player)
        pool.mark_processed()  # A1: для диагностики
        return (url, result, None)
    except Exception as e:
        return (url, None, str(e))
    finally:
        pool.put(engine)


def main():
    print("=" * 60)
    print(" 02_analyze_stockfish.py — Stockfish-анализ (v25.0, параллельный)")
    print("=" * 60)

    if not os.path.exists(STOCKFISH_PATH):
        print(f"❌ Stockfish не найден: {STOCKFISH_PATH}")
        print("   Проверь 'stockfish_path' в data/config.json")
        return

    if not fetch_api.PLAYER:
        print("❌ В config.json не указан 'player'.")
        return

    cache = load_cache(STOCKFISH_CACHE_FILE)
    print(f"📂 В кэше уже: {len(cache)} партий")

    force_recalc = cache_needs_recalc(cache)
    if force_recalc:
        print("🔄 Кэш требует пересчёта — будут пересчитаны ВСЕ партии.")

    games = fetch_api.get_games_from_cache(
        player=fetch_api.PLAYER,
        days=fetch_api.DAYS_TO_FETCH,
        time_class=fetch_api.TIME_CLASS,
        max_base=fetch_api.MAX_BULLET_BASE_TIME,
        require_pgn=True,
    )
    print(f"📥 Загружено партий из API-кэша: {len(games)}")

    if not games:
        print("❌ Нечего анализировать.")
        return

    # Отбираем только те, что нужно анализировать
    to_analyze = []
    for g in games:
        url = g.get("url", "")
        if not url:
            continue
        if not force_recalc and url in cache and game_cache_ok(cache[url]):
            continue
        to_analyze.append(g)

    print(f"🎯 К анализу: {len(to_analyze)} партий (пропущено {len(games) - len(to_analyze)} из кэша)")

    if not to_analyze:
        print("✅ Все партии уже в кэше. Нечего делать.")
        return

    # Запускаем пул
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

                # Батчинг save_cache (P2: было 20)
                if i - last_save >= SAVE_EVERY:
                    save_cache(STOCKFISH_CACHE_FILE, cache)
                    last_save = i

    except KeyboardInterrupt:
        print("\n⚠️ Прервано пользователем. Сохраняю что есть...")
    finally:
        # Финальное сохранение (независимо от результата)
        save_cache(STOCKFISH_CACHE_FILE, cache)
        pool.close()

    elapsed_total = time.time() - start_time
    print(f"\n✅ Готово за {elapsed_total/60:.1f} мин. Кэш: {STOCKFISH_CACHE_FILE}")
    print(f"   Новых: {new_count}, ошибок: {errors}")
    if to_analyze:
        print(f"   Средняя скорость: {elapsed_total/len(to_analyze):.2f} сек/партия")


if __name__ == "__main__":
    main()