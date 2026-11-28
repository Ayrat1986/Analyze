# web_dashboard/utils/trainer_db.py
# ============================================================
# Хранение прогресса тренажёра (работает напрямую через Turso
# в облаке и через Turso / chess.db локально).
# ============================================================
import hashlib
import time
import streamlit as st

try:
    from utils.db import get_connection
except ModuleNotFoundError:
    from web_dashboard.utils.db import get_connection


def _execute(query: str, params=()) -> bool:
    for attempt in range(5):
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(query, params)
            conn.commit()
            return True
        except Exception as e:
            if "locked" in str(e).lower():
                time.sleep(0.5 * (attempt + 1))
                continue
            break
    return False


def _fetchall(query: str, params=()) -> list:
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(query, params)
        if cur.description is None:
            return []
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    except Exception:
        return []


def _fetchone(query: str, params=()):
    rows = _fetchall(query, params)
    return rows[0] if rows else None


def ensure_table():
    if st.session_state.get("_trainer_table_ready"):
        return
    ok = _execute("""
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
    if ok:
        st.session_state["_trainer_table_ready"] = True


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
    ensure_table()
    _update_session(task_type, fen, "solved")
    now = int(time.time())
    _execute("""
        INSERT INTO trainer_progress (task_hash, task_type, fen, status, attempts, last_seen, next_review, created_at)
        VALUES (?, ?, ?, 'solved', 1, ?, NULL, ?)
        ON CONFLICT(task_hash) DO UPDATE SET status = 'solved', attempts = attempts + 1, last_seen = excluded.last_seen, next_review = NULL
    """, (task_hash(task_type, fen), task_type, fen, now, now))


def mark_failed(task_type: str, fen: str, retry_days: int = 3):
    ensure_table()
    _update_session(task_type, fen, "failed")
    now = int(time.time())
    next_review = now + retry_days * 86400
    _execute("""
        INSERT INTO trainer_progress (task_hash, task_type, fen, status, attempts, last_seen, next_review, created_at)
        VALUES (?, ?, ?, 'failed', 1, ?, ?, ?)
        ON CONFLICT(task_hash) DO UPDATE SET status = 'failed', attempts = attempts + 1, last_seen = excluded.last_seen, next_review = excluded.next_review
    """, (task_hash(task_type, fen), task_type, fen, now, next_review, now))


def mark_skipped(task_type: str, fen: str):
    ensure_table()
    _update_session(task_type, fen, "skipped")
    now = int(time.time())
    next_review = now + 86400
    _execute("""
        INSERT INTO trainer_progress (task_hash, task_type, fen, status, attempts, last_seen, next_review, created_at)
        VALUES (?, ?, ?, 'skipped', 1, ?, ?, ?)
        ON CONFLICT(task_hash) DO UPDATE SET status = 'skipped', attempts = attempts + 1, last_seen = excluded.last_seen, next_review = excluded.next_review
    """, (task_hash(task_type, fen), task_type, fen, now, next_review, now))


def get_status(task_type: str, fen: str) -> dict:
    h = task_hash(task_type, fen)
    if "trainer_session" in st.session_state and h in st.session_state["trainer_session"]:
        sess_data = st.session_state["trainer_session"][h]
        return {"status": sess_data["status"], "attempts": 1, "last_seen": sess_data["ts"], "next_review": None}
    row = _fetchone(
        "SELECT status, attempts, last_seen, next_review FROM trainer_progress WHERE task_hash = ?",
        (h,),
    )
    return row if row else None


def get_active_fens(task_type: str) -> set:
    now = int(time.time())
    active = set()
    rows = _fetchall("""
        SELECT fen FROM trainer_progress
        WHERE task_type = ? AND (status = 'solved' OR (next_review IS NOT NULL AND next_review > ?))
    """, (task_type, now))
    active.update({r["fen"] for r in rows})
    if "trainer_session" in st.session_state:
        for data in st.session_state["trainer_session"].values():
            if data["task_type"] == task_type and data["status"] in ("solved", "skipped", "failed"):
                active.add(data["fen"])
    return active


def get_stats() -> dict:
    result = {"solved": {"n": 0, "attempts": 0}, "failed": {"n": 0, "attempts": 0}, "skipped": {"n": 0, "attempts": 0}}
    for status in ("solved", "failed", "skipped"):
        row = _fetchone(
            "SELECT COUNT(*) as n, SUM(attempts) as att FROM trainer_progress WHERE status = ?",
            (status,),
        )
        if row:
            result[status]["n"] = row["n"] or 0
            result[status]["attempts"] = row["att"] or 0
    result["total"] = sum(v["n"] for v in result.values() if isinstance(v, dict))
    return result


def get_stats_by_type() -> dict:
    result = {}
    rows = _fetchall("SELECT task_type, status, COUNT(*) as n FROM trainer_progress GROUP BY task_type, status")
    for r in rows:
        tt = r["task_type"]
        if tt not in result:
            result[tt] = {"solved": 0, "failed": 0, "skipped": 0}
        result[tt][r["status"]] = r["n"]
    return result


def get_archive(limit: int = 100) -> list:
    res = _fetchall(
        "SELECT task_type, fen, status, attempts, last_seen, created_at FROM trainer_progress WHERE status = 'solved' ORDER BY last_seen DESC LIMIT ?",
        (limit,),
    )
    if "trainer_session" in st.session_state:
        for data in st.session_state["trainer_session"].values():
            if data["status"] == "solved":
                if not any(r["fen"] == data["fen"] for r in res):
                    res.append({
                        "task_type": data["task_type"],
                        "fen": data["fen"],
                        "status": "solved",
                        "attempts": 1,
                        "last_seen": data["ts"],
                        "created_at": data["ts"],
                    })
    res.sort(key=lambda x: x["last_seen"], reverse=True)
    return res[:limit]


def reset_task(task_type: str, fen: str):
    h = task_hash(task_type, fen)
    _execute("DELETE FROM trainer_progress WHERE task_hash = ?", (h,))
    if "trainer_session" in st.session_state and h in st.session_state["trainer_session"]:
        del st.session_state["trainer_session"][h]