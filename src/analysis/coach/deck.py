# ============================================================
# analysis/coach/deck.py — v26.3
# v26.3: дедупликация по game_url (не более 1 позиции из партии).
#        Причина включения (fresh / топ-100 / повтор pattern_tag).
#        Сыгранный ход + лучший ход + SAN (если chess).
#        Два режима тренировки в инструкции.
# v26.2: убран дублирующий заголовок.
# ============================================================
import os
import sqlite3
import random
import csv
from datetime import datetime, timezone, timedelta

import _common

try:
    import chess  # type: ignore
    _HAS_CHESS = True
except ImportError:
    _HAS_CHESS = False

DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")
REPORTS_DIR = str(_common.REPORTS_DIR)


def _conn():
    return sqlite3.connect(DB_FILE)


def _to_san(fen: str, uci: str) -> str:
    """UCI → SAN через python-chess. Если недоступно — вернуть UCI."""
    if not _HAS_CHESS or not fen or not uci:
        return uci or "?"
    try:
        board = chess.Board(fen)
        mv = chess.Move.from_uci(uci)
        if mv in board.legal_moves:
            return board.san(mv)
    except Exception:
        pass
    return uci


def report_daily_deck():
    if not os.path.exists(DB_FILE):
        print("⚠️ daily_deck пропущен.")
        return
    conn = _conn()
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(blunders)")
    cols = {row[1] for row in cur.fetchall()}
    if "fen_before" not in cols:
        print("⚠️ daily_deck пропущен: нет blunders.fen_before.")
        conn.close()
        return
    has_pattern = "pattern_tag" in cols

    now = datetime.now(timezone.utc)
    ts_7d = int((now - timedelta(days=7)).timestamp())

    pattern_col = ", b.pattern_tag" if has_pattern else ", NULL AS pattern_tag"
    base_query = f"""
        SELECT b.fen_before, b.move_num, b.loss_cp, b.best_move_uci,
               b.move_uci {pattern_col},
               g.white, g.black, g.url, g.end_time
        FROM blunders b
        JOIN games g ON g.url = b.game_url
        WHERE g.is_lag=0 AND g.is_cheater=0
          AND b.is_my_blunder=1 AND b.is_berserk=0 AND b.is_instant=0
          AND b.loss_cp > 150
          AND b.fen_before IS NOT NULL AND b.fen_before != ''
    """

    # --- Свежие (7 дней) ---
    cur.execute(base_query + " AND g.end_time >= ? ORDER BY b.loss_cp DESC",
                (ts_7d,))
    fresh_rows = cur.fetchall()

    seen_fen = set()
    seen_url = set()
    seen_pattern_count = {}
    fresh = []

    def _accept(row, max_per_pattern=2):
        fen = row[0]
        url = row[8]
        pattern = row[5] if has_pattern else None
        if fen in seen_fen:
            return False
        if url in seen_url:
            return False
        if pattern:
            if seen_pattern_count.get(pattern, 0) >= max_per_pattern:
                return False
            seen_pattern_count[pattern] = seen_pattern_count.get(pattern, 0) + 1
        return True

    for row in fresh_rows:
        if _accept(row):
            seen_fen.add(row[0])
            seen_url.add(row[8])
            fresh.append(row)
            if len(fresh) >= 10:
                break

    # --- Случайные из топ-100 ---
    cur.execute(base_query + " ORDER BY b.loss_cp DESC LIMIT 100")
    top100 = cur.fetchall()
    random.shuffle(top100)
    random_sel = []
    for row in top100:
        if _accept(row):
            seen_fen.add(row[0])
            seen_url.add(row[8])
            random_sel.append(row)
            if len(random_sel) >= 10:
                break

    txt_path = os.path.join(REPORTS_DIR, "deck_latest.txt")
    csv_path = os.path.join(REPORTS_DIR, "deck_latest.csv")

    def fmt_date(ts):
        try:
            return datetime.fromtimestamp(ts).strftime("%d.%m.%y")
        except Exception:
            return "?"

    def _reason(category, pattern):
        if category == "fresh":
            return "свежая ошибка (≤7 дней)"
        if category == "random":
            return f"повтор мотива «{pattern}»" if pattern else "топ-100 по CP"
        return category

    def _render_block(w, rows, category):
        if not rows:
            w(f" ⚠️ {category}: пусто.")
            w()
            return
        for i, row in enumerate(rows, 1):
            fen, mn, loss, best, played, pattern, wh, bl, url, ts = row
            w(f"  {i}. {wh[:15]} vs {bl[:15]} ({fmt_date(ts)}, ход {mn}, потеря {loss} CP)")
            w(f"     Причина включения: {_reason(category, pattern)}")
            w(f"     FEN: {fen}")
            if played:
                w(f"     Сыграно: {_to_san(fen, played)}  (UCI {played})")
            if best:
                w(f"     Лучше:   {_to_san(fen, best)}  (UCI {best})")
            w(f"     Тренируй: https://lichess.org/analysis/standard/{fen.replace(' ', '_')}")
            w()

    with open(txt_path, "w", encoding="utf-8") as f:
        def w(line=""):
            print(line)
            f.write(line + "\n")

        w(f"Сформирована: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        w("Причина включения указана у каждой позиции. "
          "Не более 1 позиции из одной партии, не более 2 на pattern_tag.")
        w(f"Свежих (7 дней): {len(fresh)} | Случайных из топ-100: {len(random_sel)}")
        w()

        w(" РЕЖИМЫ ТРЕНИРОВКИ:")
        w("  A) Быстрый — 3 сек на позицию.")
        w("     Задача: назвать угрозу, шахи, взятия или тактический мотив.")
        w("  B) Расчётный — 30–60 сек на позицию (для 58+ ходов и эндшпилей).")
        w("     Задача: выбрать ход, объяснить план, проверить вариант.")
        w("  Оценка успеха: ✅ решено / ⚠️ частично / ❌ не решено.")
        w()

        w(" СВЕЖИЕ (последние 7 дней):")
        _render_block(w, fresh, "fresh")
        w(" СЛУЧАЙНЫЕ ИЗ ТОП-100:")
        _render_block(w, random_sel, "random")

        w(" КАК ТРЕНИРОВАТЬ:")
        w("  1. Открой Lichess Analysis (ссылка у каждой позиции).")
        w("  2. НЕ смотри лучший ход сразу — попробуй найти сам.")
        w("  3. Сравни с Stockfish. Если ошибся — запиши, ПОЧЕМУ.")
        w("  4. Отметь результат (✅/⚠️/❌) — это основа для прогресса.")

    # CSV
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["category", "fen", "move_num", "loss_cp", "played_uci",
                     "best_move_uci", "pattern_tag", "white", "black", "url", "end_time"])
        for cat, rows in [("fresh", fresh), ("random", random_sel)]:
            for row in rows:
                fen, mn, loss, best, played, pattern, wh, bl, url, ts = row
                wr.writerow([cat, fen, mn, loss, played or "", best or "",
                             pattern or "", wh, bl, url, ts])

    # Архив
    training_dir = os.path.join(REPORTS_DIR, "training")
    os.makedirs(training_dir, exist_ok=True)
    archive = os.path.join(training_dir, f"deck_{datetime.now().strftime('%Y-%m-%d')}.txt")
    try:
        import shutil
        shutil.copy2(txt_path, archive)
        print(f" Архив: {archive}")
    except Exception as e:
        print(f"⚠️ Архив не сохранён: {e}")

    print(f"\n✅ {txt_path}")
    print(f"✅ {csv_path}")
    conn.close()
