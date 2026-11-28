# web_dashboard/utils/sync_to_turso.py
# ============================================================
# Двусторонняя синхронизация локальной SQLite (data/chess.db)
# и облачной Turso через HTTP Pipeline API v2.
# ============================================================
import argparse
import base64
import json
import math
import os
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import List, Optional, Tuple

try:
    import tomllib
except ModuleNotFoundError:
    tomllib = None

UTILS_DIR = Path(__file__).resolve().parent
WEB_DIR = UTILS_DIR.parent
BASE_DIR = WEB_DIR.parent

DB_PATH = BASE_DIR / "data" / "chess.db"
STATE_FILE = BASE_DIR / "data" / ".turso_sync_state.json"
LOCK_FILE = BASE_DIR / "data" / ".turso_sync.lock"
BATCH_SIZE = 500


def load_turso_credentials(interactive: bool = False) -> Tuple[Optional[str], Optional[str]]:
    url = os.environ.get("TURSO_DATABASE_URL") or os.environ.get("TURSO_URL")
    token = os.environ.get("TURSO_AUTH_TOKEN") or os.environ.get("TURSO_TOKEN")

    if (not url or not token) and tomllib is not None:
        for secret_file in [
            WEB_DIR / ".streamlit" / "secrets.toml",
            BASE_DIR / ".streamlit" / "secrets.toml",
        ]:
            if secret_file.exists():
                try:
                    data = tomllib.loads(secret_file.read_text(encoding="utf-8"))
                    turso = data.get("turso", {})
                    url = url or turso.get("url")
                    token = token or turso.get("token") or turso.get("auth_token")
                except Exception:
                    pass

    config_file = BASE_DIR / "data" / "config.json"
    if (not url or not token) and config_file.exists():
        try:
            cfg = json.loads(config_file.read_text(encoding="utf-8"))
            turso = cfg.get("turso", {})
            url = url or turso.get("url") or cfg.get("turso_url")
            token = token or turso.get("token") or turso.get("auth_token") or cfg.get("turso_token")
        except Exception:
            pass

    if interactive:
        if not url:
            url = input("Введи Turso URL (libsql://... или https://...): ").strip()
        if not token:
            token = input("Введи Turso Auth Token: ").strip()

    if not url or not token:
        return None, None

    url = url.strip()
    if url.startswith("libsql://"):
        url = "https://" + url[len("libsql://"):]
    elif url.startswith("wss://"):
        url = "https://" + url[len("wss://"):]

    return url.rstrip("/"), token.strip()


def _encode_arg(val) -> dict:
    if val is None:
        return {"type": "null"}
    if isinstance(val, bool):
        return {"type": "integer", "value": "1" if val else "0"}
    if isinstance(val, int):
        return {"type": "integer", "value": str(val)}
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            return {"type": "null"}
        return {"type": "float", "value": val}
    if isinstance(val, (bytes, bytearray)):
        return {"type": "blob", "base64": base64.b64encode(bytes(val)).decode("ascii")}
    return {"type": "text", "value": str(val)}


def _decode_val(cell: dict):
    t = cell.get("type")
    if t == "null":
        return None
    v = cell.get("value")
    if t == "integer":
        return int(v)
    if t == "float":
        return float(v)
    if t == "blob":
        return base64.b64decode(cell.get("base64", ""))
    return v


