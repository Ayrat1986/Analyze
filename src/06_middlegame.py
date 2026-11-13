# ============================================================
# 06_middlegame.py — МИТТЕЛЬШПИЛЬ (Оркестратор v25.0)
# §28: удалены phase_deep, plan_retention, piece_activity,
#      long_vs_short, positional_weaknesses.
# ============================================================
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, SRC_DIR)

import _common
from analysis.middlegame import (
    report_advantage_speed,
    report_transition_errors,
    report_tactical_motifs,
    report_win_loss_conversion,
    report_position_types,
    report_summary,
)

REPORTS = [
    ("middlegame_summary",   report_summary),
    ("advantage_speed",      report_advantage_speed),
    ("transition_errors",    report_transition_errors),
    ("tactical_motifs",      report_tactical_motifs),
    ("win_loss_conversion",  report_win_loss_conversion),
    ("position_types",       report_position_types),
]


def main():
    print("=" * 60)
    print(" 06_middlegame.py — МИТТЕЛЬШПИЛЬ (v25.0, оркестратор)")
    print("=" * 60)

    if not _common.CONFIG.get("player"):
        print("⚠️ В config.json нет 'player' — часть отчётов будет некорректной.")

    DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")
    if not os.path.exists(DB_FILE):
        print(f"❌ Не найдена {DB_FILE}. Запусти 03_migrate_sqlite.py.")
        return

    for i, (name, fn) in enumerate(REPORTS, 1):
        print(f"\n── {i}/{len(REPORTS)}. {name} ──")
        fn()

    print(f"\n✅ Все {len(REPORTS)} отчётов в: {_common.REPORTS_DIR}")


if __name__ == "__main__":
    main()