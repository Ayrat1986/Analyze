# ============================================================
# 09_psych_state.py — ЛИЧНОЕ: СОСТОЯНИЕ И РЕЖИМ (v26.6)
# FIX: Добавлен флаг --force (совместимость с run.py v26.2).
# FIX: Исправлены вызовы report_time_profile(conn, w) и
#      report_lag_report(conn, w) через report_context.
# ============================================================
import os
import sys
import argparse

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, SRC_DIR)

import _common
from analysis.common import report_context
from analysis.psych_state.common import _conn


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkin", type=str, default=None, help="Чек-ин: 'сон=7,энергия=6,стресс=3'")
    parser.add_argument("--force", action="store_true", help="Игнорировать кэш")
    args = parser.parse_args()

    if args.checkin:
        if not os.path.exists(str(_common.BASE_DIR / "data" / "chess.db")):
            print("❌ Нет базы данных.")
            return
        from analysis.psych_state.daily_checkin import write_checkin, _parse_checkin
        data = _parse_checkin(args.checkin)
        if data:
            write_checkin(data)
        else:
            print("⚠️ Пустой чек-ин.")
        return

    print("=" * 60)
    print(" 09_psych_state.py — ЛИЧНОЕ: СОСТОЯНИЕ И РЕЖИМ (v26.6)")
    print("=" * 60)

    DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")
    if not os.path.exists(DB_FILE):
        print(f"❌ Не найдена {DB_FILE}. Запусти 03_migrate_sqlite.py.")
        return

    print("\n── 1/7. Time Profile (просрочки, менеджмент) ──")
    from analysis.psych_state.time_management import report_time_profile
    conn = _conn()
    try:
        with report_context("time_profile") as w:
            report_time_profile(conn, w)
    finally:
        conn.close()

    print("\n── 2/7. Lag Report (аномалии времени) ──")
    from analysis.psych_state.time_management import report_lag_report
    conn = _conn()
    try:
        with report_context("lag_report") as w:
            report_lag_report(conn, w)
    finally:
        conn.close()

    print("\n── 3/7. Time Target (ЦЕЛЕВОЕ ВРЕМЯ) ──")
    from analysis.psych_state.time_target import report_time_target
    report_time_target()

    print("\n── 4/7. Speed Rating (СКОРОСТЬ → РЕЙТИНГ) ──")
    from analysis.psych_state.speed_rating import report_speed_rating
    report_speed_rating()

    print("\n── 5/7. Combined Rating (GameR + SpeedR) ──")
    from analysis.psych_state.combined_rating import report_combined_rating
    report_combined_rating()

    print("\n── 6/7. Behavior Tracker + Psych Tilt ──")
    from analysis.psych_state.endurance import report_behavior_tracker
    report_behavior_tracker()
    from analysis.psych_state.psych_tilt import run_psych_tilt
    run_psych_tilt()

    print("\n── 7/7. Clock Checkpoints (Время на 10-60 ходах) ──")
    from analysis.psych_state.time_management import report_clock_checkpoints
    conn = _conn()
    try:
        with report_context("clock_checkpoints") as w:
            report_clock_checkpoints(conn, w)
    finally:
        conn.close()

    print(f"\n✅ Все 7 блоков готовы. Отчёты в: {_common.REPORTS_DIR}")


if __name__ == "__main__":
    main()