# ============================================================
# 12_coach.py — ТРЕНЕР (Оркестратор v20.1)
# ============================================================
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, SRC_DIR)

import _common
from analysis.coach import (
    report_coach_plan_weekly,
    report_codex_advice,
    report_coach_voice,
    report_daily_deck,
)

def main():
    print("=" * 60)
    print(" 12_coach.py — ТРЕНЕР: СИНТЕЗ И ИТОГ (v20.1)")
    print("=" * 60)

    DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")
    if not os.path.exists(DB_FILE):
        print(f"❌ Не найдена {DB_FILE}. Запусти 03_migrate_sqlite.py.")
        return

    print("\n── 1/4. Coach plan weekly ──")
    report_coach_plan_weekly()

    print("\n── 2/4. Codex advice ──")
    report_codex_advice()

    print("\n── 3/4. Coach voice (совет на сегодня) ──")
    report_coach_voice()

    print("\n── 4/4. Daily deck (20 FEN) ──")
    report_daily_deck()

    print(f"\n✅ Все 4 отчета в: {_common.REPORTS_DIR}")

if __name__ == "__main__":
    main()