def _turso_pipeline(pipeline_url: str, token: str, statements: list) -> List[dict]:
    requests_payload = [{"type": "execute", "stmt": s} for s in statements]
    requests_payload.append({"type": "close"})

    req = urllib.request.Request(
        pipeline_url,
        data=json.dumps({"requests": requests_payload}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            res = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Turso HTTP {e.code}: {body}") from e

    results = []
    for item in res.get("results", []):
        if item.get("type") == "error":
            err = item.get("error", {})
            msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            raise RuntimeError(f"Turso SQL error: {msg}")
        if "response" in item and "result" in item["response"]:
            results.append(item["response"]["result"])
    return results


def _turso_query(pipeline_url: str, token: str, sql: str, args: Optional[list] = None) -> Tuple[List[str], List[tuple]]:
    stmt: dict = {"sql": sql}
    if args:
        stmt["args"] = [_encode_arg(a) for a in args]
    res_list = _turso_pipeline(pipeline_url, token, [stmt])
    if not res_list:
        return [], []
    res = res_list[0]
    cols = [c["name"] for c in res.get("cols", [])]
    rows = [tuple(_decode_val(cell) for cell in row) for row in res.get("rows", [])]
    return cols, rows


def _pull_cloud_progress(conn: sqlite3.Connection, pipeline_url: str, token: str, quiet: bool = False):
    _, table_rows = _turso_query(
        pipeline_url, token,
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('trainer_progress', 'checkins')",
    )
    remote_tables = {r[0] for r in table_rows}

    if "trainer_progress" in remote_tables:
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
        cols, rows = _turso_query(
            pipeline_url, token,
            "SELECT task_hash, task_type, fen, status, attempts, last_seen, next_review, created_at FROM trainer_progress",
        )
        if rows:
            for r in rows:
                conn.execute("""
                    INSERT INTO trainer_progress
                        (task_hash, task_type, fen, status, attempts, last_seen, next_review, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(task_hash) DO UPDATE SET
                        status = excluded.status,
                        attempts = MAX(trainer_progress.attempts, excluded.attempts),
                        last_seen = excluded.last_seen,
                        next_review = excluded.next_review
                    WHERE COALESCE(excluded.last_seen, 0) >= COALESCE(trainer_progress.last_seen, 0)
                """, r)
            conn.commit()
            if not quiet:
                print(f"← Подтянуто записей trainer_progress из Turso: {len(rows)}")

    if "checkins" in remote_tables:
        local_exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='checkins'").fetchone()
        if local_exists:
            cols, rows = _turso_query(pipeline_url, token, 'SELECT * FROM "checkins"')
            if cols and rows:
                cols_q = ", ".join(f'"{c}"' for c in cols)
                ph = ", ".join("?" for _ in cols)
                for r in rows:
                    conn.execute(f'INSERT OR REPLACE INTO "checkins" ({cols_q}) VALUES ({ph})', r)
                conn.commit()
                if not quiet:
                    print(f"← Подтянуто записей checkins из Turso: {len(rows)}")


def _acquire_lock() -> bool:
    if LOCK_FILE.exists():
        if time.time() - LOCK_FILE.stat().st_mtime > 300:
            LOCK_FILE.unlink(missing_ok=True)
        else:
            return False
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")
    return True


def _release_lock():
    LOCK_FILE.unlink(missing_ok=True)


def _save_sync_state():
    if not DB_PATH.exists():
        return
    st = DB_PATH.stat()
    STATE_FILE.write_text(
        json.dumps({"db_mtime": st.st_mtime, "db_size": st.st_size, "synced_at": int(time.time())}, indent=2),
        encoding="utf-8",
    )


def is_sync_needed() -> bool:
    if not DB_PATH.exists():
        return False
    url, token = load_turso_credentials(interactive=False)
    if not url or not token:
        return False
    if not STATE_FILE.exists():
        return True
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        st = DB_PATH.stat()
        return (
            abs(st.st_mtime - float(state.get("db_mtime", 0))) > 0.5
            or st.st_size != int(state.get("db_size", -1))
        )
    except Exception:
        return True


def sync_now(interactive: bool = False, quiet: bool = False) -> bool:
    if not DB_PATH.exists():
        if not quiet:
            print(f"⚠️ Локальная база не найдена: {DB_PATH}")
        return False

    base_url, token = load_turso_credentials(interactive=interactive)
    if not base_url or not token:
        if not quiet:
            print("⏩ Синхронизация с Turso пропущена (не заданы URL/Token).")
        return False

    if not _acquire_lock():
        if not quiet:
            print("⏩ Синхронизация с Turso уже выполняется другим процессом.")
        return False

    try:
        pipeline_url = f"{base_url}/v2/pipeline"
        if not quiet:
            print(f"\n☁️ Синхронизация с Turso ({base_url})...")

        conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
        try:
            _pull_cloud_progress(conn, pipeline_url, token, quiet=quiet)

            cur = conn.cursor()
            tables = cur.execute(
                "SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND sql IS NOT NULL"
            ).fetchall()

            for table_name, create_sql in tables:
                if not quiet:
                    print(f"→ Выгрузка таблицы '{table_name}'...")
                _turso_pipeline(pipeline_url, token, [
                    {"sql": f'DROP TABLE IF EXISTS "{table_name}"'},
                    {"sql": create_sql},
                ])

                col_info = cur.execute(f'PRAGMA table_info("{table_name}")').fetchall()
                cols = [c[1] for c in col_info]
                cols_quoted = ", ".join(f'"{c}"' for c in cols)
                placeholders = ", ".join("?" for _ in cols)
                insert_sql = f'INSERT INTO "{table_name}" ({cols_quoted}) VALUES ({placeholders})'

                rows_cur = conn.cursor()
                rows_cur.execute(f'SELECT {cols_quoted} FROM "{table_name}"')

                total = 0
                while True:
                    batch = rows_cur.fetchmany(BATCH_SIZE)
                    if not batch:
                        break
                    stmts = [{"sql": insert_sql, "args": [_encode_arg(v) for v in row]} for row in batch]
                    _turso_pipeline(pipeline_url, token, stmts)
                    total += len(batch)
                    if not quiet:
                        print(f"   загружено строк: {total}", end="\r")

                if not quiet:
                    print(f"   ✅ {table_name}: {total} строк        ")

            indexes = cur.execute("SELECT name, sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL").fetchall()
            if indexes:
                _turso_pipeline(pipeline_url, token, [{"sql": sql} for _, sql in indexes])
        finally:
            conn.close()

        _save_sync_state()
        if not quiet:
            print("✅ База chess.db автоматически синхронизирована с Turso!")
        return True
    finally:
        _release_lock()


def sync_if_needed(quiet: bool = True) -> bool:
    if not is_sync_needed():
        return False
    return sync_now(interactive=False, quiet=quiet)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Синхронизация chess.db с Turso")
    parser.add_argument("--if-needed", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if args.if_needed:
        sync_if_needed(quiet=args.quiet)
    else:
        sync_now(interactive=True, quiet=args.quiet)