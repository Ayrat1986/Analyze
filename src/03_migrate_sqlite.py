# ============================================================
# 03_migrate_sqlite.py — v25.1
# P2: INSERT OR REPLACE → ON CONFLICT(url) DO UPDATE SET.
# FIX: Исправлено количество плейсхолдеров (было 54, нужно 53).
# ============================================================
import json
import os
import sqlite3
import shutil
import glob
from datetime import datetime

import _common
from core.метрики import game_rating

from analysis.constants import (
    DEPTH, BLUNDER_THRESHOLD,
    NORMAL_TIME, BERSERK_TIME, INSTANT_TIME,
    TRUE_BERSERK_MIN_MOVES, TIME_THRESHOLDS_VERSION
)

CACHE_FILE = str(_common.BASE_DIR / "data" / "stockfish_cache.json")
DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")
BACKUP_DIR = str(_common.BASE_DIR / "data" / "backup")

SCHEMA_VERSION = 22

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    url TEXT PRIMARY KEY, end_time INTEGER NOT NULL, white TEXT, black TEXT, opening TEXT, eco TEXT,
    my_rating INTEGER, opp_rating INTEGER, opp_username TEXT, won INTEGER, draw INTEGER, reason TEXT,
    is_cheater INTEGER, is_lag INTEGER, end_berserk INTEGER, game_length INTEGER, acpl REAL, acpl_normal REAL,
    acpl_berserk REAL, acpl_opening REAL, acpl_middlegame REAL, acpl_endgame REAL, accuracy REAL,
    moves_normal INTEGER, moves_berserk INTEGER, depth INTEGER, analyzed_at TEXT, acpl_opponent_normal REAL,
    acpl_opponent_total REAL, accuracy_opponent REAL, opp_blunders_total INTEGER, eval_final REAL,
    max_eval_advantage REAL, min_eval_advantage REAL, berserk_move_enter INTEGER, berserk_moves_count INTEGER,
    is_true_berserk INTEGER, timeout_at_move INTEGER, timeout_with_clock REAL, eval_after_opening REAL,
    momentum_after_blunder REAL, moves_in_winning_position INTEGER, opening_line TEXT, pgn TEXT,
    clocks TEXT, eval_history TEXT, critical_moments INTEGER, time_control TEXT, game_rating REAL,
    flag_result TEXT, my_clock_at_timeout REAL, opp_clock_at_timeout REAL, opp_style TEXT
);

