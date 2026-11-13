# ============================================================
# analysis/dashboard.py — v25.0 (§24)
# Единый источник отчётов: REPORTS из dashboards/*.py.
# Удалён дублирующий список groups.
# ============================================================
import os

import _common
from analysis.common import report_context, REPORTS_DIR
from analysis.dashboards.index import write_index as write_index_v20
from analysis.dashboards.openings import build_openings, REPORTS as OPENINGS_REPORTS
from analysis.dashboards.middlegame import build_middlegame, REPORTS as MIDDLEGAME_REPORTS
from analysis.dashboards.endgame import build_endgame, REPORTS as ENDGAME_REPORTS
from analysis.dashboards.psych_focus import build_psych_focus, REPORTS as PSYCH_FOCUS_REPORTS
from analysis.dashboards.psych_state import build_psych_state, REPORTS as PSYCH_STATE_REPORTS
from analysis.dashboards.psych_rating import build_psych_rating, REPORTS as PSYCH_RATING_REPORTS
from analysis.dashboards.opponents import build_opponents, REPORTS as OPPONENTS_REPORTS
from analysis.dashboards.coach import build_coach, REPORTS as COACH_REPORTS

DASHBOARDS_DIR = os.path.join(REPORTS_DIR, "dashboards")


def write_index():
    """Делегирует в index.py."""
    write_index_v20()


def build_all():
    os.makedirs(DASHBOARDS_DIR, exist_ok=True)
    print("=" * 60)
    print(" СБОРКА ДАШБОРДОВ — v25.0 (REPORTS)")
    print("=" * 60)

    print("\n── 00_INDEX.txt (корень) ──")
    write_index()

    # 01_openings.txt
    print("\n── 01_openings.txt ──")
    with report_context("01_openings", subdir="dashboards") as w:
        build_openings(w)

    # 02_middlegame.txt
    print("\n── 02_middlegame.txt ──")
    with report_context("02_middlegame", subdir="dashboards") as w:
        build_middlegame(w)

    # 03_endgame.txt
    print("\n── 03_endgame.txt ──")
    with report_context("03_endgame", subdir="dashboards") as w:
        build_endgame(w)

    # 04_psych_focus.txt
    print("\n── 04_psych_focus.txt ──")
    with report_context("04_psych_focus", subdir="dashboards") as w:
        build_psych_focus(w)

    # 05_psych_state.txt
    print("\n── 05_psych_state.txt ──")
    with report_context("05_psych_state", subdir="dashboards") as w:
        build_psych_state(w)

    # 06_psych_rating.txt
    print("\n── 06_psych_rating.txt ──")
    with report_context("06_psych_rating", subdir="dashboards") as w:
        build_psych_rating(w)

    # 07_opponents.txt
    print("\n── 07_opponents.txt ──")
    with report_context("07_opponents", subdir="dashboards") as w:
        build_opponents(w)

    # 08_coach.txt
    print("\n── 08_coach.txt ──")
    with report_context("08_coach", subdir="dashboards") as w:
        build_coach(w)

    total_files = 1 + 8
    print(f"\n✅ Готово: {total_files} файлов (00_INDEX + 8 доменов)")


if __name__ == "__main__":
    build_all()