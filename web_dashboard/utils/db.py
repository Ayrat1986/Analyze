# web_dashboard/utils/db.py — Подключение к chess.db + кэш
# ============================================================
# Подключение к Turso (libSQL) для Streamlit.
# Заменяет sqlite3.connect() на удалённое соединение.
# ============================================================
import os
from typing import Any, List, Optional
import sqlite3
import pandas as pd
import streamlit as st

DB_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "chess.db"
))

try:
    import libsql_client
    _USE_LIBSQL_CLIENT = True
except ModuleNotFoundError:
    # Если libsql_client не установлен, попробуем libsql_experimental
    try:
        import libsql_experimental as libsql
        _USE_LIBSQL_CLIENT = False
    except ModuleNotFoundError:
        raise RuntimeError(
            "Установите libsql-client: pip install libsql-client"
        )


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
        # libsql_client выполняет запросы сразу; явный commit не нужен.
        return None

    def rollback(self):
        return None

    def close(self):
        close_fn = getattr(self._client, "close", None)
        if callable(close_fn):
            close_fn()


@st.cache_resource(show_spinner="Подключение к Turso…")
def get_connection():
    """
    Возвращает соединение с Turso.
    Кэшируется Streamlit, чтобы не открывать новое соединение при каждом запросе.
    """
    # Читаем секреты из Streamlit
    url = st.secrets.get("turso", {}).get("url")
    token = st.secrets.get("turso", {}).get("token")

    # Если секретов нет, пробуем переменные окружения (для локальной разработки)
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
        # libsql_client ожидает https:// вместо libsql://
        if url.startswith("libsql://"):
            url = "https://" + url[len("libsql://"):]
        client = libsql_client.create_client_sync(url, auth_token=token)
        return _LibsqlClientConnection(client)
    else:
        # libsql_experimental принимает libsql:// напрямую
        return libsql.connect(database=url, auth_token=token)


def query_df(sql: str, params=None) -> pd.DataFrame:
    """
    Выполняет SQL-запрос и возвращает DataFrame.
    Удобно для страниц Streamlit, которые читают данные для отображения.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(sql, params or ())
    if cur.description is None:
        return pd.DataFrame()
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    return pd.DataFrame(rows, columns=cols)
    
@st.cache_resource
def get_connection():
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"Нет базы: {DB_PATH}")
    # check_same_thread=False нужен для Streamlit
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _get_db_mtime() -> float:
    """Время последнего изменения chess.db (для сброса кэша)."""
    if os.path.exists(DB_PATH):
        return os.path.getmtime(DB_PATH)
    return 0.0


@st.cache_data(ttl=300)
def _query_df_cached(sql: str, params: tuple, db_mtime: float) -> pd.DataFrame:
    """Внутренняя функция: кэшируется по SQL + параметрам + mtime."""
    conn = get_connection()
    return pd.read_sql_query(sql, conn, params=params)


def query_df(sql: str, params: tuple = ()) -> pd.DataFrame:
    """
    Возвращает DataFrame. Кэш сбрасывается, если chess.db изменилась.
    mtime передаётся в ключ кэша, поэтому старые данные не залипнут.
    """
    return _query_df_cached(sql, params, _get_db_mtime())

def cutoff_ts(days: int) -> int:
    """Unix-timestamp N дней назад (UTC)."""
    from datetime import datetime, timezone, timedelta
    return int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
