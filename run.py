# ============================================================
# src/run.py — Оркестратор конвейера (v26.4)
# FIX: Надежный импорт sync_to_turso (проверка sys.path).
# ============================================================
import os
import sys
import time
import argparse
import subprocess
from datetime import datetime

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(CURRENT_DIR) if os.path.basename(CURRENT_DIR).lower() == "src" else CURRENT_DIR
SRC_DIR = os.path.join(BASE_DIR, "src")

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import _common
from analysis.utils.build_cache import is_up_to_date, mark_completed, cleanup_old_cache

DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")
SF_CACHE = str(_common.BASE_DIR / "data" / "stockfish_cache.json")
API_CACHE = str(_common.BASE_DIR / "data" / "chess_api_cache.json")
RULES_FILE = str(_common.BASE_DIR / "data" / "codex_rules.json")
CONFIG_FILE = str(_common.BASE_DIR / "data" / "config.json")
LOCK_FILE = os.path.join(BASE_DIR, "run.py.lock")

STEPS = {
    0:  ("Data quality",   "00_data_quality.py",       False, [DB_FILE, CONFIG_FILE], False),
    1:  ("Fetch API",      "01_fetch_chess_api.py",    False, [API_CACHE, CONFIG_FILE], False),
    2:  ("Stockfish",      "02_analyze_stockfish.py",  False, [API_CACHE, CONFIG_FILE], False),
    3:  ("Migrate SQLite", "03_migrate_sqlite.py",     False, [SF_CACHE, CONFIG_FILE], False),
    4:  ("Export CSV",     "04_export_csv.py",         False, [DB_FILE, CONFIG_FILE], False),
    5:  ("Openings",       "05_openings.py",           True,  [DB_FILE, CONFIG_FILE], False),
    6:  ("Middlegame",     "06_middlegame.py",         True,  [DB_FILE, CONFIG_FILE], False),
    7:  ("Endgame",        "07_endgame.py",            False, [DB_FILE, CONFIG_FILE], False),
    8:  ("Psych Focus",    "08_psych_focus.py",        False, [DB_FILE, CONFIG_FILE], False),
    9:  ("Psych State",    "09_psych_state.py",        False, [DB_FILE, CONFIG_FILE], False),
    10: ("Psych Rating",   "10_psych_rating.py",       False, [DB_FILE, CONFIG_FILE], False),
    11: ("Opponents",      "11_psych_opponents.py",    False, [DB_FILE, CONFIG_FILE], False),
    12: ("Coach",          "12_coach.py",              False, [DB_FILE, RULES_FILE, CONFIG_FILE], False),
    13: ("Dashboard",      "13_dashboard_final.py",    False, [DB_FILE, CONFIG_FILE], True),
}

def check_lock():
    if os.path.exists(LOCK_FILE):
        print(f"\n🛑 ОШИБКА: Найден файл {LOCK_FILE}.")
        print(f"   Если вы уверены, что ничего не работает, удалите файл: {LOCK_FILE}")
        return False
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))
    return True

def release_lock():
    if os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)

def run_smoke_test():
    dash_dir = os.path.join(str(_common.REPORTS_DIR), "dashboards")
    expected_files = [f for f in os.listdir(dash_dir) if f.endswith(".txt")] if os.path.exists(dash_dir) else []
    if len(expected_files) < 8:
        print(f"⚠️ SMOKE-TEST FAIL: Найдено {len(expected_files)} из 8 файлов дашбордов.")
        return
    for fname in expected_files:
        fpath = os.path.join(dash_dir, fname)
        if os.path.getsize(fpath) < 100:
            print(f"⚠️ SMOKE-TEST FAIL: Файл {fname} слишком мал (возможно, пустой).")
            return
    print("✅ SMOKE-TEST OK: Все дашборды сгенерированы и не пусты.")

def _auto_sync_turso():
    """Автоматически выгружает обновлённую chess.db в Turso."""
    try:
        # Защита для GitHub Actions: гарантируем, что корень проекта в sys.path
        if BASE_DIR not in sys.path:
            sys.path.insert(0, BASE_DIR)
        from web_dashboard.utils.sync_to_turso import sync_if_needed
        sync_if_needed(quiet=False)
    except Exception as e:
        print(f"⚠️ Автосинхронизация с Turso не выполнена: {e}")

