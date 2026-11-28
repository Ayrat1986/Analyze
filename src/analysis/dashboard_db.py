# ============================================================
# analysis/dashboard_db.py — v27.5
# Подключение к БД (SQLite / Turso), перцентили, клинок и агрессия PGN.
# ============================================================
import os
import re
import sqlite3
import statistics
import _common
from analysis.common import PLAYER

HAS_TURSO = False
if os.environ.get("GITHUB_ACTIONS") != "true":
    try:
        from web_dashboard.utils.db import get_connection
        HAS_TURSO = True
    except ImportError:
        HAS_TURSO = False

DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")

_SAN_TOKEN_RE = re.compile(
    r"^(?:O-O-O|O-O|[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?[+#]?)$"
)

DASHBOARD_FILES = [
    ("01_openings.txt", "Дебюты: planner, репертуар, шпаргалки"),
    ("02_middlegame.txt", "Миттельшпиль: ACPL, план, тактика"),
    ("03_endgame.txt", "Эндшпиль: техника, флаги, берсерк"),
    ("04_psych_focus.txt", "Зевки: анатомия, первый, missed"),
    ("05_psych_state.txt", "Время, режим, тильт, выносливость"),
    ("06_psych_rating.txt", "Рейтинг, прогресс, потенциал"),
    ("07_opponents.txt", "Соперники: стиль, crushed_by, deep"),
    ("08_coach.txt", "Тренер: совет дня, план, колода"),
]


def get_conn():
    """Универсальное подключение: Turso (в облаке) или локальный SQLite."""
    if HAS_TURSO:
        try:
            return get_connection()
        except Exception:
            pass
    return sqlite3.connect(DB_FILE)


def get_blade_state(combr: float) -> str:
    if combr >= 2650:
        return "🗡️ Острый Клинок"
    if combr >= 2550:
        return "⚔️ Боевой Клинок"
    if combr >= 2450:
        return "🪵 Тупеющий Клинок"
    if combr >= 2300:
        return "🧱 Тупой Клинок"
    return "💀 Сломанный Клинок"


def percentile(sorted_vals: list, q: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    pos = (len(sorted_vals) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = pos - lo
    return float(sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac)


def game_aggr_scores(cur, cutoff_ts: int) -> list:
    """Индексы агрессии (шкала ~0..10, база 7.8) по каждой партии за окно."""
    scores = []
    try:
        cur.execute(
            """
            SELECT pgn, white FROM games
            WHERE is_lag=0 AND is_cheater=0 AND end_time >= ?
              AND pgn IS NOT NULL AND pgn != ''
            """,
            (cutoff_ts,),
        )
        for pgn, white in cur.fetchall():
            is_white = (white == PLAYER)
            body = re.sub(r"\[[^\]]*\]", " ", pgn)
            body = re.sub(r"\{[^}]*\}", " ", body)
            body = re.sub(r"\b\d+\.(?:\.\.)?", " ", body)
            tokens = [t for t in body.split() if _SAN_TOKEN_RE.match(t)]
            my_moves = tokens[0::2] if is_white else tokens[1::2]
            if not my_moves:
                continue
            aggr_moves = sum(1 for m in my_moves if ("x" in m or "+" in m or "#" in m))
            aggr_pct = (aggr_moves / len(my_moves)) * 100.0
            scores.append(aggr_pct * (7.8 / 28.0))
    except Exception:
        pass
    return scores


def calc_aggr_score_from_pgn(cur, cutoff_ts: int) -> float:
    scores = game_aggr_scores(cur, cutoff_ts)
    if scores:
        return round(statistics.mean(scores), 2)
    return 7.8