# ============================================================
# run.py — Оркестратор конвейера (v25.3)
# v25.2: Изоляция sys.argv для шагов с argparse.
# v25.3: Восстановлено логирование в reports/run_log.txt.
# ============================================================
import os
import sys
import time
import argparse
import traceback
from datetime import datetime

# --- ИСПРАВЛЕНИЕ ПУТЕЙ ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(CURRENT_DIR) == "Analyze":
    BASE_DIR = CURRENT_DIR
    SRC_DIR = os.path.join(CURRENT_DIR, "src")
else:
    SRC_DIR = CURRENT_DIR
    BASE_DIR = os.path.dirname(CURRENT_DIR)

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)
# -------------------------

import _common
from analysis.utils.build_cache import is_up_to_date, mark_completed, cleanup_old_cache

DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")
SF_CACHE = str(_common.BASE_DIR / "data" / "stockfish_cache.json")
API_CACHE = str(_common.BASE_DIR / "data" / "chess_api_cache.json")
RULES_FILE = str(_common.BASE_DIR / "data" / "codex_rules.json")
CONFIG_FILE = str(_common.BASE_DIR / "data" / "config.json")

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

    # Логирование старта (v25.3)
    _common.log_start(filename)
    
    start_time = time.time()
    
    # Изоляция sys.argv
    old_argv = sys.argv.copy()
    sys.argv = [os.path.join(SRC_DIR, filename)]
    
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "mod", os.path.join(SRC_DIR, filename))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if hasattr(mod, "main"):
            mod.main()
        elapsed = time.time() - start_time
        print(f"\n✅ ШАГ {step_key} завершен за {elapsed:.1f} сек")
        
        # Логирование успеха
        _common.log_end(filename, "OK")

        if not always_run:
            mark_completed(name, deps)

        return True, elapsed
    except SystemExit as e:
        elapsed = time.time() - start_time
        if e.code == 0:
            print(f"\n✅ ШАГ {step_key} завершен за {elapsed:.1f} сек (sys.exit 0)")
            _common.log_end(filename, "OK (sys.exit)")
            return True, elapsed
        else:
            print(f"\n❌ ОШИБКА в шаге {step_key} ({elapsed:.1f} сек): sys.exit {e.code}")
            _common.log_end(filename, f"ERROR: sys.exit {e.code}")
            return False, elapsed
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"\n❌ ОШИБКА в шаге {step_key} ({elapsed:.1f} сек): {e}")
        traceback.print_exc()
        # Логирование ошибки
        _common.log_end(filename, f"ERROR: {e}")
        return False, elapsed
    finally:
        sys.argv = old_argv

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", type=str, default="all", help="Шаги через запятую")
    parser.add_argument("--keep-going", action="store_true", help="Не останавливаться при ошибке")
    parser.add_argument("--fast", action="store_true", help="Пропустить тяжелые шаги")
    parser.add_argument("--force", action="store_true", help="Игнорировать кэш")
    parser.add_argument("--dry-run", action="store_true", help="Показать план без запуска")
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
        print(f"\nВсего шагов: {len(steps_to_run)}")
        return

    print("=" * 60)
    print(" ЗАПУСК КОНВЕЙЕРА (v25.3)")
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

if __name__ == "__main__":
    main()