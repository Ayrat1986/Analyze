# web_dashboard/utils/trainer_db.py
import sqlite3
import hashlib
import os
import time
import streamlit as st

DB_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "chess.db"
))

def _conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def ensure_table():
    try:
        conn = _conn()
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
        conn.commit()
        conn.close()
    except Exception:
        pass # Если облако не разрешает запись, таблица уже есть в базе

def task_hash(task_type: str, fen: str) -> str:
    return hashlib.sha256(f"{task_type}:{fen}".encode("utf-8")).hexdigest()[:16]

def _update_session(task_type, fen, status):
    """Сохраняет статус в память сессии (работает даже на облаке)."""
    if "trainer_session" not in st.session_state:
        st.session_state["trainer_session"] = {}
    h = task_hash(task_type, fen)
    st.session_state["trainer_session"][h] = {
        "status": status, "fen": fen, "task_type": task_type, "ts": time.time()
    }

def mark_solved(task_type: str, fen: str):
    _update_session(task_type, fen, "solved")
    try:
        now = int(time.time())
        conn = _conn()
        conn.execute("""
            INSERT INTO trainer_progress
                (task_hash, task_type, fen, status, attempts, last_seen, next_review, created_at)
            VALUES (?, ?, ?, 'solved', 1, ?, NULL, ?)
            ON CONFLICT(task_hash) DO UPDATE SET
                status = 'solved', attempts = attempts + 1, last_seen = excluded.last_seen, next_review = NULL
        """, (task_hash(task_type, fen), task_type, fen, now, now))
        conn.commit()
        conn.close()
    except Exception:
        pass # Игнорируем ошибку "read-only" на облаке

def mark_failed(task_type: str, fen: str, retry_days: int = 3):
    _update_session(task_type, fen, "failed")
    try:
        now = int(time.time())
        next_review = now + retry_days * 86400
        conn = _conn()
        conn.execute("""
            INSERT INTO trainer_progress
                (task_hash, task_type, fen, status, attempts, last_seen, next_review, created_at)
            VALUES (?, ?, ?, 'failed', 1, ?, ?, ?)
            ON CONFLICT(task_hash) DO UPDATE SET
                status = 'failed', attempts = attempts + 1, last_seen = excluded.last_seen, next_review = excluded.next_review
        """, (task_hash(task_type, fen), task_type, fen, now, next_review, now))
        conn.commit()
        conn.close()
    except Exception:
        pass

def mark_skipped(task_type: str, fen: str):
    _update_session(task_type, fen, "skipped")
    try:
        now = int(time.time())
        next_review = now + 86400
        conn = _conn()
        conn.execute("""
            INSERT INTO trainer_progress
                (task_hash, task_type, fen, status, attempts, last_seen, next_review, created_at)
            VALUES (?, ?, ?, 'skipped', 1, ?, ?, ?)
            ON CONFLICT(task_hash) DO UPDATE SET
                status = 'skipped', attempts = attempts + 1, last_seen = excluded.last_seen, next_review = excluded.next_review
        """, (task_hash(task_type, fen), task_type, fen, now, next_review, now))
        conn.commit()
        conn.close()
    except Exception:
        pass

def get_status(task_type: str, fen: str) -> dict:
    h = task_hash(task_type, fen)
    # 1. Проверяем память сессии
    if "trainer_session" in st.session_state and h in st.session_state["trainer_session"]:
        sess_data = st.session_state["trainer_session"][h]
        # Эмуляция структуры ответа БД
        return {"status": sess_data["status"], "attempts": 1, "last_seen": sess_data["ts"], "next_review": None}
    
    # 2. Проверяем БД
    try:
        conn = _conn()
        row = conn.execute("SELECT status, attempts, last_seen, next_review FROM trainer_progress WHERE task_hash = ?", (h,)).fetchone()
        conn.close()
        if row: return dict(row)
    except Exception:
        pass
    return None

def get_active_fens(task_type: str) -> set:
    now = int(time.time())
    active = set()
    
    # 1. Из БД
    try:
        conn = _conn()
        rows = conn.execute("""
            SELECT fen FROM trainer_progress 
            WHERE task_type = ? AND (status = 'solved' OR (next_review IS NOT NULL AND next_review > ?))
        """, (task_type, now)).fetchall()
        active.update({r["fen"] for r in rows})
        conn.close()
    except Exception:
        pass
        
    # 2. Из памяти сессии
    if "trainer_session" in st.session_state:
        for h, data in st.session_state["trainer_session"].items():
            if data["task_type"] == task_type and data["status"] in ("solved", "skipped", "failed"):
                active.add(data["fen"])
                
    return active

def get_stats() -> dict:
    result = {"solved": {"n": 0, "attempts": 0}, "failed": {"n": 0, "attempts": 0}, "skipped": {"n": 0, "attempts": 0}}
    
    # Из БД
    try:
        conn = _conn()
        for status in ("solved", "failed", "skipped"):
            row = conn.execute("SELECT COUNT(*) as n, SUM(attempts) as att FROM trainer_progress WHERE status = ?", (status,)).fetchone()
            result[status]["n"] = row["n"] or 0
            result[status]["attempts"] = row["att"] or 0
        conn.close()
    except Exception:
        pass
        
    # Из сессии (если БД пустая/read-only)
    if "trainer_session" in st.session_state:
        for data in st.session_state["trainer_session"].values():
            status = data["status"]
            if status in result:
                result[status]["n"] += 1
                
    result["total"] = sum(v["n"] for v in result.values() if isinstance(v, dict))
    return result

def get_stats_by_type() -> dict:
    result = {}
    try:
        conn = _conn()
        rows = conn.execute("SELECT task_type, status, COUNT(*) as n FROM trainer_progress GROUP BY task_type, status").fetchall()
        for r in rows:
            tt = r["task_type"]
            if tt not in result: result[tt] = {"solved": 0, "failed": 0, "skipped": 0}
            result[tt][r["status"]] = r["n"]
        conn.close()
    except Exception:
        pass
    return result

def get_archive(limit: int = 100) -> list:
    res = []
    # Из БД
    try:
        conn = _conn()
        rows = conn.execute("SELECT task_type, fen, status, attempts, last_seen, created_at FROM trainer_progress WHERE status = 'solved' ORDER BY last_seen DESC LIMIT ?", (limit,)).fetchall()
        res.extend([dict(r) for r in rows])
        conn.close()
    except Exception:
        pass
        
    # Из сессии
    if "trainer_session" in st.session_state:
        for h, data in st.session_state["trainer_session"].items():
            if data["status"] == "solved":
                # Проверяем, нет ли уже такого в БД
                if not any(r["fen"] == data["fen"] for r in res):
                    res.append({"task_type": data["task_type"], "fen": data["fen"], "status": "solved", "attempts": 1, "last_seen": data["ts"], "created_at": data["ts"]})
                    
    res.sort(key=lambda x: x["last_seen"], reverse=True)
    return res[:limit]

def reset_task(task_type: str, fen: str):
    h = task_hash(task_type, fen)
    try:
        conn = _conn()
        conn.execute("DELETE FROM trainer_progress WHERE task_hash = ?", (h,))
        conn.commit()
        conn.close()
    except Exception:
        pass
    
    if "trainer_session" in st.session_state and h in st.session_state["trainer_session"]:
        del st.session_state["trainer_session"][h]