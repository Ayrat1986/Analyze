# web_dashboard/utils/db.py
# ============================================================
# Подключение к Turso (libSQL / HTTP API v2) или локальной
# SQLite (data/chess.db) для Streamlit.
# ============================================================
import base64
import json
import os
import sqlite3
import urllib.request
from pathlib import Path
from typing import Any, List, Optional, Tuple
import pandas as pd
import streamlit as st

_DRIVER = "http"
try:
    import libsql_client
    _DRIVER = "libsql_client"
except ModuleNotFoundError:
    try:
        import libsql_experimental as libsql
        _DRIVER = "libsql_experimental"
    except ModuleNotFoundError:
        _DRIVER = "http"


class _LibsqlClientCursor:
    """Минимальный DB-API-совместимый курсор для libsql_client."""
    def __init__(self, client):
        self._client = client
        self._rows: List[Any] = []
        self._row_index = 0
        self.description = None
        self.rowcount = 0
        self.lastrowid = None

    def execute(self, query: str, params=None):
        result = self._client.execute(query, params or ())
        self._rows = list(result) if result is not None else []
        self._row_index = 0
        columns = getattr(result, "columns", None)
        self.description = [(col,) for col in columns] if columns else None
        self.rowcount = int(getattr(result, "rows_affected", 0) or 0)
        self.lastrowid = getattr(result, "last_insert_rowid", None)
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


class _LibsqlClientConnection:
    """Обёртка соединения libsql_client под интерфейс sqlite3.Connection."""
    def __init__(self, client):
        self._client = client

    def cursor(self):
        return _LibsqlClientCursor(self._client)

    def commit(self):
        return None

    def rollback(self):
        return None

    def close(self):
        close_fn = getattr(self._client, "close", None)
        if callable(close_fn):
            close_fn()


def _encode_http_arg(val: Any) -> dict:
    if val is None:
        return {"type": "null"}
    if isinstance(val, bool):
        return {"type": "integer", "value": "1" if val else "0"}
    if isinstance(val, int):
        return {"type": "integer", "value": str(val)}
    if isinstance(val, float):
        return {"type": "float", "value": val}
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

    def execute(self, query: str, params=None):
        stmt: dict = {"sql": query}
        if isinstance(params, dict):
            stmt["named_args"] = [
                {"name": str(k).lstrip(":@$"), "value": _encode_http_arg(v)}
                for k, v in params.items()
            ]
        elif params:
            stmt["args"] = [_encode_http_arg(p) for p in params]

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
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        first = data["results"][0]
        if first.get("type") == "error":
            raise RuntimeError(f"Turso SQL error: {first.get('error')}")

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
    return url, token


def _find_local_sqlite() -> Optional[Path]:
    """Ищет локальную БД data/chess.db относительно корня проекта."""
    local_db = Path(__file__).resolve().parents[2] / "data" / "chess.db"
    return local_db if local_db.exists() else None


@st.cache_resource(show_spinner="Подключение к базе данных…")
def get_connection():
    """Возвращает соединение с Turso, а при отсутствии секретов — с локальной chess.db."""
    url, token = _get_turso_credentials()

    if url and token:
        if _DRIVER == "libsql_client":
            if url.startswith("libsql://"):
                url = "https://" + url[len("libsql://"):]
            client = libsql_client.create_client_sync(url, auth_token=token)
            return _LibsqlClientConnection(client)

        if _DRIVER == "libsql_experimental":
            return libsql.connect(database=url, auth_token=token)

        if url.startswith("libsql://"):
            url = "https://" + url[len("libsql://"):]
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