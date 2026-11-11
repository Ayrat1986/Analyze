# ============================================================
# analysis/dashboards/opponents.py — 07_opponents.txt
# ============================================================
from analysis.common import read_report_file

REPORTS = [
    ("opponent_weakness.txt", "🎯 СЛАБОСТИ СОПЕРНИКОВ"),
    ("opponent_deep.txt", "👤 ПРОФИЛИ ТОП-10"),
    ("crushed_by.txt", "🩸 ТЕ, КТО РАСКАЛЫВАЕТ"),
    ("style_vs_rating.txt", "🎭 СТИЛЬ vs РЕЙТИНГ"),
    ("style_position_type.txt", "🎭 СТИЛЬ × ПОЗИЦИЯ × РЕЙТИНГ"),
    ("style_time_deficit.txt", "⏱️ СТИЛЬ × ВРЕМЯ × ДЕФИЦИТ"),
    ("anti_aggressor.txt", "🛡️ АНТИ-АГРЕССОР"),
]


def build_opponents(w):
    w.w_separator(char="#", length=60, title="🎭 ПСИХОЛОГИЯ СОПЕРНИКОВ")
    w.w("Файл: 07_opponents.txt")
    w.w("Источник: 11_psych_opponents.py")
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