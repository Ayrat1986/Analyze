# web_dashboard/utils/db.py
# ============================================================
# Подключение к Turso (libSQL) для Streamlit.
# Полностью заменяет локальный sqlite3.
# ============================================================
import os
from typing import Any, List, Optional
import pandas as pd
import streamlit as st

try:
    import libsql_client
    _USE_LIBSQL_CLIENT = True
except ModuleNotFoundError:
    try:
        import libsql_experimental as libsql
        _USE_LIBSQL_CLIENT = False
    except ModuleNotFoundError as e:
        raise RuntimeError(
            "Не установлен ни libsql-client, ни libsql-experimental. "
            "Добавьте один из пакетов в requirements.txt."
        ) from e


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


@st.cache_resource(show_spinner="Подключение к Turso…")
def get_connection():
    """Возвращает соединение с Turso (кэшируется Streamlit)."""
    url = st.secrets.get("turso", {}).get("url")
    token = st.secrets.get("turso", {}).get("token")
    if not url:
        url = os.environ.get("TURSO_DATABASE_URL")
    if not token:
        token = os.environ.get("TURSO_AUTH_TOKEN")

    if not url or not token:
        raise RuntimeError(
            "Не заданы TURSO_URL и TURSO_TOKEN. "
            "Добавьте их в Secrets Streamlit или в переменные окружения."
        )

    if _USE_LIBSQL_CLIENT:
        if url.startswith("libsql://"):
            url = "https://" + url[len("libsql://"):]
        client = libsql_client.create_client_sync(url, auth_token=token)
        return _LibsqlClientConnection(client)
    else:
        return libsql.connect(database=url, auth_token=token)


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
