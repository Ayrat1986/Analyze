# ============================================================
# 11_psych_opponents.py — ПСИХОЛОГИЯ СОПЕРНИКОВ (v25.0)
# §4 (уточнение): opponent_deep возвращён, но анализирует
# только тех, кто в crushed_by. Ищем паттерны.
# ============================================================
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, SRC_DIR)

import _common
from analysis.opponents.weakness import (
    report_opponent_weakness, report_opponent_deep, report_crushed_by
)
from analysis.opponents.trainer import report_anti_aggressor_trainer


def main():
    print("=" * 60)
    print(" 11_psych_opponents.py — ПСИХОЛОГИЯ СОПЕРНИКОВ (v25.0)")
    print("=" * 60)

    DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")
    if not os.path.exists(DB_FILE):
        print(f"❌ Не найдена {DB_FILE}. Запусти 03_migrate_sqlite.py.")
        return

    print("\n── 1/4. Opponent weakness ──")
    report_opponent_weakness()

    print("\n── 2/4. Crushed by (сильнее) ──")
    report_crushed_by()

    print("\n── 3/4. Deep Dive (как они ломают) ──")
    report_opponent_deep()

    print("\n── 4/4. Anti-Aggressor Trainer (FENs) ──")
    report_anti_aggressor_trainer()

    print(f"\n✅ Все 4 отчёта готовы.")


if __name__ == "__main__":
    main()