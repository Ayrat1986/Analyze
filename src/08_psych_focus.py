# ============================================================
# 08_psych_focus.py — ВНИМАНИЕ И ЗЕВКИ (v18.9)
# ============================================================
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, SRC_DIR)

import _common

def main():
    print("=" * 60)
    print(" 08_psych_focus.py — ВНИМАНИЕ И ЗЕВКИ (v18.9)")
    print("=" * 60)

    DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")
    if not os.path.exists(DB_FILE):
        print(f"❌ Не найдена {DB_FILE}. Запусти 03_migrate_sqlite.py.")
        return

    print("\n── 1/5. Blunder Anatomy ──")
    from analysis.psych_focus.blunder_anatomy import run_blunder_anatomy
    run_blunder_anatomy()

    print("\n── 2/5. First Blunder (водораздел) ──")
    from analysis.psych_focus.first_blunder import run_first_blunder
    run_first_blunder()

    print("\n── 3/5. Missed Threats & Mates ──")
    from analysis.psych_focus.missed import run_missed
    run_missed()

    print("\n── 4/5. Game Review (разбор) ──")
    from analysis.psych_focus.review import run_game_review
    run_game_review()

    print("\n── 5/5. Auto Graphs ──")
    from analysis.psych_focus.graphs import run_auto_graphs
    run_auto_graphs()

    print(f"\n✅ Все 5 блоков готовы. Отчёты в: {_common.REPORTS_DIR}")

if __name__ == "__main__":
    main()