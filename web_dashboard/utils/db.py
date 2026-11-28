# web_dashboard/utils/db.py
# ============================================================
# Подключение к Turso (HTTP Pipeline API v2) или локальной
# SQLite (data/chess.db) для Streamlit.
# ============================================================
import base64
import json
import numbers
import os
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, List, Optional, Tuple
import pandas as pd
import streamlit as st


def _encode_http_arg(val: Any) -> dict:
    if val is None:
        return {"type": "null"}
    if isinstance(val, bool):
        return {"type": "integer", "value": "1" if val else "0"}
    if isinstance(val, numbers.Integral):
        return {"type": "integer", "value": str(int(val))}
    if isinstance(val, numbers.Real):
        return {"type": "float", "value": float(val)}
    if isinstance(val, (bytes, bytearray)):
        return {"type": "blob", "base64": base64.b64encode(bytes(val)).decode("ascii")}
    return {"type": "text", "value": str(val)}


def _decode_http_val(cell: dict) -> Any:
    cell_type = cell.get("type")
    if cell_type == "null":
        return None
    val = cell.get("value")
    if cell_type == "integer":
        return int(val)
    if cell_type == "float":
        return float(val)
    if cell_type == "blob":
        return base64.b64decode(cell.get("base64", ""))
    return val


class _TursoHttpCursor:
    """DB-API-совместимый курсор поверх Turso HTTP Pipeline API v2."""
    def __init__(self, url: str, token: str):
        self._url = url.rstrip("/") + "/v2/pipeline"
        self._token = token
        self._rows: List[tuple] = []
        self._row_index = 0
        self.description = None
        self.rowcount = 0
        self.lastrowid = None

    def _send_stmt(self, query: str, params=None) -> dict:
        stmt: dict = {"sql": query}
        if isinstance(params, dict):
            stmt["named_args"] = [
                {"name": str(k).lstrip(":@$"), "value": _encode_http_arg(v)}
                for k, v in params.items()
            ]
        elif params:
            stmt["args"] = [_encode_http_arg(p) for p in list(params)]

        payload = json.dumps({
            "requests": [
                {"type": "execute", "stmt": stmt},
                {"type": "close"},
            ]
        }).encode("utf-8")

        req = urllib.request.Request(
            self._url,
            data=payload,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            st.error(f"Turso HTTP {e.code}: {err_body}")
            st.stop()

        return data["results"][0]

    def execute(self, query: str, params=None):
        first = self._send_stmt(query, params)
        if first.get("type") == "error":
            err = first.get("error", {})
            msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)

            tables_info = ""
            diag = self._send_stmt("SELECT name FROM sqlite_master WHERE type='table'")
            if diag.get("type") != "error":
                rows = diag["response"]["result"].get("rows", [])
                tables = [r[0].get("value") for r in rows if r]
                tables_info = f"\n\nТаблицы в базе Turso: {tables or 'пусто (0 таблиц)'}"

            st.error(f"Turso SQL error: {msg}{tables_info}")
            st.stop()

        res = first["response"]["result"]
        cols = [c["name"] for c in res.get("cols", [])]
        self.description = [(c,) for c in cols] if cols else None
        self._rows = [
            tuple(_decode_http_val(cell) for cell in row)
            for row in res.get("rows", [])
        ]
        self._row_index = 0
        self.rowcount = int(res.get("affected_row_count", 0) or 0)
        self.lastrowid = res.get("last_insert_rowid")
        return self

    def fetchone(self):
        if self._row_index >= len(self._rows):
            return None
        row = self._rows[self._row_index]
        self._row_index += 1
        return row

    def fetchall(self):
        if self._row_index >= len(self._rows):
            return []
        rows = self._rows[self._row_index:]
        self._row_index = len(self._rows)
        return rows


class _TursoHttpConnection:
    """Обёртка HTTP-подключения к Turso под интерфейс sqlite3.Connection."""
    def __init__(self, url: str, token: str):
        self._url = url
        self._token = token

    def cursor(self):
        return _TursoHttpCursor(self._url, self._token)

    def commit(self):
        return None

    def rollback(self):
        return None

    def close(self):
        return None


def _get_turso_credentials() -> Tuple[Optional[str], Optional[str]]:
    """Безопасно извлекает URL и токен Turso из st.secrets или env."""
    url: Optional[str] = None
    token: Optional[str] = None
    try:
        turso_sec = st.secrets.get("turso", {})
        if turso_sec:
            url = turso_sec.get("url")
            token = turso_sec.get("token") or turso_sec.get("auth_token")
    except Exception:
        pass

    url = url or os.environ.get("TURSO_DATABASE_URL") or os.environ.get("TURSO_URL")
    token = token or os.environ.get("TURSO_AUTH_TOKEN") or os.environ.get("TURSO_TOKEN")

    if url:
        url = url.strip()
        if url.startswith("libsql://"):
            url = "https://" + url[len("libsql://"):]
        elif url.startswith("wss://"):
            url = "https://" + url[len("wss://"):]
    if token:
        token = token.strip()

    return url, token


def _find_local_sqlite() -> Optional[Path]:
    """Ищет локальную БД data/chess.db относительно корня проекта."""
    local_db = Path(__file__).resolve().parents[2] / "data" / "chess.db"
    return local_db if local_db.exists() else None


@st.cache_resource(show_spinner="Подключение к базе данных…")
def get_connection():
    """Возвращает HTTP-соединение с Turso, а при отсутствии секретов — с локальной chess.db."""
    url, token = _get_turso_credentials()

    if url and token:
        return _TursoHttpConnection(url, token)

    local_db = _find_local_sqlite()
    if local_db is not None:
        return sqlite3.connect(str(local_db), check_same_thread=False)

    raise RuntimeError(
        "Не найдены ни секреты Turso (TURSO_DATABASE_URL / TURSO_AUTH_TOKEN), "
        "ни локальная база data/chess.db."
    )


@st.cache_data(ttl=60)
def query_df(sql: str, params=None) -> pd.DataFrame:
    """Выполняет SQL и возвращает DataFrame (с кэшем на 60 секунд)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(sql, params or ())
    if cur.description is None:
        return pd.DataFrame()
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    return pd.DataFrame(rows, columns=cols)


def cutoff_ts(days: int) -> int:
    """Unix-timestamp N дней назад (UTC)."""
    from datetime import datetime, timezone, timedelta
    return int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
