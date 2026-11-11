# ============================================================
# analysis/dashboards/endgame.py — 03_endgame.txt
# ============================================================
from analysis.common import read_report_file

REPORTS = [
    ("endgame_skills.txt", "🛡️ ЭНДШПИЛЬНАЯ ТЕХНИКА"),
    ("endgame_trainer.txt", "🛡️ ТРЕНАЖЕР ЭНДШПИЛЯ"),
    ("berserk_zone.txt", "🏃 ЗОНА БЕРСЕРКА"),
    ("missed_berserk.txt", "🏃 УПУЩЕННЫЙ БЕРСЕРК"),
    ("time_gap_analysis.txt", "⏳ ФЛАГ-ЦУГЦВАНГ"),
]


def build_endgame(w):
    w.w_separator(char="#", length=60, title="🛡️ ЭНДШПИЛЬ И БЕРСЕРК")
    w.w("Файл: 03_endgame.txt")
    w.w("Источник: 07_endgame.py")
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