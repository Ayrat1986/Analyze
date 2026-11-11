# src/core/метрики.py
"""
Единый источник правды для формул.
Сейчас game_rating дублируется в 03 и 14, perf_rating — в 08, 10, 01.
Здесь — одна реализация.
"""


def game_rating(acpl):
    """
    Потенциал (качество ходов) по ACPL.
    Формула: 3200 - acpl * 10, обрезка [1000, 3200].
    40 ACPL → 2800, 60 ACPL → 2600.
    """
    if not acpl or acpl <= 0:
        return 0
    return max(1000, min(3200, 3200 - acpl * 10))


def perf_rating(avg_opp, wins, draws, total):
    """
    Performance Rating (результат).
    avg_opp + (score - 0.5) * 800, где score = (wins + 0.5*draws) / total.
    """
    if not total or not avg_opp:
        return 0
    score = (wins + 0.5 * draws) / total
    return avg_opp + (score - 0.5) * 800


def anchor(min_window, peak, avg_opp):
    """
    Якорь (дно, ниже которого не падаешь — диагностика).
    Среднее из трёх: минимум за окно, пик−150, ср.сопер×0.98.
    """
    if not min_window or not peak or not avg_opp:
        return 0
    return (min_window + (peak - 150) + avg_opp * 0.98) / 3


def home_zone(hist_peak, avg_my):
    """
    Домашняя зона (где рейтинг «живёт»).
    ((пик − 100) + средний + средний) / 3.
    Используется в 13 (build_sql_summary).
    """
    if not hist_peak or not avg_my:
        return 0
    return ((hist_peak - 100) + avg_my + avg_my) / 3