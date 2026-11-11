# ============================================================
# analysis/dashboards/psych_state.py — 05_psych_state.txt (v19.5)
# ============================================================
from analysis.common import read_report_file

REPORTS = [
    ("time_report_windows.txt", "⏱️ ВРЕМЯ ПО ОКНАМ"),
    ("time_target.txt", "🎯 ЦЕЛЕВОЕ ВРЕМЯ НА ХОД"),
    ("speed_rating.txt", "⚡ SPEED RATING (скорость → рейтинг)"),
    ("combined_rating.txt", "🔗 COMBINED RATING (GameR + SpeedR)"),
    ("hours_overview.txt", "🕐 ЧАСЫ И ДНИ"),
    ("time_profile.txt", "⏱️ TIME PROFILE"),
    ("lag_report.txt", "🕵️ LAG REPORT"),
    ("endurance.txt", "🏃 ВЫНОСЛИВОСТЬ"),
    ("behavior_tracker.txt", "🧠 ПОВЕДЕНИЕ ПО СЕССИЯМ"),
    ("tilt_timer.txt", "⏱️ TILT TIMER"),
    ("panic_curve.txt", "📉 КРИВАЯ ПАНИКИ"),
    ("cascade_tilt.txt", "🧠 КАСКАДНЫЙ ТИЛЬТ"),
    ("aggression_profile.txt", "🥊 АГРЕССИЯ И ИНВЕРСИЯ"),
    ("timeout_vs_rating.txt", "📉 ЦЕНА ЦЕЙТНОТА"),
    ("daily_checkin.txt", "📋 DAILY CHECK-IN"),
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