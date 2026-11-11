# web_dashboard/utils/trainer_db.py
"""
Хранилище прогресса тренировок.
Таблица trainer_progress в chess.db.
Веб-слой: только UI, не анализ.
"""
import sqlite3
import hashlib
import os
import time
from datetime import datetime, timezone, timedelta

DB_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "chess.db"
))


def _conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_table():
    """Создаёт таблицу trainer_progress, если её нет."""
    conn = _conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trainer_progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_hash TEXT UNIQUE NOT NULL,
                task_type TEXT NOT NULL,
                fen TEXT NOT NULL,
                status TEXT NOT NULL,
                attempts INTEGER DEFAULT 1,
                last_seen INTEGER,
                next_review INTEGER,
                created_at INTEGER NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_trainer_next_review
            ON trainer_progress(next_review)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_trainer_status
            ON trainer_progress(status)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_trainer_type
            ON trainer_progress(task_type)
        """)
        conn.commit()
    finally:
        conn.close()


def task_hash(task_type: str, fen: str) -> str:
    """Стабильный хеш задачи (тип + FEN). Используется как ключ кнопок."""
    raw = f"{task_type}:{fen}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def mark_solved(task_type: str, fen: str):
    """Задача решена. Уходит в архив (не показывать)."""
    h = task_hash(task_type, fen)
    now = int(time.time())
    conn = _conn()
    try:
        conn.execute("""
            INSERT INTO trainer_progress
                (task_hash, task_type, fen, status, attempts, last_seen, next_review, created_at)
            VALUES (?, ?, ?, 'solved', 1, ?, NULL, ?)
            ON CONFLICT(task_hash) DO UPDATE SET
                status = 'solved',
                attempts = attempts + 1,
                last_seen = excluded.last_seen,
                next_review = NULL
        """, (h, task_type, fen, now, now))
        conn.commit()
    finally:
        conn.close()


def mark_failed(task_type: str, fen: str, retry_days: int = 3):
    """Задача не решена. Вернуть через `retry_days` дней."""
    h = task_hash(task_type, fen)
    now = int(time.time())
    next_review = now + retry_days * 86400
    conn = _conn()
    try:
        conn.execute("""
            INSERT INTO trainer_progress
                (task_hash, task_type, fen, status, attempts, last_seen, next_review, created_at)
            VALUES (?, ?, ?, 'failed', 1, ?, ?, ?)
            ON CONFLICT(task_hash) DO UPDATE SET
                status = 'failed',
                attempts = attempts + 1,
                last_seen = excluded.last_seen,
                next_review = excluded.next_review
        """, (h, task_type, fen, now, next_review, now))
        conn.commit()
    finally:
        conn.close()


def mark_skipped(task_type: str, fen: str):
    """Задача пропущена. Вернуть завтра."""
    h = task_hash(task_type, fen)
    now = int(time.time())
    next_review = now + 86400
    conn = _conn()
    try:
        conn.execute("""
            INSERT INTO trainer_progress
                (task_hash, task_type, fen, status, attempts, last_seen, next_review, created_at)
            VALUES (?, ?, ?, 'skipped', 1, ?, ?, ?)
            ON CONFLICT(task_hash) DO UPDATE SET
                status = 'skipped',
                attempts = attempts + 1,
                last_seen = excluded.last_seen,
                next_review = excluded.next_review
        """, (h, task_type, fen, now, next_review, now))
        conn.commit()
    finally:
        conn.close()


def get_status(task_type: str, fen: str) -> dict:
    """Возвращает статус задачи (или None, если не видели)."""
    h = task_hash(task_type, fen)
    conn = _conn()
    try:
        row = conn.execute("""
            SELECT status, attempts, last_seen, next_review
            FROM trainer_progress WHERE task_hash = ?
        """, (h,)).fetchone()
        if row:
            return dict(row)
        return None
    finally:
        conn.close()


def get_active_fens(task_type: str) -> set:
    """
    Возвращает FEN, которые СЕЙЧАС не надо показывать.
    Сюда входят: solved (навсегда) + failed/skipped с next_review > now.
    """
    now = int(time.time())
    conn = _conn()
    try:
        rows = conn.execute("""
            SELECT fen FROM trainer_progress
            WHERE task_type = ?
              AND (
                status = 'solved'
                OR (next_review IS NOT NULL AND next_review > ?)
              )
        """, (task_type, now)).fetchall()
        return {r["fen"] for r in rows}
    finally:
        conn.close()


def get_stats() -> dict:
    """Общая статистика по тренировкам."""
    conn = _conn()
    try:
        result = {}
        for status in ("solved", "failed", "skipped"):
            row = conn.execute("""
                SELECT COUNT(*) as n, SUM(attempts) as att
                FROM trainer_progress WHERE status = ?
            """, (status,)).fetchone()
            result[status] = {"n": row["n"] or 0, "attempts": row["att"] or 0}
        result["total"] = sum(v["n"] for v in result.values())
        return result
    finally:
        conn.close()


def get_stats_by_type() -> dict:
    """Статистика по типам задач (deck / worst / endgame)."""
    conn = _conn()
    try:
        rows = conn.execute("""
            SELECT task_type, status, COUNT(*) as n
            FROM trainer_progress
            GROUP BY task_type, status
        """).fetchall()
        result = {}
        for r in rows:
            tt = r["task_type"]
            if tt not in result:
                result[tt] = {"solved": 0, "failed": 0, "skipped": 0}
            result[tt][r["status"]] = r["n"]
        return result
    finally:
        conn.close()


def get_archive(limit: int = 100) -> list:
    """Архив решённых задач (для просмотра)."""
    conn = _conn()
    try:
        rows = conn.execute("""
            SELECT task_type, fen, status, attempts, last_seen, created_at
            FROM trainer_progress
            WHERE status = 'solved'
            ORDER BY last_seen DESC LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def reset_task(task_type: str, fen: str):
    """Сбросить задачу (вернуть в очередь)."""
    h = task_hash(task_type, fen)
    conn = _conn()
    try:
        conn.execute("DELETE FROM trainer_progress WHERE task_hash = ?", (h,))
        conn.commit()
    finally:
        conn.close()