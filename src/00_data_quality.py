# ============================================================
# 00_data_quality.py — Кросс-проверки целостности (v25.0)
# Удалены: check_aggregation_consistency, check_metrics_json,
#          check_trainer_progress (см. PROJECT_RULES §28).
# ============================================================
import sqlite3
import os
import sys
import json
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, SRC_DIR)

import _common

DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")
STOCKFISH_CACHE = str(_common.BASE_DIR / "data" / "stockfish_cache.json")
REPORTS_DIR = str(_common.REPORTS_DIR)

try:
    import colorama
    colorama.init()
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    RESET = "\033[0m"
except ImportError:
    GREEN = YELLOW = RED = CYAN = RESET = ""


class Checker:
    def __init__(self):
        self.passed = 0
        self.warnings = 0
        self.failed = 0
        self.messages = []

    def ok(self, msg: str):
        self.passed += 1
        self.messages.append(f"{GREEN}✅ OK{RESET}  {msg}")
        print(f"{GREEN}✅ OK{RESET}  {msg}")

    def warn(self, msg: str):
        self.warnings += 1
        self.messages.append(f"{YELLOW}⚠️  WARN{RESET} {msg}")
        print(f"{YELLOW}⚠️  WARN{RESET} {msg}")

    def fail(self, msg: str):
        self.failed += 1
        self.messages.append(f"{RED}❌ FAIL{RESET} {msg}")
        print(f"{RED}❌ FAIL{RESET} {msg}")

    def summary(self) -> bool:
        print()
        print("=" * 60)
        print(" ИТОГ ПРОВЕРКИ")
        print("=" * 60)
        print(f"  {GREEN}Пройдено:{RESET}     {self.passed}")
        print(f"  {YELLOW}Предупреждений:{RESET} {self.warnings}")
        print(f"  {RED}Ошибок:{RESET}       {self.failed}")
        print()
        return self.failed == 0


def check_db_exists(chk: Checker) -> bool:
    if not os.path.exists(DB_FILE):
        chk.fail(f"БД не найдена: {DB_FILE}")
        return False
    size_mb = os.path.getsize(DB_FILE) / (1024 * 1024)
    chk.ok(f"БД найдена: {size_mb:.1f} МБ")
    return True


def check_integrity(chk: Checker, conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("PRAGMA integrity_check")
    result = cur.fetchone()[0]
    if result == "ok":
        chk.ok("PRAGMA integrity_check: ok (файл БД цел)")
    else:
        chk.fail(f"PRAGMA integrity_check: {result} (БД битая!)")

    cur.execute("PRAGMA foreign_key_check")
    violations = cur.fetchall()
    if not violations:
        chk.ok("PRAGMA foreign_key_check: 0 нарушений (FK работают)")
    else:
        chk.warn(f"PRAGMA foreign_key_check: {len(violations)} нарушений")
        for v in violations[:3]:
            chk.warn(f"  {v}")


def check_fk_integrity(chk: Checker, conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM blunders")
    total_blunders = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(*) FROM blunders b
        WHERE NOT EXISTS (SELECT 1 FROM games g WHERE g.url = b.game_url)
    """)
    orphans = cur.fetchone()[0]

    if orphans == 0:
        chk.ok(f"FK целостность: {total_blunders} зевков, 0 orphans")
    else:
        chk.fail(f"FK нарушена: {orphans} зевков ссылаются на несуществующие игры")


def check_duplicates(chk: Checker, conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM games")
    n_games = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT url, COUNT(*) as cnt
            FROM games GROUP BY url HAVING cnt > 1
        )
    """)
    dups = cur.fetchone()[0]

    if dups == 0:
        chk.ok(f"Уникальность games: {n_games} партий, 0 дубликатов")
    else:
        chk.fail(f"Найдено {dups} дубликатов url в games")


def check_duplicate_pgn(chk: Checker, conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT pgn, COUNT(*) as cnt
            FROM games
            WHERE pgn IS NOT NULL AND pgn != ''
            GROUP BY pgn HAVING cnt > 1
        )
    """)
    dups = cur.fetchone()[0]
    if dups == 0:
        chk.ok("Дубликаты PGN: 0 (все партии уникальны)")
    else:
        chk.warn(f"Дубликаты PGN: {dups} (одна партия сыграна дважды)")


def check_next_move_time(chk: Checker, conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM blunders WHERE is_my_blunder = 1")
    total = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(*) FROM blunders
        WHERE is_my_blunder = 1 AND next_move_time IS NOT NULL
    """)
    filled = cur.fetchone()[0]

    if total == 0:
        chk.warn("next_move_time: нет зевков для проверки")
        return

    pct = filled / total * 100
    if pct >= 90:
        chk.ok(f"next_move_time: {filled}/{total} ({pct:.1f}%) заполнено")
    elif pct >= 50:
        chk.warn(f"next_move_time: {filled}/{total} ({pct:.1f}%) — меньше 90%")
    else:
        chk.fail(f"next_move_time: только {filled}/{total} ({pct:.1f}%) — Tilt Timer сломан")


