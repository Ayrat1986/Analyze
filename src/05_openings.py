# ============================================================
# 05_openings.py — ДЕБЮТ (Оркестратор v20.0)
# ============================================================
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, SRC_DIR)

import _common
from analysis.openings import (
    report_openings, report_repertoire, report_openings_winrate_trend,
    report_opening_performance, report_weak_spots_matrix, report_rating_by_opening,
    report_line_anatomy, run_opening_planner
)
from analysis.openings.cheat_sheets import report_opening_cheat_sheets

def main():
    print("=" * 60)
    print(" 05_openings.py — ДЕБЮТ (v20.0)")
    print("=" * 60)

    DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")
    if not os.path.exists(DB_FILE):
        print(f"❌ Не найдена {DB_FILE}. Запусти 03_migrate_sqlite.py.")
        return

    print("\n── 1/3. SQL-отчёты ──")
    report_openings()
    report_repertoire()
    report_openings_winrate_trend()
    report_opening_performance()
    report_weak_spots_matrix()
    report_rating_by_opening()
    report_line_anatomy()

    print("\n── 2/3. Шпаргалки по проблемным дебютам ──")
    report_opening_cheat_sheets()

    print("\n── 3/3. Opening planner (Stockfish) ──")
    run_opening_planner()

if __name__ == "__main__":
    main()