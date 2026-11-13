# ============================================================
# 05_openings.py — ДЕБЮТ (Оркестратор v25.0)
# §28: удалены report_openings, openings_winrate_trend,
#      opening_performance, weak_spots_matrix, rating_by_opening.
# Оставлены: opening_planner, repertoire, line_anatomy, cheat_sheets.
# ============================================================
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, SRC_DIR)

import _common
from analysis.openings import (
    report_repertoire,
    report_line_anatomy,
    run_opening_planner,
)
from analysis.openings.cheat_sheets import report_opening_cheat_sheets


def main():
    print("=" * 60)
    print(" 05_openings.py — ДЕБЮТ (v25.0)")
    print("=" * 60)

    DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")
    if not os.path.exists(DB_FILE):
        print(f"❌ Не найдена {DB_FILE}. Запусти 03_migrate_sqlite.py.")
        return

    print("\n── 1/4. Репертуар ──")
    report_repertoire()

    print("\n── 2/4. Анатомия линий (топ-6 ходов) ──")
    report_line_anatomy()

    print("\n── 3/4. Шпаргалки по проблемным дебютам ──")
    report_opening_cheat_sheets()

    print("\n── 4/4. Opening planner (Stockfish) ──")
    run_opening_planner()


if __name__ == "__main__":
    main()