# ============================================================
# analysis/dashboards/psych_rating.py — 06_psych_rating.txt
# ============================================================
from analysis.common import read_report_file

REPORTS = [
    ("bullet_stats_report.txt", "📊 BULLET STATS"),
    ("progress_curve.txt", "📈 PROGRESS CURVE"),
    ("stability.txt", "🎖️ СТАБИЛЬНОСТЬ"),
    ("game_rating_vs_perf.txt", "🚀 GAME RATING vs PERF"),
    ("potential_tracker.txt", "🚀 АНАЛИЗ ПОТЕНЦИАЛА"),
    ("micro_sessions.txt", "⚡ МИКРО-СЕССИИ"),
]


def build_psych_rating(w):
    w.w_separator(char="#", length=60, title="🧠 РЕЙТИНГ И ПРОГРЕСС")
    w.w("Файл: 06_psych_rating.txt")
    w.w("Источник: 10_psych_rating.py")
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