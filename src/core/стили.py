# src/core/стили.py
"""
Кэш стилей соперников.
Проблема: classify_opponent_style парсит PGN при каждом вызове.
04, 05 (через build_opponent_style_map), 11 (дважды) вызывают независимо.
Решение: in-memory кэш за процесс. Один парсинг на партию.
"""
import io
from collections import defaultdict

import chess
import chess.pgn

from _chess_utils import (
    classify_opponent_style,
    build_opponent_style_map,
)

# Кэш 1: стиль одной партии. Ключ — (cache_key or hash(pgn), player_is_white).
# cache_key — это url партии (если есть), иначе hash(pgn).
_STYLE_CACHE: dict = {}

# Кэш 2: карта {opp_username: style}. Ключ — (путь_к_БД, player).
_MAP_CACHE: dict = {}


def get_style(pgn, player_is_white, cache_key=None):
    """
    Стиль соперника в одной партии (с кэшем).
    cache_key — url партии; если None, используется hash(pgn).
    """
    key = (cache_key if cache_key is not None else hash(pgn), player_is_white)
    if key in _STYLE_CACHE:
        return _STYLE_CACHE[key]
    style = classify_opponent_style(pgn, player_is_white)
    _STYLE_CACHE[key] = style
    return style


def get_opponent_style_map(conn, player):
    """
    Карта {opp_username: style} по всем соперникам в БД (с кэшем).
    Кэш по (путь_к_БД, player) — переживает повторные вызовы в одном процессе.
    """
    path = str(conn.execute("PRAGMA database_list").fetchone()[2])
    key = (path, player)
    if key in _MAP_CACHE:
        return _MAP_CACHE[key]
    result = build_opponent_style_map(conn, player)
    _MAP_CACHE[key] = result
    return result


def clear_cache():
    """Сброс кэшей. Полезно для тестов."""
    _STYLE_CACHE.clear()
    _MAP_CACHE.clear()