# ============================================================
# 11_psych_opponents.py — ПСИХОЛОГИЯ СОПЕРНИКОВ (Оркестратор v6)
# ============================================================
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, SRC_DIR)

import _common

try:
    import chess
    HAVE_CHESS = True
except ImportError:
    HAVE_CHESS = False
    print("⚠️ python-chess не установлен — часть отчётов будет пропущена.")

try:
    from analysis.opponents.weakness import report_opponent_weakness, report_opponent_deep, report_crushed_by
    from analysis.opponents.style import report_style_vs_rating
    from analysis.opponents.anti import report_anti_aggressor
    from analysis.opponents.position_type import report_style_position_type
    from analysis.opponents.time_deficit import report_style_time_deficit
    from analysis.opponents.trainer import report_anti_aggressor_trainer  # <-- НОВОЕ
except ImportError as e:
    print(f"❌ Ошибка импорта модулей: {e}")
    sys.exit(1)


def main():
    print("=" * 60)
    print(" 11_psych_opponents.py — ПСИХОЛОГИЯ СОПЕРНИКОВ (v6)")
    print("=" * 60)

    DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")
    PLAYER = _common.CONFIG.get("player", "")

    if not os.path.exists(DB_FILE):
        print(f"❌ Не найдена {DB_FILE}. Запусти 03_migrate_sqlite.py.")
        return

    print("\n── 1/8. Opponent weakness ──")
    report_opponent_weakness()

    print("\n── 2/8. Opponent deep ──")
    report_opponent_deep()

    print("\n── 3/8. Crushed by (сильнее) ──")
    report_crushed_by()

    if HAVE_CHESS:
        print("\n── 4/8. Style vs rating ──")
        report_style_vs_rating()

        print("\n── 5/8. Anti-aggressor ──")
        report_anti_aggressor()

        print("\n── 6/8. Style × Position × Rating ──")
        report_style_position_type()

        print("\n── 7/8. Style × Time × Deficit ──")
        report_style_time_deficit()
    else:
        print("\n⏩ Пропущены шаги 4-7 (нет python-chess)")

    print("\n── 8/8. Anti-Aggressor Trainer (FENs) ──")
    report_anti_aggressor_trainer()

    print(f"\n✅ Все отчёты готовы.")


if __name__ == "__main__":
    main()