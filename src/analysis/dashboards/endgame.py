# ============================================================
# analysis/dashboards/endgame.py — 03_endgame.txt
# ============================================================
from analysis.common import read_report_file
import os
import sqlite3
import _common
from analysis.common import report_context

REPORTS = [
    ("endgame_skills.txt", "🛡️ ЭНДШПИЛЬНАЯ ТЕХНИКА"),
    ("endgame_trainer.txt", "🛡️ ТРЕНАЖЕР ЭНДШПИЛЯ"),
    ("berserk_zone.txt", "🏃 ЗОНА БЕРСЕРКА"),
    ("missed_berserk.txt", "🏃 УПУЩЕННЫЙ БЕРСЕРК"),
    ("time_gap_analysis.txt", "⏳ ФЛАГ-ЦУГЦВАНГ"),
]

DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")

def build_endgame(w):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    w.w_separator(title="ЭНДШПИЛЬ И ДЛИННЫЕ ПАРТИИ")

    # 1. Истинный ACPL эндшпиля (по ходам > 30)
    cur.execute("""
        SELECT ROUND(AVG(acpl_endgame), 1), COUNT(*)
        FROM games 
        WHERE is_lag=0 AND is_cheater=0 AND acpl_endgame > 0
    """)
    true_eg_acpl, true_eg_n = cur.fetchone()
    true_eg_acpl = true_eg_acpl or 0
    true_eg_n = true_eg_n or 0

    w.w(" 1. Качество в эндшпиле (ходы > 30):")
    w.w(f"    ACPL: {true_eg_acpl:.1f} CP | N={true_eg_n} партий")
    w.w()

    # 2. ACPL длинных партий (длина >= 60 ходов)
    cur.execute("""
        SELECT ROUND(AVG(acpl), 1), COUNT(*)
        FROM games 
        WHERE is_lag=0 AND is_cheater=0 AND acpl > 0 AND game_length >= 60
    """)
    long_acpl, long_n = cur.fetchone()
    long_acpl = long_acpl or 0
    long_n = long_n or 0

    w.w(" 2. Качество в длинных партиях (вся партия >= 60 ходов):")
    w.w(f"    ACPL: {long_acpl:.1f} CP | N={long_n} партий")
    w.w("    (Это НЕ эндшпиль. Это общая точность в затяжных играх)")
    w.w()

    # 3. Победы по флагу и мату в эндшпиле
    cur.execute("""
        SELECT 
            SUM(CASE WHEN reason='мат' AND won=1 THEN 1 ELSE 0 END) AS mate_wins,
            SUM(CASE WHEN reason='просрочка' AND won=1 THEN 1 ELSE 0 END) AS flag_wins,
            SUM(CASE WHEN reason='сдача' AND won=1 THEN 1 ELSE 0 END) AS resign_wins
        FROM games
        WHERE is_lag=0 AND is_cheater=0 AND game_length >= 60
    """)
    mw, fw, rw = cur.fetchone()
    mw, fw, rw = mw or 0, fw or 0, rw or 0
    total_wins = mw + fw + rw or 1

    w.w(" 3. Как реализуются победы в длинных партиях:")
    w.w(f"    Мат:       {mw} ({mw/total_wins*100:.1f}%)")
    w.w(f"    Сдача:     {rw} ({rw/total_wins*100:.1f}%)")
    w.w(f"    По флагу:  {fw} ({fw/total_wins*100:.1f}%)")
    w.w()

    # 4. Слив выигранных эндшпилей
    cur.execute("""
        SELECT COUNT(*)
        FROM games
        WHERE is_lag=0 AND is_cheater=0 
          AND max_eval_advantage >= 300 
          AND won=0 AND draw=0
          AND game_length >= 60
    """)
    eg_sliv = cur.fetchone()[0] or 0
    w.w(f" 4. Слив перевеса (+3.0) в длинных партиях: {eg_sliv} партий")
    w.w()

    conn.close()
    
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
