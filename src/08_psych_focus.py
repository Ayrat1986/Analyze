# ============================================================
# 08_psych_focus.py — ВНИМАНИЕ И ЗЕВКИ (v25.0)
# Удалён шаг 5/5 (Auto Graphs) — PDF удалён, PNG не нужны.
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
    print(" 08_psych_focus.py — ВНИМАНИЕ И ЗЕВКИ (v25.0)")
    print("=" * 60)

    DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")
    if not os.path.exists(DB_FILE):
        print(f"❌ Не найдена {DB_FILE}. Запусти 03_migrate_sqlite.py.")
        return

    print("\n── 1/4. Blunder Anatomy ──")
    from analysis.psych_focus.blunder_anatomy import run_blunder_anatomy
    run_blunder_anatomy()

    print("\n── 2/4. First Blunder (водораздел) ──")
    from analysis.psych_focus.first_blunder import run_first_blunder
    run_first_blunder()

    print("\n── 3/4. Missed Threats & Mates ──")
    from analysis.psych_focus.missed import run_missed
    run_missed()

    print("\n── 4/4. Game Review (разбор) ──")
    from analysis.psych_focus.review import run_game_review
    run_game_review()

    print(f"\n✅ Все 4 блока готовы. Отчёты в: {_common.REPORTS_DIR}")


if __name__ == "__main__":
    main()