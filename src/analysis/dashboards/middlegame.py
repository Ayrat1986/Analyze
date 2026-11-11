# ============================================================
# analysis/dashboards/middlegame.py — 02_middlegame.txt
# ============================================================
from analysis.common import read_report_file

REPORTS = [
    ("middlegame_summary.txt", "📋 СВОДКА ПО МИТТЕЛЬШПИЛЮ"),
    ("phase_deep_dive.txt", "🔍 ГЛУБОКИЙ АНАЛИЗ ФАЗ"),
    ("tactical_motifs.txt", "⚔️ ТАКТИЧЕСКИЕ МОТИВЫ"),
    ("win_loss_conversion.txt", "💰 РЕАЛИЗАЦИЯ ПЕРЕВЕСА"),
    ("advantage_speed.txt", "⚡ ADVANTAGE SPEED"),
    ("positional_weaknesses.txt", "♟️ ПОЗИЦИОННЫЕ СЛАБОСТИ"),
    ("transition_errors.txt", "🌉 TRANSITION ERRORS"),
    ("plan_retention.txt", "📋 PLAN RETENTION"),
    ("piece_activity.txt", "🎭 PIECE ACTIVITY"),
    ("position_type_classifier.txt", "🎭 ТИП ПОЗИЦИИ → WINRATE"),
    ("long_vs_short.txt", "📏 КОРОТКИЕ vs ДЛИННЫЕ"),
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