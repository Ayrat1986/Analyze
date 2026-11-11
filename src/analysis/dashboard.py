# ============================================================
# analysis/dashboard.py — v20.1 (Исправлен дубликат write_index)
# ============================================================
import os
from datetime import datetime
import _common
from analysis.common import report_context, REPORTS_DIR, read_report_file
from analysis.dashboards.index import build_index, write_index as write_index_v20

DASHBOARDS_DIR = os.path.join(REPORTS_DIR, "dashboards")

def write_index():
    """Делегирует в новый index.py."""
    write_index_v20()

def build_group(w, title, domain, reports):
    w.w_separator(char="#", length=60, title=title)
    w.w(f"Файл: {domain}")
    w.w()
    for filename, rep_title in reports:
        w.w_separator(title=f"{rep_title} (из {filename})")
        lines = read_report_file(filename)
        if lines is None:
            w.w(f"⚠️ Файл {filename} не найден")
        elif not lines or (len(lines) == 1 and not lines[0].strip()):
            w.w(f"⚠️ Файл {filename} пуст")
        else:
            for line in lines:
                w.w(line)
        w.w()

def build_all():
    os.makedirs(DASHBOARDS_DIR, exist_ok=True)
    print("=" * 60); print(" СБОРКА ДАШБОРДОВ — v20.1"); print("=" * 60)
    print("\n── 00_INDEX.txt (корень) ──")
    write_index()

    groups = [
        ("01_openings", "♟️ ДЕБЮТЫ", "05_openings.py", [
            ("opening_planner.txt", "🌳 OPENING PLANNER"),
            ("opening_recommendations.txt", "✅ РЕКОМЕНДАЦИИ"),
            ("opening_repertoire.txt", "♟️ РЕПЕРТУАР"),
            ("openings_winrate_trend.txt", "📉 ТРЕНД WINRATE"),
            ("opening_performance.txt", "♟️ ПРОИЗВОДИТЕЛЬНОСТЬ"),
            ("weak_spots_matrix.txt", "🎯 МАТРИЦА СЛАБОСТЕЙ"),
            ("rating_by_opening.txt", "📈 Δ РЕЙТИНГА"),
            ("line_anatomy.txt", "🔬 АНАТОМИЯ"),
        ]),
        ("02_middlegame", "🔍 МИТТЕЛЬШПИЛЬ", "06_middlegame.py", [
            ("middlegame_summary.txt", "📋 СВОДКА"),
            ("phase_deep_dive.txt", "🔍 ГЛУБОКИЙ АНАЛИЗ"),
            ("tactical_motifs.txt", "⚔️ ТАКТИКА"),
            ("win_loss_conversion.txt", "💰 РЕАЛИЗАЦИЯ"),
            ("advantage_speed.txt", "⚡ СКОРОСТЬ"),
            ("positional_weaknesses.txt", "♟️ СЛАБОСТИ"),
            ("transition_errors.txt", "🌉 ПЕРЕХОД"),
            ("plan_retention.txt", "📋 УДЕРЖАНИЕ ПЛАНА"),
            ("piece_activity.txt", "🎭 АКТИВНОСТЬ"),
            ("position_type_classifier.txt", "🎭 ТИП ПОЗИЦИИ"),
            ("long_vs_short.txt", "📏 ДЛИНА ПАРТИИ"),
        ]),
        ("03_endgame", "🛡️ ЭНДШПИЛЬ", "07_endgame.py", [
            ("endgame_skills.txt", "🛡️ ТЕХНИКА"),
            ("endgame_trainer.txt", "🛡️ ТРЕНАЖЕР"),
            ("berserk_zone.txt", "🏃 БЕРСЕРК"),
            ("missed_berserk.txt", "🏃 УПУЩЕННЫЙ БЕРСЕРК"),
            ("time_gap_analysis.txt", "⏳ ФЛАГ-ЦУГЦВАНГ"),
        ]),
        ("04_psych_focus", "🧠 ВНИМАНИЕ И ЗЕВКИ", "08_psych_focus.py", [
            ("blunder_report_windows.txt", "📊 ОКНА"),
            ("blunder_anatomy.txt", "🔬 АНАТОМИЯ"),
            ("first_blunder_report.txt", "📊 ПЕРВЫЙ ЗЕВОК"),
            ("missed_mates.txt", "🎯 МАТЫ"),
            ("missed_threats.txt", "🎯 УГРОЗЫ"),
        ]),
        ("05_psych_state", "🧠 СОСТОЯНИЕ И РЕЖИМ", "09_psych_state.py", [
            ("time_report_windows.txt", "⏱️ ВРЕМЯ ПО ОКНАМ"),
            ("time_target.txt", "🎯 ЦЕЛЕВОЕ ВРЕМЯ"),
            ("speed_rating.txt", "⚡ SPEED RATING"),
            ("combined_rating.txt", "🔗 COMBINED RATING"),
            ("hours_overview.txt", "🕐 ЧАСЫ И ДНИ"),
            ("time_profile.txt", "⏱️ ПРОФИЛЬ"),
            ("lag_report.txt", "🕵️ ЛАГИ"),
            ("endurance.txt", "🏃 ВЫНОСЛИВОСТЬ"),
            ("behavior_tracker.txt", "🧠 СЕССИИ"),
            ("tilt_timer.txt", "⏱️ ТИЛЬТ"),
            ("panic_curve.txt", "📉 ПАНИКА"),
            ("cascade_tilt.txt", "🧠 КАСКАД"),
            ("aggression_profile.txt", "🥊 АГРЕССИЯ"),
            ("timeout_vs_rating.txt", "📉 ЦЕЙТНОТ"),
            ("daily_checkin.txt", "📋 ЧЕК-ИН"),
        ]),
        ("06_psych_rating", "🧠 РЕЙТИНГ", "10_psych_rating.py", [
            ("bullet_stats_report.txt", "📊 СТАТИСТИКА"),
            ("progress_curve.txt", "📈 ПРОГРЕСС"),
            ("stability.txt", "🎖️ СТАБИЛЬНОСТЬ"),
            ("game_rating_vs_perf.txt", "🚀 GAMER vs PERF"),
            ("potential_tracker.txt", "🚀 ПОТЕНЦИАЛ"),
            ("micro_sessions.txt", "⚡ МИКРО-СЕССИИ"),
        ]),
        ("07_opponents", "🎭 СОПЕРНИКИ", "11_psych_opponents.py", [
            ("opponent_weakness.txt", "🎯 СЛАБОСТИ"),
            ("opponent_deep.txt", "👤 ПРОФИЛИ"),
            ("crushed_by.txt", "🩸 РАСКАЛЫВАЮТ"),
            ("style_vs_rating.txt", "🎭 СТИЛЬ"),
            ("style_position_type.txt", "🎭 СТИЛЬ × ПОЗИЦИЯ"),
            ("style_time_deficit.txt", "⏱️ СТИЛЬ × ВРЕМЯ"),
            ("anti_aggressor.txt", "🛡️ АНТИ-АГРЕССОР"),
        ]),
        ("08_coach", "🎓 ТРЕНЕР", "12_coach.py", [
            ("coach_voice.txt", "🎯 СОВЕТ ДНЯ"),
            ("deck_latest.txt", "🎯 КОЛОДА"),
            ("coach_plan_weekly.txt", "🎯 ПЛАН"),
            ("codex_advice.txt", "🧠 КОДЕКС"),
        ]),
    ]

    for name, title, source, reports in groups:
        print(f"\n── {name}.txt ──")
        with report_context(name, subdir="dashboards") as w:
            build_group(w, title, source, reports)

    print(f"\n✅ Готово: {1 + len(groups)} файлов")

if __name__ == "__main__":
    build_all()