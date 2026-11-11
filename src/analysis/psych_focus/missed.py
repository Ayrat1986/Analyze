# ============================================================
# analysis/psych_focus/missed.py (v19.1)
# ============================================================
from analysis.common import report_context
from .common import _conn

def report_missed_mates():
    conn = _conn(); cur = conn.cursor()
    
    cur.execute("""
        SELECT g.white, g.black, b.move_num, b.what, b.fen_before, b.best_move_uci, b.loss_cp, g.url
        FROM blunders b JOIN games g ON g.url=b.game_url
        WHERE g.is_lag=0 AND g.is_cheater=0 AND b.is_my_blunder=1 AND b.pattern_tag = 'missed_mate'
        ORDER BY g.end_time DESC LIMIT 20
    """)
    rows = cur.fetchall()

    with report_context("missed_mates") as w:
        w.w_separator(title="ЧТО Я НЕ УВИДЕЛ (Пропущенные маты)")
        w.w(f"Найдено позиций: {len(rows)}")
        w.w()
        
        if not rows:
            w.w("✅ За последнее время пропущенных матов нет. Отличная тактика!")
        else:
            w.w("💡 Здесь ты мог поставить мат, но сыграл иначе. Тренируй эти позиции:")
            w.w()
            for i, (white, black, move_num, what, fen, best_uci, loss, url) in enumerate(rows, 1):
                w.w(f"#{i}. {white} vs {black} (Ход {move_num})")
                w.w(f"    Что случилось: {what}")
                w.w(f"    FEN: {fen}")
                if best_uci: w.w(f"    💡 Лучший ход: {best_uci}")
                w.w(f"    Тренируй: https://lichess.org/analysis/standard/{fen.replace(' ', '_')}")
                w.w(f"    Ссылка: {url}")
                w.w()
    conn.close()

def report_missed_threats():
    conn = _conn(); cur = conn.cursor()

    with report_context("missed_threats") as w:
        w.w_separator(title="ПРОПУЩЕННЫЕ УГРОЗЫ (Missed Threats)")
        w.w("Здесь собраны зевки, после которых у соперника был явный тактический удар.\n")

        cur.execute("""
            SELECT b.move_num, b.loss_cp, b.pattern_tag, b.fen_before, g.white, g.black, g.url
            FROM blunders b JOIN games g ON g.url = b.game_url
            WHERE b.is_my_blunder=1 AND b.is_berserk=0 AND b.is_instant=0 AND b.missed_threat=1
            ORDER BY b.loss_cp DESC LIMIT 50
        """)
        rows = cur.fetchall()

        if not rows:
            w.w("✅ Отлично! Ты не пропускал явных тактических угроз.")
        else:
            w.w(f"Найдено позиций: {len(rows)}\n")
            for i, (move_num, loss_cp, tag, fen, white, black, url) in enumerate(rows, 1):
                w.w(f"#{i}. {white[:15]} vs {black[:15]} (Ход {move_num}, потеря {loss_cp} CP)")
                w.w(f"    Паттерн: {tag}")
                if fen:
                    w.w(f"    FEN: {fen}")
                    w.w(f"    Тренируй: https://lichess.org/analysis/standard/{fen.replace(' ', '_')}")
                w.w(f"    Ссылка: {url}")
                w.w()

    conn.close()

def run_missed():
    print("  1/2. Missed Mates")
    report_missed_mates()
    print("  2/2. Missed Threats")
    report_missed_threats()