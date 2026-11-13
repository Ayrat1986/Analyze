# ============================================================
# 09_psych_state.py — ЛИЧНОЕ: СОСТОЯНИЕ И РЕЖИМ (v25.0)
# §28: удалены time_report_windows, hours_overview,
#      endurance (report_endurance), daily_checkin (отчёт).
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
        if data:
            write_checkin(data)
        else:
            print("⚠️ Пустой чек-ин.")
        return

    print("=" * 60)
    print(" 09_psych_state.py — ЛИЧНОЕ: СОСТОЯНИЕ И РЕЖИМ (v25.0)")
    print("=" * 60)

    DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")
    if not os.path.exists(DB_FILE):
        print(f"❌ Не найдена {DB_FILE}. Запусти 03_migrate_sqlite.py.")
        return

    print("\n── 1/6. Time Profile (просрочки, менеджмент) ──")
    from analysis.psych_state.time_management import report_time_profile
    report_time_profile()

    print("\n── 2/6. Lag Report (аномалии времени) ──")
    from analysis.psych_state.time_management import report_lag_report
    report_lag_report()

    print("\n── 3/6. Time Target (ЦЕЛЕВОЕ ВРЕМЯ) ──")
    from analysis.psych_state.time_target import report_time_target
    report_time_target()

    print("\n── 4/6. Speed Rating (СКОРОСТЬ → РЕЙТИНГ) ──")
    from analysis.psych_state.speed_rating import report_speed_rating
    report_speed_rating()

    print("\n── 5/6. Combined Rating (GameR + SpeedR) ──")
    from analysis.psych_state.combined_rating import report_combined_rating
    report_combined_rating()

    print("\n── 6/6. Behavior Tracker + Psych Tilt ──")
    from analysis.psych_state.endurance import report_behavior_tracker
    report_behavior_tracker()
    from analysis.psych_state.psych_tilt import run_psych_tilt
    run_psych_tilt()

    print(f"\n✅ Все 6 блоков готовы. Отчёты в: {_common.REPORTS_DIR}")


if __name__ == "__main__":
    main()