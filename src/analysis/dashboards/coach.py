# ============================================================
# analysis/dashboards/coach.py — 08_coach.txt
# ============================================================
from analysis.common import read_report_file

REPORTS = [
    ("coach_voice.txt", "🎯 СОВЕТ ТРЕНЕРА НА СЕГОДНЯ"),
    ("deck_latest.txt", "🎯 КОЛОДА НА СЕГОДНЯ (20 FEN)"),
    ("coach_plan_weekly.txt", "🎯 ПЛАН НА НЕДЕЛЮ"),
    ("codex_advice.txt", "🧠 СОВЕТЫ AI-ТРЕНЕРА (Кодекс Пули)"),
]


def build_coach(w):
    w.w_separator(char="#", length=60, title="🎓 ТРЕНЕР — ИТОГ")
    w.w("Файл: 08_coach.txt")
    w.w("Источник: 12_coach.py")
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