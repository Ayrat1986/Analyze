# ============================================================
# analysis/dashboards/middlegame.py — 02_middlegame.txt (v25.0)
# §28: REPORTS сокращён с 11 до 6 отчётов.
# ============================================================
from analysis.common import read_report_file

REPORTS = [
    ("middlegame_summary.txt",       "📋 СВОДКА ПО МИТТЕЛЬШПИЛЮ"),
    ("advantage_speed.txt",          "⚡ ADVANTAGE SPEED"),
    ("transition_errors.txt",        "🌉 TRANSITION ERRORS"),
    ("tactical_motifs.txt",          "⚔️ ТАКТИЧЕСКИЕ МОТИВЫ"),
    ("win_loss_conversion.txt",      "💰 РЕАЛИЗАЦИЯ ПЕРЕВЕСА"),
    ("position_type_classifier.txt", "🎭 ТИП ПОЗИЦИИ → WINRATE"),
]


def build_middlegame(w):
    w.w_separator(char="#", length=60, title="🔍 МИТТЕЛЬШПИЛЬ")
    w.w("Файл: 02_middlegame.txt")
    w.w("Источник: 06_middlegame.py")
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