def check_acpl_sanity(chk: Checker, conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE acpl > 0),
            MIN(CASE WHEN acpl > 0 THEN acpl END),
            MAX(CASE WHEN acpl > 0 THEN acpl END),
            AVG(CASE WHEN acpl > 0 THEN acpl END)
        FROM games
        WHERE is_lag=0 AND is_cheater=0
    """)
    n, mn, mx, avg = cur.fetchone()

    if n == 0:
        chk.warn("ACPL: нет партий с acpl > 0")
        return

    issues = []
    if mn < 5:
        issues.append(f"min={mn:.1f} (слишком мало)")
    if mx > 500:
        issues.append(f"max={mx:.1f} (слишком много)")
    if avg < 20 or avg > 150:
        issues.append(f"avg={avg:.1f} (вне нормы 20-150)")

    if issues:
        chk.warn(f"ACPL sanity: {'; '.join(issues)}")
    else:
        chk.ok(f"ACPL: n={n}, min={mn:.0f}, avg={avg:.0f}, max={mx:.0f}")


def check_opening_line(chk: Checker, conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM games WHERE is_lag=0 AND is_cheater=0")
    total = cur.fetchone()[0] or 1

    cur.execute("""
        SELECT COUNT(*) FROM games
        WHERE is_lag=0 AND is_cheater=0
          AND opening_line IS NOT NULL AND opening_line != ''
    """)
    filled = cur.fetchone()[0]
    pct = filled / total * 100

    if pct >= 95:
        chk.ok(f"opening_line: {filled}/{total} ({pct:.1f}%) заполнено")
    elif pct >= 50:
        chk.warn(f"opening_line: {filled}/{total} ({pct:.1f}%) — меньше 95%.")
    else:
        chk.fail(f"opening_line: только {filled}/{total} ({pct:.1f}%)")


def check_stockfish_cache(chk: Checker):
    if not os.path.exists(STOCKFISH_CACHE):
        chk.warn(f"stockfish_cache.json не найден")
        return

    size_mb = os.path.getsize(STOCKFISH_CACHE) / (1024 * 1024)
    try:
        with open(STOCKFISH_CACHE, "r", encoding="utf-8") as f:
            cache = json.load(f)
        if not isinstance(cache, dict):
            chk.fail(f"stockfish_cache: не dict")
            return
        n = len(cache)
        sample_key = next(iter(cache))
        sample = cache[sample_key]
        required = ("acpl", "blunders", "pgn")
        missing = [r for r in required if r not in sample]
        if missing:
            chk.warn(f"stockfish_cache: {n} партий, но у sample нет {missing}")
        else:
            chk.ok(f"stockfish_cache: {n} партий ({size_mb:.1f} МБ)")
    except json.JSONDecodeError as e:
        chk.fail(f"stockfish_cache: битый JSON — {e}")


def main():
    print("=" * 60)
    print(" 00_data_quality.py — Кросс-проверки целостности (v25.0)")
    print("=" * 60)
    print()

    chk = Checker()

    if not check_db_exists(chk):
        chk.summary()
        return 1

    conn = sqlite3.connect(DB_FILE)
    try:
        check_integrity(chk, conn)
        check_fk_integrity(chk, conn)
        check_duplicates(chk, conn)
        check_duplicate_pgn(chk, conn)
        check_next_move_time(chk, conn)
        check_acpl_sanity(chk, conn)
        check_opening_line(chk, conn)
    finally:
        conn.close()

    check_stockfish_cache(chk)

    ok = chk.summary()

    report_path = os.path.join(REPORTS_DIR, "data_quality.txt")
    os.makedirs(REPORTS_DIR, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("=" * 60 + "\n")
        f.write(" DATA QUALITY REPORT (v25.0)\n")
        f.write("=" * 60 + "\n\n")
        for m in chk.messages:
            clean = m
            for c in (GREEN, YELLOW, RED, CYAN, RESET):
                clean = clean.replace(c, "")
            f.write(clean + "\n")
        f.write(f"\nИтог: passed={chk.passed}, warnings={chk.warnings}, failed={chk.failed}\n")
    print(f"\n📄 Отчёт: {report_path}")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())