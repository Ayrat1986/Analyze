# ============================================================
# analysis/dashboards/psych_state.py — 05_psych_state.txt (v25.0)
# §28: убраны time_report_windows, hours_overview, endurance,
#      tilt_timer, daily_checkin. Оставлено 9 отчётов.
# ============================================================
from analysis.common import read_report_file

REPORTS = [
    ("time_profile.txt",       "⏱️ TIME PROFILE"),
    ("lag_report.txt",         "🕵️ LAG REPORT"),
    ("time_target.txt",        "🎯 ЦЕЛЕВОЕ ВРЕМЯ НА ХОД"),
    ("speed_rating.txt",       "⚡ SPEED RATING (скорость → рейтинг)"),
    ("combined_rating.txt",    "🔗 COMBINED RATING (GameR + SpeedR)"),
    ("behavior_tracker.txt",   "🧠 ПОВЕДЕНИЕ ПО СЕССИЯМ"),
    ("panic_curve.txt",        "📉 КРИВАЯ ПАНИКИ"),
    ("cascade_tilt.txt",       "🧠 КАСКАДНЫЙ ТИЛЬТ"),
    ("aggression_profile.txt", "🥊 АГРЕССИЯ И ИНВЕРСИЯ"),
]


def build_psych_state(w):
    w.w_separator(char="#", length=60, title="🧠 СОСТОЯНИЕ И РЕЖИМ")
    w.w("Файл: 05_psych_state.txt")
    w.w("Источник: 09_psych_state.py")
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