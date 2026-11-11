# ============================================================
# analysis/common.py — v20.1 (WAL + оптимизация)
# ============================================================
import os
import sqlite3
from datetime import datetime, timezone, timedelta
import _common

DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")
REPORTS_DIR = str(_common.REPORTS_DIR)
PLAYER = _common.CONFIG.get("player", "")

WINDOWS = [1, 2, 7, 30, 90, 365]
WINDOW_LABELS = {1: "1 день", 2: "2 дня", 7: "7 дней", 30: "30 дней", 90: "90 дней", 365: "365 дней"}

def window_label(days: int) -> str:
    return WINDOW_LABELS.get(days, f"{days} дней")

def window_cutoff_ts(days: int) -> int:
    return int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())

RATING_BUCKETS = [
    ("< 2400",     0,     2400),
    ("2400-2499",  2400,  2500),
    ("2500-2599",  2500,  2600),
    ("2600-2699",  2600,  2700),
    ("2700-2799",  2700,  2800),
    ("2800+",      2800,  99999),
]
RATING_BUCKET_LABELS = [label for label, _, _ in RATING_BUCKETS]

def rating_bucket(r) -> str:
    if not r or r == 0: return "unknown"
    for label, lo, hi in RATING_BUCKETS:
        if lo <= r < hi: return label
    return "2800+"

def _conn():
    """Подключение с WAL-режимом для параллельного чтения."""
    conn = sqlite3.connect(DB_FILE, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def read_report_file(filename):
    path = os.path.join(REPORTS_DIR, filename)
    if not os.path.exists(path): path = os.path.join(REPORTS_DIR, "dashboards", filename)
    if not os.path.exists(path): return None
    with open(path, "r", encoding="utf-8") as f: return f.read().strip().split("\n")

class ReportWriter:
    def __init__(self, f): self.f = f
    def w(self, line=""): print(line); self.f.write(str(line) + "\n")
    def w_separator(self, char="=", length=60, title=None):
        self.w(char * length)
        if title: self.w(f" {title}"); self.w(char * length)

class ReportContext:
    def __init__(self, name: str, subdir: str = None):
        self.name = name
        if subdir:
            base = os.path.join(REPORTS_DIR, subdir)
            self.path = os.path.join(base, f"{name}.txt")
        else:
            self.path = os.path.join(REPORTS_DIR, f"{name}.txt")
        self.file = None
    def __enter__(self) -> ReportWriter:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.file = open(self.path, "w", encoding="utf-8")
        return ReportWriter(self.file)
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.file: self.file.close()
        if exc_type: print(f"❌ Ошибка в отчёте {self.name}: {exc_val}")
        else: print(f"\n✅ {self.path}")

def report_context(name: str, subdir: str = None) -> ReportContext:
    return ReportContext(name, subdir=subdir)