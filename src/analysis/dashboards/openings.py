# ============================================================
# analysis/dashboards/openings.py — 01_openings.txt (v25.0)
# §28: REPORTS сокращён с 9 до 4 отчётов.
# ============================================================
from analysis.common import read_report_file

REPORTS = [
    ("opening_planner.txt",       "🌳 OPENING PLANNER (Stockfish)"),
    ("opening_repertoire.txt",    "♟️ РЕПЕРТУАР"),
    ("opening_cheat_sheets.txt",  "🧠 ШПАРГАЛКИ (D00, D02, D10)"),
    ("line_anatomy.txt",          "🔬 АНАТОМИЯ ЛИНИЙ"),
]


def build_openings(w):
    w.w_separator(char="#", length=60, title="♟️ ДЕБЮТЫ")
    w.w("Файл: 01_openings.txt")
    w.w("Источник: 05_openings.py")
    w.w()
    for filename, title in REPORTS:
        w.w_separator(title=f"{title} (из {filename})")
        lines = read_report_file(filename)
        if lines is None:
            w.w(f"⚠️ Файл {filename} не найден")
        elif not lines or (len(lines) == 1 and not lines[0].strip()):
            w.w(f"⚠️ Файл {filename} пуст")
        else:
            for line in lines:
                w.w(line)
        w.w()