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
    # timeout=30 решает проблему блокировки базы при параллельной записи
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn

def _execute_with_retry(query, params):
    """Помогает избежать ошибки 'database is locked'."""
    for attempt in range(5):
        try:
            conn = _conn()
            conn.execute(query, params)
            conn.commit()
            conn.close()
            return True
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower():
                time.sleep(0.5 * (attempt + 1))
                continue
            else:
                break
        except Exception:
            break
    return False

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
        pass

def task_hash(task_type: str, fen: str) -> str:
    return hashlib.sha256(f"{task_type}:{fen}".encode("utf-8")).hexdigest()[:16]

def _update_session(task_type, fen, status):
    if "trainer_session" not in st.session_state:
        st.session_state["trainer_session"] = {}
    h = task_hash(task_type, fen)
    st.session_state["trainer_session"][h] = {
        "status": status, "fen": fen, "task_type": task_type, "ts": time.time()
    }

def mark_solved(task_type: str, fen: str):
    _update_session(task_type, fen, "solved")
    now = int(time.time())
    _execute_with_retry("""
        INSERT INTO trainer_progress (task_hash, task_type, fen, status, attempts, last_seen, next_review, created_at)
        VALUES (?, ?, ?, 'solved', 1, ?, NULL, ?)
        ON CONFLICT(task_hash) DO UPDATE SET status = 'solved', attempts = attempts + 1, last_seen = excluded.last_seen, next_review = NULL
    """, (task_hash(task_type, fen), task_type, fen, now, now))

def mark_failed(task_type: str, fen: str, retry_days: int = 3):
    _update_session(task_type, fen, "failed")
    now = int(time.time())
    next_review = now + retry_days * 86400
    _execute_with_retry("""
        INSERT INTO trainer_progress (task_hash, task_type, fen, status, attempts, last_seen, next_review, created_at)
        VALUES (?, ?, ?, 'failed', 1, ?, ?, ?)
        ON CONFLICT(task_hash) DO UPDATE SET status = 'failed', attempts = attempts + 1, last_seen = excluded.last_seen, next_review = excluded.next_review
    """, (task_hash(task_type, fen), task_type, fen, now, next_review, now))

def mark_skipped(task_type: str, fen: str):
    _update_session(task_type, fen, "skipped")
    now = int(time.time())
    next_review = now + 86400
    _execute_with_retry("""
        INSERT INTO trainer_progress (task_hash, task_type, fen, status, attempts, last_seen, next_review, created_at)
        VALUES (?, ?, ?, 'skipped', 1, ?, ?, ?)
        ON CONFLICT(task_hash) DO UPDATE SET status = 'skipped', attempts = attempts + 1, last_seen = excluded.last_seen, next_review = excluded.next_review
    """, (task_hash(task_type, fen), task_type, fen, now, next_review, now))

def get_status(task_type: str, fen: str) -> dict:
    h = task_hash(task_type, fen)
    if "trainer_session" in st.session_state and h in st.session_state["trainer_session"]:
        sess_data = st.session_state["trainer_session"][h]
        return {"status": sess_data["status"], "attempts": 1, "last_seen": sess_data["ts"], "next_review": None}
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
    if "trainer_session" in st.session_state:
        for h, data in st.session_state["trainer_session"].items():
            if data["task_type"] == task_type and data["status"] in ("solved", "skipped", "failed"):
                active.add(data["fen"])
    return active

def get_stats() -> dict:
    result = {"solved": {"n": 0, "attempts": 0}, "failed": {"n": 0, "attempts": 0}, "skipped": {"n": 0, "attempts": 0}}
    try:
        conn = _conn()
        for status in ("solved", "failed", "skipped"):
            row = conn.execute("SELECT COUNT(*) as n, SUM(attempts) as att FROM trainer_progress WHERE status = ?", (status,)).fetchone()
            result[status]["n"] = row["n"] or 0
            result[status]["attempts"] = row["att"] or 0
        conn.close()
    except Exception:
        pass
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
    try:
        conn = _conn()
        rows = conn.execute("SELECT task_type, fen, status, attempts, last_seen, created_at FROM trainer_progress WHERE status = 'solved' ORDER BY last_seen DESC LIMIT ?", (limit,)).fetchall()
        res.extend([dict(r) for r in rows])
        conn.close()
    except Exception:
        pass
    if "trainer_session" in st.session_state:
        for h, data in st.session_state["trainer_session"].items():
            if data["status"] == "solved":
                if not any(r["fen"] == data["fen"] for r in res):
                    res.append({"task_type": data["task_type"], "fen": data["fen"], "status": "solved", "attempts": 1, "last_seen": data["ts"], "created_at": data["ts"]})
    res.sort(key=lambda x: x["last_seen"], reverse=True)
    return res[:limit]

def reset_task(task_type: str, fen: str):
    h = task_hash(task_type, fen)
    _execute_with_retry("DELETE FROM trainer_progress WHERE task_hash = ?", (h,))
    if "trainer_session" in st.session_state and h in st.session_state["trainer_session"]:
        del st.session_state["trainer_session"][h]