CREATE TABLE IF NOT EXISTS blunders (
    id INTEGER PRIMARY KEY AUTOINCREMENT, game_url TEXT REFERENCES games(url) ON DELETE CASCADE,
    move_num INTEGER, move_uci TEXT, loss_cp INTEGER, eval_before INTEGER, eval_after INTEGER,
    eval_swing REAL, what TEXT, pattern_tag TEXT, is_berserk INTEGER, is_instant INTEGER, is_normal INTEGER,
    is_my_blunder INTEGER DEFAULT 0, time_spent REAL, player_is_white INTEGER, next_move_time REAL,
    is_next_move_blunder INTEGER DEFAULT 0, ply INTEGER, fen_before TEXT, best_move_uci TEXT,
    missed_threat INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS checkins (
    id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL UNIQUE,
    sleep_hours REAL, mood INTEGER, energy INTEGER, stress INTEGER, note TEXT, created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS trainer_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT, task_hash TEXT UNIQUE NOT NULL, task_type TEXT NOT NULL, fen TEXT NOT NULL,
    status TEXT NOT NULL, attempts INTEGER DEFAULT 1, last_seen INTEGER, next_review INTEGER, created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS monitoring_log (
    date TEXT PRIMARY KEY,
    games INTEGER,
    avg_my_rating REAL,
    avg_opp_rating REAL,
    perf_rating REAL,
    acpl REAL,
    game_r REAL,
    speed_r REAL,
    combined_r REAL,
    delta REAL,
    stddev_acpl REAL,
    aggression REAL,
    hunter_pct REAL,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_games_end_time ON games(end_time);
CREATE INDEX IF NOT EXISTS idx_games_opening ON games(opening);
CREATE INDEX IF NOT EXISTS idx_games_opp ON games(opp_username);
CREATE INDEX IF NOT EXISTS idx_games_true_berserk ON games(is_true_berserk);
CREATE INDEX IF NOT EXISTS idx_games_eco ON games(substr(eco, 1, 3));
CREATE INDEX IF NOT EXISTS idx_blunders_game ON blunders(game_url);
CREATE INDEX IF NOT EXISTS idx_blunders_move ON blunders(move_num);
CREATE INDEX IF NOT EXISTS idx_blunders_mine ON blunders(is_my_blunder);
CREATE INDEX IF NOT EXISTS idx_blunders_loss_cp ON blunders(loss_cp);
CREATE INDEX IF NOT EXISTS idx_checkins_date ON checkins(date);
CREATE INDEX IF NOT EXISTS idx_trainer_next_review ON trainer_progress(next_review);
CREATE INDEX IF NOT EXISTS idx_games_dashboard ON games(end_time, my_rating, opp_rating);
"""

def migrate_schema(conn):
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(games)")
    cols = {row[1] for row in cur.fetchall()}
    new_games_cols = {
        "acpl_opponent_normal": "REAL", "acpl_opponent_total": "REAL",
        "accuracy_opponent": "REAL", "opp_blunders_total": "INTEGER",
        "eval_final": "REAL", "max_eval_advantage": "REAL", "min_eval_advantage": "REAL",
        "berserk_move_enter": "INTEGER", "berserk_moves_count": "INTEGER",
        "is_true_berserk": "INTEGER", "acpl_opening": "REAL",
        "acpl_middlegame": "REAL", "acpl_endgame": "REAL",
        "timeout_at_move": "INTEGER", "timeout_with_clock": "REAL",
        "eval_after_opening": "REAL", "momentum_after_blunder": "REAL",
        "moves_in_winning_position": "INTEGER", "opening_line": "TEXT",
        "pgn": "TEXT", "clocks": "TEXT", "eval_history": "TEXT",
        "critical_moments": "INTEGER", "time_control": "TEXT", "game_rating": "REAL",
        "flag_result": "TEXT", "my_clock_at_timeout": "REAL", "opp_clock_at_timeout": "REAL",
        "opp_style": "TEXT"
    }
    for name, typ in new_games_cols.items():
        if name not in cols:
            conn.execute(f"ALTER TABLE games ADD COLUMN {name} {typ}")
            print(f"  ➕ games.{name} ({typ})")
    conn.commit()

    cur.execute("PRAGMA table_info(blunders)")
    bcols = {row[1] for row in cur.fetchall()}
    new_blunders_cols = {
        "is_my_blunder": "INTEGER DEFAULT 0", "pattern_tag": "TEXT", "eval_swing": "REAL",
        "next_move_time": "REAL", "is_next_move_blunder": "INTEGER DEFAULT 0",
        "ply": "INTEGER", "fen_before": "TEXT", "best_move_uci": "TEXT", "missed_threat": "INTEGER DEFAULT 0",
    }
    for name, typ in new_blunders_cols.items():
        if name not in bcols:
            conn.execute(f"ALTER TABLE blunders ADD COLUMN {name} {typ}")
            print(f"  ➕ blunders.{name} ({typ})")
    conn.commit()

def migrate_version(conn):
    v = conn.execute("PRAGMA user_version").fetchone()[0]
    if v < SCHEMA_VERSION:
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        print(f"📦 Schema version: {v} → {SCHEMA_VERSION}")
    else:
        print(f"📦 Schema version: {v} (актуальна)")
    conn.commit()

def make_backup():
    if not os.path.exists(DB_FILE):
        return
    os.makedirs(BACKUP_DIR, exist_ok=True)
    backup_name = os.path.join(BACKUP_DIR, f"chess_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
    try:
        shutil.copy2(DB_FILE, backup_name)
        print(f"💾 Бэкап: {backup_name}")
        backups = sorted(glob.glob(os.path.join(BACKUP_DIR, "chess_*.db")))
        for old in backups[:-5]:
            os.remove(old)
    except Exception as e:
        print(f"⚠️ Бэкап не удался: {e}")

def clean_orphans(conn):
    cur = conn.cursor()
    cur.execute("DELETE FROM blunders WHERE game_url NOT IN (SELECT url FROM games)")
    orphans = cur.rowcount
    conn.commit()
    if orphans:
        print(f"🧹 Очищено сирот в blunders: {orphans}")
    else:
        print(f"🧹 Сирот нет.")

def check_fk(conn):
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_key_check")
    violations = cur.fetchall()
    if violations:
        print(f"⚠️ FK нарушения: {len(violations)} записей")
        for v in violations[:5]:
            print(f"   {v}")
    else:
        print(f"✅ FK-проверка пройдена (0 нарушений).")

def main():
    print("=" * 60)
    print(" 03_migrate_sqlite.py — v25.1 (ON CONFLICT, fix placeholders)")
    print("=" * 60)

    if not os.path.exists(CACHE_FILE):
        print(f"❌ Не найден {CACHE_FILE}.")
        return

    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        cache = json.load(f)

    if not cache:
        print(f"❌ {CACHE_FILE} пуст.")
        return

    print(f"📂 Загружено из кэша: {len(cache)} партий")
    make_backup()

    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA foreign_keys = ON")
    print(f"✅ PRAGMA foreign_keys = ON")

    conn.executescript(SCHEMA)
    migrate_schema(conn)
    migrate_version(conn)
    clean_orphans(conn)

    games_inserted = 0
    blunders_inserted = 0
    blunders_with_fen = 0

    # 53 колонки = 53 знака вопроса
    UPSERT_GAMES = """
        INSERT INTO games
        (url, end_time, white, black, opening, eco, my_rating, opp_rating, opp_username,
         won, draw, reason, is_cheater, is_lag, end_berserk, game_length,
         acpl, acpl_normal, acpl_berserk, accuracy, moves_normal, moves_berserk, depth,
         analyzed_at, acpl_opponent_normal, acpl_opponent_total, accuracy_opponent,
         opp_blunders_total, eval_final, max_eval_advantage, min_eval_advantage,
         berserk_move_enter, berserk_moves_count, is_true_berserk,
         acpl_opening, acpl_middlegame, acpl_endgame,
         timeout_at_move, timeout_with_clock, eval_after_opening,
         momentum_after_blunder, moves_in_winning_position, opening_line,
         pgn, clocks, eval_history, critical_moments, time_control, game_rating,
         flag_result, my_clock_at_timeout, opp_clock_at_timeout, opp_style)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(url) DO UPDATE SET
            end_time = excluded.end_time,
            white = excluded.white,
            black = excluded.black,
            opening = excluded.opening,
            eco = excluded.eco,
            my_rating = excluded.my_rating,
            opp_rating = excluded.opp_rating,
            opp_username = excluded.opp_username,
            won = excluded.won,
            draw = excluded.draw,
            reason = excluded.reason,
            is_cheater = excluded.is_cheater,
            is_lag = excluded.is_lag,
            end_berserk = excluded.end_berserk,
            game_length = excluded.game_length,
            acpl = excluded.acpl,
            acpl_normal = excluded.acpl_normal,
            acpl_berserk = excluded.acpl_berserk,
            accuracy = excluded.accuracy,
            moves_normal = excluded.moves_normal,
            moves_berserk = excluded.moves_berserk,
            depth = excluded.depth,
            analyzed_at = excluded.analyzed_at,
            acpl_opponent_normal = excluded.acpl_opponent_normal,
            acpl_opponent_total = excluded.acpl_opponent_total,
            accuracy_opponent = excluded.accuracy_opponent,
            opp_blunders_total = excluded.opp_blunders_total,
            eval_final = excluded.eval_final,
            max_eval_advantage = excluded.max_eval_advantage,
            min_eval_advantage = excluded.min_eval_advantage,
            berserk_move_enter = excluded.berserk_move_enter,
            berserk_moves_count = excluded.berserk_moves_count,
            is_true_berserk = excluded.is_true_berserk,
            acpl_opening = excluded.acpl_opening,
            acpl_middlegame = excluded.acpl_middlegame,
            acpl_endgame = excluded.acpl_endgame,
            timeout_at_move = excluded.timeout_at_move,
            timeout_with_clock = excluded.timeout_with_clock,
            eval_after_opening = excluded.eval_after_opening,
            momentum_after_blunder = excluded.momentum_after_blunder,
            moves_in_winning_position = excluded.moves_in_winning_position,
            opening_line = excluded.opening_line,
            pgn = excluded.pgn,
            clocks = excluded.clocks,
            eval_history = excluded.eval_history,
            critical_moments = excluded.critical_moments,
            time_control = excluded.time_control,
            game_rating = excluded.game_rating,
            flag_result = excluded.flag_result,
            my_clock_at_timeout = excluded.my_clock_at_timeout,
            opp_clock_at_timeout = excluded.opp_clock_at_timeout,
            opp_style = excluded.opp_style
    """

    for url, r in cache.items():
        # Пропускаем служебные ключи
        if not isinstance(r, dict):
            continue

        conn.execute("DELETE FROM blunders WHERE game_url = ?", (url,))
        clocks_json = json.dumps(r.get("clocks", []), ensure_ascii=False)
        eval_history_json = json.dumps(r.get("eval_history", []), ensure_ascii=False)
        gr = game_rating(r.get("acpl", 0))

        conn.execute(UPSERT_GAMES, (
            url, r.get("end_time", 0), r.get("white"), r.get("black"),
            r.get("opening"), r.get("eco"),
            r.get("my_rating", 0), r.get("opponent_rating", 0), r.get("opponent_username"),
            int(bool(r.get("won"))), int(bool(r.get("draw"))), r.get("reason"),
            int(bool(r.get("is_cheater"))), int(bool(r.get("is_lag"))),
            int(bool(r.get("end_berserk"))), r.get("game_length", 0),
            r.get("acpl", 0), r.get("acpl_normal", 0), r.get("acpl_berserk", 0),
            r.get("accuracy", 0), r.get("moves_normal", 0), r.get("moves_berserk", 0),
            r.get("depth", 0), r.get("analyzed_at"),
            r.get("acpl_opponent_normal", 0), r.get("acpl_opponent_total", 0),
            r.get("accuracy_opponent", 0), r.get("opp_blunders_total", 0),
            r.get("eval_final", 0), r.get("max_eval_advantage", 0), r.get("min_eval_advantage", 0),
            r.get("berserk_move_enter"), r.get("berserk_moves_count", 0),
            int(bool(r.get("is_true_berserk", False))),
            r.get("acpl_opening", 0), r.get("acpl_middlegame", 0), r.get("acpl_endgame", 0),
            r.get("timeout_at_move"), r.get("timeout_with_clock"),
            r.get("eval_after_opening", 0), r.get("momentum_after_blunder", 0),
            r.get("moves_in_winning_position", 0), r.get("opening_line", ""),
            r.get("pgn", ""), clocks_json, eval_history_json,
            r.get("critical_moments", 0), r.get("time_control", "unknown"), gr,
            r.get("flag_result"), r.get("my_clock_at_timeout"), r.get("opp_clock_at_timeout"),
            r.get("opp_style", "unknown")
        ))
        games_inserted += 1

        for b in r.get("blunders", []):
            fen_before = b.get("fen_before")
            if fen_before:
                blunders_with_fen += 1
            conn.execute("""
                INSERT INTO blunders
                (game_url, move_num, move_uci, loss_cp, eval_before, eval_after,
                 eval_swing, what, pattern_tag, is_berserk, is_instant, is_normal,
                 is_my_blunder, time_spent, player_is_white,
                 next_move_time, is_next_move_blunder, ply, fen_before, best_move_uci, missed_threat)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                url, b.get("move_num"), b.get("move"), b.get("loss"),
                b.get("eval_before"), b.get("eval_after"), b.get("eval_swing", 0),
                b.get("what"), b.get("pattern_tag", "blunder"),
                int(bool(b.get("is_berserk"))), int(bool(b.get("is_instant"))), int(bool(b.get("is_normal"))),
                int(bool(b.get("is_my_blunder", False))), b.get("time_spent", 0), int(bool(b.get("player_is_white"))),
                b.get("next_move_time"), int(bool(b.get("is_next_move_blunder", False))), b.get("ply"),
                fen_before, b.get("best_move_uci"), int(bool(b.get("missed_threat", False))),
            ))
            blunders_inserted += 1

    conn.commit()
    check_fk(conn)
    conn.close()

    print(f"\n✅ Готово: {DB_FILE}")
    print(f"   Партий:              {games_inserted}")
    print(f"   Зевков:              {blunders_inserted}")
    print(f"   Из них с fen_before: {blunders_with_fen}")


if __name__ == "__main__":
    main()