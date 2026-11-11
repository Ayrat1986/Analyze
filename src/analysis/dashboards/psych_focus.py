# ============================================================
# analysis/dashboards/psych_focus.py — 04_psych_focus.txt
# ============================================================
from analysis.common import read_report_file

REPORTS = [
    ("blunder_report_windows.txt", "📊 ЗЕВКИ ПО ОКНАМ (1/2/7/30/90)"),
    ("blunder_anatomy.txt", "🔬 BLUNDER ANATOMY (время на ход)"),
    ("first_blunder_report.txt", "📊 ПЕРВЫЙ ЗЕВОК"),
    ("missed_mates.txt", "🎯 ПРОПУЩЕННЫЕ МАТЫ"),
    ("missed_threats.txt", "🎯 ПРОПУЩЕННЫЕ УГРОЗЫ"),
]


def build_psych_focus(w):
    w.w_separator(char="#", length=60, title="🧠 ВНИМАНИЕ И ЗЕВКИ")
    w.w("Файл: 04_psych_focus.txt")
    w.w("Источник: 08_psych_focus.py")
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