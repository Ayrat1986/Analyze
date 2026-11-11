# ============================================================
# 09_psych_state.py — ЛИЧНОЕ: СОСТОЯНИЕ И РЕЖИМ (v19.5)
# ============================================================
import os
import sys
import argparse

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, SRC_DIR)

import _common
from analysis.psych_state.daily_checkin import write_checkin, _parse_checkin


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkin", type=str, default=None,
                        help="Чек-ин: 'сон=7,энергия=6,стресс=3'")
    args = parser.parse_args()

    if args.checkin:
        if not os.path.exists(str(_common.BASE_DIR / "data" / "chess.db")):
            print("❌ Нет базы данных.")
            return
        data = _parse_checkin(args.checkin)
        if data: write_checkin(data)
        else: print("⚠️ Пустой чек-ин.")
        return

    print("=" * 60)
    print(" 09_psych_state.py — ЛИЧНОЕ: СОСТОЯНИЕ И РЕЖИМ (v19.5)")
    print("=" * 60)

    DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")
    if not os.path.exists(DB_FILE):
        print(f"❌ Не найдена {DB_FILE}. Запусти 03_migrate_sqlite.py.")
        return

    print("\n── 1/8. Time Management ──")
    from analysis.psych_state.time_management import run_time_management
    run_time_management()

    print("\n── 2/8. Time Target (ЦЕЛЕВОЕ ВРЕМЯ) ──")
    from analysis.psych_state.time_target import report_time_target
    report_time_target()

    print("\n── 3/8. Speed Rating (СКОРОСТЬ → РЕЙТИНГ) ──")
    from analysis.psych_state.speed_rating import report_speed_rating
    report_speed_rating()

    print("\n── 4/8. Combined Rating (GameR + SpeedR) ──")
    from analysis.psych_state.combined_rating import report_combined_rating
    report_combined_rating()

    print("\n── 5/8. Hours & Days ──")
    from analysis.psych_state.hours_days import run_hours_days
    run_hours_days()

    print("\n── 6/8. Endurance & Sessions ──")
    from analysis.psych_state.endurance import run_endurance
    run_endurance()

    print("\n── 7/8. Psych Tilt ──")
    from analysis.psych_state.psych_tilt import run_psych_tilt
    run_psych_tilt()

    print("\n── 8/8. Daily Check-in ──")
    from analysis.psych_state.daily_checkin import run_daily_checkin
    run_daily_checkin()

    print(f"\n✅ Все 8 блоков готовы. Отчёты в: {_common.REPORTS_DIR}")


if __name__ == "__main__":
    main()