def _run_step(step_key, name, filename, fast_mode, force=False):
    step_info = STEPS[step_key]
    is_heavy = step_info[2]
    deps = step_info[3]
    always_run = step_info[4]

    if fast_mode and is_heavy:
        print(f"  ⏩ Пропущен (--fast): {name}")
        return True, 0.0

    if not force and not always_run and is_up_to_date(name, deps):
        print(f"  ⏩ Пропущен (нет изменений): {name}")
        return True, 0.0

    print(f"\n{'='*60}")
    print(f"  ШАГ {step_key}: {name} ({filename})")
    print(f"{'='*60}")

    _common.log_start(filename)
    start_time = time.time()
    script_path = os.path.join(SRC_DIR, filename)

    cmd = [sys.executable, script_path]
    if force:
        cmd.append("--force")

    try:
        result = subprocess.run(cmd, check=True, capture_output=False, text=True)
        elapsed = time.time() - start_time
        print(f"\n✅ ШАГ {step_key} завершен за {elapsed:.1f} сек")
        _common.log_end(filename, "OK")
        if not always_run:
            mark_completed(name, deps)
        return True, elapsed
    except subprocess.CalledProcessError as e:
        elapsed = time.time() - start_time
        print(f"\n❌ ОШИБКА в шаге {step_key} ({elapsed:.1f} сек): код {e.returncode}")
        _common.log_end(filename, f"ERROR: subprocess code {e.returncode}")
        return False, elapsed
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"\n❌ ОШИБКА в шаге {step_key} ({elapsed:.1f} сек): {e}")
        _common.log_end(filename, f"ERROR: {e}")
        return False, elapsed

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", type=str, default="all")
    parser.add_argument("--keep-going", action="store_true")
    parser.add_argument("--fast", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.steps == "all":
        steps_to_run = sorted(STEPS.keys())
    else:
        steps_to_run = []
        for s in args.steps.split(","):
            s = s.strip()
            try:
                key = int(s)
            except ValueError:
                print(f"⚠️ Неизвестный шаг: {s!r} (пропущен)")
                continue
            if key in STEPS:
                steps_to_run.append(key)
            else:
                print(f"⚠️ Неизвестный шаг: {s!r} (пропущен)")

    deleted = cleanup_old_cache(days=30)
    if deleted > 0:
        print(f"🧹 Очищено устаревших хэшей: {deleted}")

    if args.dry_run:
        print("\n" + "=" * 60)
        print(" ПЛАН ЗАПУСКА (--dry-run)")
        print("=" * 60)
        for s in steps_to_run:
            name, filename, is_heavy, deps, always_run = STEPS[s]
            skip_fast = " (--fast)" if args.fast and is_heavy else ""
            skip_cache = " (нет изменений)" if not args.force and not always_run and is_up_to_date(name, deps) else ""
            print(f"  {s:>2}. {name:<25} {filename}{skip_fast}{skip_cache}")
        return

    if not check_lock():
        return

    try:
        print("=" * 60)
        print(" ЗАПУСК КОНВЕЙЕРА (v26.4)")
        print("=" * 60)
        print(f"Игрок: {_common.CONFIG.get('player', '?')}")
        print(f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Режим: {'--fast' if args.fast else 'полный'}")
        print(f"Флаг --force: {'ВКЛ' if args.force else 'ВЫКЛ'}")
        print(f"Шагов: {len(steps_to_run)}")

        total_time = 0.0
        success_count = 0
        fail_count = 0

        for s in steps_to_run:
            name, filename, _, _, _ = STEPS[s]
            ok, elapsed = _run_step(s, name, filename, args.fast, force=args.force)
            total_time += elapsed
            if ok:
                success_count += 1
            else:
                fail_count += 1
                if not args.keep_going:
                    print(f"\n🛑 СТОП: шаг {s} упал. Флаг --keep-going не установлен.")
                    break

        print("\n" + "=" * 60)
        print(" ИТОГИ")
        print("=" * 60)
        print(f"  ✅ Успешно: {success_count}")
        print(f"  ❌ Ошибок:  {fail_count}")
        print(f"  ⏱️  Время:  {total_time:.1f} сек")
        print("=" * 60)

        if 13 in steps_to_run and fail_count == 0:
            run_smoke_test()

        if success_count > 0:
            _auto_sync_turso()

        if fail_count > 0:
            sys.exit(1)

    finally:
        release_lock()

if __name__ == "__main__":
    main()