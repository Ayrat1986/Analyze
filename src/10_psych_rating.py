# ============================================================
# 10_psych_rating.py — РЕЙТИНГ (Оркестратор v20.1)
# ============================================================
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, SRC_DIR)

import _common
from analysis.psych_rating import (
    report_bullet_stats,
    report_progress_curve,
    report_stability,
    report_game_rating_vs_perf,
    report_potential_tracker,
    report_micro_sessions,
)

def main():
    print("=" * 60)
    print(" 10_psych_rating.py — РЕЙТИНГ И ПРОГРЕСС (v20.1)")
    print("=" * 60)

    DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")
    if not os.path.exists(DB_FILE):
        print(f"❌ Не найдена {DB_FILE}. Запусти 03_migrate_sqlite.py.")
        return

    print("\n── 1/6. Bullet Stats ──")
    report_bullet_stats()

    print("\n── 2/6. Progress Curve ──")
    report_progress_curve()

    print("\n── 3/6. Stability ──")
    report_stability()

    print("\n── 4/6. GameR vs Perf ──")
    report_game_rating_vs_perf()

    print("\n── 5/6. Potential Tracker ──")
    report_potential_tracker()
    
    print("\n── 6/6. Micro Sessions ──")
    report_micro_sessions()

    print(f"\n✅ Все отчеты в: {_common.REPORTS_DIR}")

if __name__ == "__main__":
    main()