# ============================================================
# analysis/coach/deck.py
# ============================================================
import os
import sqlite3
import random
import csv
from datetime import datetime, timezone, timedelta
import _common

DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")
REPORTS_DIR = str(_common.REPORTS_DIR)

def _conn():
    return sqlite3.connect(DB_FILE)

def report_daily_deck():
    if not os.path.exists(DB_FILE): print("⚠️ daily_deck пропущен."); return
    conn = _conn(); cur = conn.cursor()

    cur.execute("PRAGMA table_info(blunders)")
    cols = {row[1] for row in cur.fetchall()}
    if "fen_before" not in cols: print("⚠️ daily_deck пропущен: нет blunders.fen_before."); conn.close(); return

    now = datetime.now(timezone.utc)
    ts_7d = int((now - timedelta(days=7)).timestamp())

    cur.execute("""
        SELECT b.fen_before, b.move_num, b.loss_cp, b.best_move_uci, g.white, g.black, g.url, g.end_time
        FROM blunders b JOIN games g ON g.url = b.game_url
        WHERE g.is_lag=0 AND g.is_cheater=0 AND b.is_my_blunder=1 AND b.is_berserk=0 AND b.is_instant=0
          AND b.loss_cp > 150 AND b.fen_before IS NOT NULL AND b.fen_before != '' AND g.end_time >= ?
        ORDER BY b.loss_cp DESC
    """, (ts_7d,))
    fresh_rows = cur.fetchall()
    seen_fen = set(); fresh = []
    for row in fresh_rows:
        if row[0] in seen_fen: continue
        seen_fen.add(row[0]); fresh.append(row)
        if len(fresh) >= 10: break

    cur.execute("""
        SELECT b.fen_before, b.move_num, b.loss_cp, b.best_move_uci, g.white, g.black, g.url, g.end_time
        FROM blunders b JOIN games g ON g.url = b.game_url
        WHERE g.is_lag=0 AND g.is_cheater=0 AND b.is_my_blunder=1 AND b.is_berserk=0 AND b.is_instant=0
          AND b.loss_cp > 150 AND b.fen_before IS NOT NULL AND b.fen_before != ''
        ORDER BY b.loss_cp DESC LIMIT 100
    """)
    top100 = cur.fetchall()
    random_pool = [r for r in top100 if r[0] not in seen_fen]
    random.shuffle(random_pool)
    random_sel = []
    for row in random_pool:
        if len(random_sel) >= 10: break
        if row[0] in seen_fen: continue
        seen_fen.add(row[0]); random_sel.append(row)

    txt_path = os.path.join(REPORTS_DIR, "deck_latest.txt")
    csv_path = os.path.join(REPORTS_DIR, "deck_latest.csv")

    def fmt_date(ts):
        try: return datetime.fromtimestamp(ts).strftime("%d.%m.%y")
        except Exception: return "?"

    with open(txt_path, "w", encoding="utf-8") as f:
        def w(line=""): print(line); f.write(line + "\n")
        w("=" * 60); w(" 🎯 КОЛОДА НА СЕГОДНЯ (20 FEN)"); w("=" * 60)
        w(f"Сформирована: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        w("Формат: FEN + лучший ход (Stockfish).")
        w(f"Свежих (7 дней): {len(fresh)}  |  Случайных из топ-100: {len(random_sel)}"); w()

        if fresh:
            w("📅 СВЕЖИЕ (последние 7 дней):")
            for i, (fen, mn, loss, best, wh, bl, url, ts) in enumerate(fresh, 1):
                w(f"  {i}. {wh[:15]} vs {bl[:15]} ({fmt_date(ts)}, ход {mn}, потеря {loss} CP)")
                w(f"     FEN: {fen}")
                if best: w(f"     Лучший ход: {best}")
                w(f"     Тренируй: https://lichess.org/analysis/standard/{fen.replace(' ', '_')}"); w()
        else: w("  ⚠️ Нет свежих зевков за 7 дней."); w()

        if random_sel:
            w("🎲 СЛУЧАЙНЫЕ ИЗ ТОП-100:")
            for i, (fen, mn, loss, best, wh, bl, url, ts) in enumerate(random_sel, 1):
                w(f"  {i}. {wh[:15]} vs {bl[:15]} ({fmt_date(ts)}, ход {mn}, потеря {loss} CP)")
                w(f"     FEN: {fen}")
                if best: w(f"     Лучший ход: {best}")
                w(f"     Тренируй: https://lichess.org/analysis/standard/{fen.replace(' ', '_')}"); w()
        else: w("  ⚠️ Топ-100 пуст.")

        w("🎯 КАК ТРЕНИРОВАТЬ:")
        w("  1. Открой Lichess Analysis (ссылка выше).")
        w("  2. НЕ смотри лучший ход сразу — попробуй найти сам.")
        w("  3. Сравни с Stockfish. Если ошибся — запиши, ПОЧЕМУ.")
        w("  4. 20 FEN × 3 сек = 1 минута. Каждый день — минута.")

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["category", "fen", "move_num", "loss_cp", "best_move_uci", "white", "black", "url", "end_time"])
        for cat, rows in [("fresh", fresh), ("random", random_sel)]:
            for (fen, mn, loss, best, wh, bl, url, ts) in rows:
                w.writerow([cat, fen, mn, loss, best or "", wh, bl, url, ts])

    training_dir = os.path.join(REPORTS_DIR, "training")
    os.makedirs(training_dir, exist_ok=True)
    archive_name = os.path.join(training_dir, f"deck_{datetime.now().strftime('%Y-%m-%d')}.txt")
    try:
        import shutil
        shutil.copy2(txt_path, archive_name)
        print(f"📦 Архив: {archive_name}")
    except Exception as e: print(f"⚠️ Архив не сохранён: {e}")

    print(f"\n✅ {txt_path}")
    print(f"✅ {csv_path}")
    conn.close()