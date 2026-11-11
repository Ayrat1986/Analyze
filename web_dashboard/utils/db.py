# web_dashboard/utils/db.py — Подключение к chess.db + кэш
import os
import sqlite3
import pandas as pd
import streamlit as st

DB_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "chess.db"
))


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