# ============================================================
# analysis/openings/planner.py — Opening Planner (v25.1)
# FIX: Убран несуществующий аргумент timeout=30.0 из analyze_fen().
#      Вместо него добавлен time=30.0 внутрь chess.engine.Limit() (§19).
# §P3: analyze_fen — time.sleep(0.5) между попытками.
#      Без sleep — busy-loop при пустом пуле (спин на CPU).
# ============================================================
import os
import sys
import io
import json
import gzip
import queue
import threading
import sqlite3
import statistics
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import chess
import chess.pgn
import chess.engine

import _common

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import PLAYER

DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")
STOCKFISH_PATH = _common.CONFIG.get("stockfish_path", "")
STOCKFISH_CACHE = str(_common.BASE_DIR / "data" / "stockfish_positions_cache.json.gz")
CODEX_RULES_FILE = str(_common.BASE_DIR / "data" / "codex_rules.json")

CACHE_VERSION = "4.9"
NUM_ENGINES = 4
NUM_WORKERS = 2
MAX_RETRIES = 3
USE_STOCKFISH = True

FEN_CACHE = None
ENGINE_POOL = None


# ============================================================
# FEN CACHE
# ============================================================
class FenCache:
    def __init__(self, path=STOCKFISH_CACHE):
        self.path = path
        self.data = {}
        self.lock = threading.Lock()
        self.load()

    def load(self):
        if os.path.exists(self.path):
            try:
                with gzip.open(self.path, "rt", encoding="utf-8") as f:
                    raw = json.load(f)
                if raw.get("version") == CACHE_VERSION:
                    self.data = raw.get("positions", {})
                else:
                    print(f"⚠️ Кэш версии {raw.get('version')} != {CACHE_VERSION} — сброс")
                    self.data = {}
            except Exception:
                self.data = {}
        print(f"📂 FEN-кэш: {len(self.data)} позиций")

    def save(self):
        try:
            with self.lock:
                tmp = self.path + ".tmp"
                with gzip.open(tmp, "wt", encoding="utf-8") as f:
                    json.dump({"version": CACHE_VERSION, "positions": self.data},
                              f, ensure_ascii=False)
                os.replace(tmp, self.path)
            print(f"💾 FEN-кэш сохранён: {len(self.data)} позиций")
        except Exception as e:
            print(f"⚠️ Ошибка сохранения: {e}")

    def get(self, fen):
        with self.lock:
            return self.data.get(fen)

    def put(self, fen, best_move):
        with self.lock:
            self.data[fen] = best_move


# ============================================================
# ENGINE POOL
# ============================================================
class EnginePool:
    def __init__(self, size=4):
        self.pool = queue.Queue()
        self.engines = []
        for _ in range(size):
            try:
                eng = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
                self.pool.put(eng)
                self.engines.append(eng)
            except Exception as e:
                print(f"⚠️ Движок не запустился: {e}")

    def get(self):
        try:
            return self.pool.get(timeout=5)
        except queue.Empty:
            return None

    def put(self, engine):
        if engine is not None:
            self.pool.put(engine)

    def close(self):
        for eng in self.engines:
            try:
                eng.quit()
            except Exception:
                pass


# ============================================================
# STOCKFISH
# ============================================================
def analyze_fen(fen):
    if not ENGINE_POOL:
        return None
    cached = FEN_CACHE.get(fen)
    if cached is not None:
        return cached
    for attempt in range(MAX_RETRIES):
        engine = ENGINE_POOL.get()
        if not engine:
            # §P3: sleep, чтобы не спинить CPU при пустом пуле
            time.sleep(0.5)
            continue
        try:
            board = chess.Board(fen)
            # FIX: time=30.0 внутри Limit вместо несуществующего timeout
            info = engine.analyse(
                board,
                chess.engine.Limit(depth=12, time=30.0),
            )
            if info.get("pv"):
                best = board.san(info["pv"][0])
                FEN_CACHE.put(fen, best)
                return best
        except chess.engine.EngineTerminatedError:
            print(f"⚠️ Движок умер при анализе FEN")
            time.sleep(1.0)
        except Exception as e:
            print(f"⚠️ Ошибка анализа: {e}")
            time.sleep(0.5)
        finally:
            ENGINE_POOL.put(engine)
    return None


# ============================================================
# CODEX
# ============================================================
def load_codex_rules():
    if not os.path.exists(CODEX_RULES_FILE):
        return []
    try:
        with open(CODEX_RULES_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("rules", [])
    except Exception:
        return []


# ============================================================
# BAD POSITIONS
# ============================================================
def get_bad_positions(conn, eco3, limit=5):
    positions = []
    cur = conn.cursor()
    cur.execute("""
        SELECT b.move_num, b.move_uci, b.loss_cp,
               b.fen_before, b.best_move_uci,
               g.white, g.black, g.pgn,
               datetime(g.end_time, 'unixepoch', '+3 hours') as dt,
               g.url
        FROM blunders b
        JOIN games g ON g.url = b.game_url
        WHERE substr(g.eco, 1, 3) = ?
          AND b.is_my_blunder = 1
          AND b.is_berserk = 0 AND b.is_instant = 0
          AND g.is_lag=0 AND g.is_cheater=0
        ORDER BY b.loss_cp DESC
        LIMIT ?
    """, (eco3, limit * 3))

    for move_num, move_uci, loss_cp, fen_db, best_uci_db, white, black, pgn, dt, url in cur.fetchall():
        if len(positions) >= limit:
            break
        try:
            fen_before = fen_db
            best_uci = best_uci_db

            if not fen_before and pgn:
                game = chess.pgn.read_game(io.StringIO(pgn))
                if not game:
                    continue
                player_is_white = (white or "").lower() == PLAYER.lower()
                target_ply = (move_num - 1) * 2 + (0 if player_is_white else 1)
                board = game.board()
                for ply_idx, node in enumerate(game.mainline()):
                    if ply_idx == target_ply:
                        fen_before = board.fen()
                        break
                    board.push(node.move)

            if not fen_before:
                continue

            best_move_san = None
            if best_uci:
                try:
                    b_obj = chess.Board(fen_before)
                    best_move_san = b_obj.san(chess.Move.from_uci(best_uci))
                except Exception:
                    best_move_san = best_uci

            if not best_move_san and ENGINE_POOL:
                best_move_san = analyze_fen(fen_before)

            positions.append({
                "fen": fen_before,
                "move_num": move_num,
                "loss_cp": loss_cp,
                "best_move": best_move_san,
                "url": url,
                "white": white,
                "black": black,
                "date": dt,
            })
        except Exception:
            continue
    return positions


# ============================================================
# OPENING TREE
# ============================================================
def build_opening_tree(conn, eco3, player, max_moves=10):
    tree_white = defaultdict(lambda: {"n": 0, "w": 0, "fen": ""})
    tree_black = defaultdict(lambda: {"n": 0, "w": 0, "fen": ""})
    cur = conn.cursor()
    cur.execute("""
        SELECT pgn, won, white FROM games
        WHERE substr(eco, 1, 3) = ? AND pgn IS NOT NULL AND pgn != ''
          AND is_lag=0 AND is_cheater=0
    """, (eco3,))
    for pgn, won, white in cur.fetchall():
        try:
            game = chess.pgn.read_game(io.StringIO(pgn))
            if not game:
                continue
            is_white = (white or "").lower() == player.lower()
            tree = tree_white if is_white else tree_black
            board = game.board()
            line = []
            for i, node in enumerate(game.mainline(), 1):
                if i > max_moves:
                    break
                san = board.san(node.move)
                line.append(san)
                key = " ".join(line)
                tree[key]["n"] += 1
                if won:
                    tree[key]["w"] += 1
                board.push(node.move)
                tree[key]["fen"] = board.fen()
        except Exception:
            continue
    return tree_white, tree_black


# ============================================================
# ANALYZE ONE OPENING (18 SQL-запросов)
# ============================================================
def analyze_opening(eco3, codex_rules=None, style_map=None):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    r = {"eco": eco3}

    try:
        # 1. База
        cur.execute("""
            SELECT COUNT(*), SUM(won),
                AVG(acpl_opening), AVG(acpl_middlegame), AVG(acpl_endgame), AVG(game_length),
                SUM(CASE WHEN won=1 THEN acpl_middlegame END),
                SUM(CASE WHEN won=1 THEN 1 ELSE 0 END),
                SUM(CASE WHEN won=0 THEN acpl_middlegame END),
                SUM(CASE WHEN won=0 THEN 1 ELSE 0 END),
                SUM(CASE WHEN reason='просрочка' THEN 1 ELSE 0 END),
                SUM(CASE WHEN max_eval_advantage >= 300 THEN 1 ELSE 0 END),
                SUM(CASE WHEN max_eval_advantage >= 300 AND won=0 AND draw=0 THEN 1 ELSE 0 END)
            FROM games
            WHERE substr(eco, 1, 3) = ? AND is_lag=0 AND is_cheater=0
        """, (eco3,))
        row = cur.fetchone()
        if not row or not row[0] or row[0] < 5:
            return None

        (total, wins, acpl_op, acpl_mid, acpl_end, avg_len,
         sum_won_mid, cnt_won, sum_loss_mid, cnt_loss,
         timeouts, sliv_total, sliv_lost) = row

        r.update({
            "total": total, "wins": wins or 0,
            "winrate": (wins or 0) / total * 100,
            "acpl_op": acpl_op or 0, "acpl_mid": acpl_mid or 0, "acpl_end": acpl_end or 0,
            "avg_len": avg_len or 0,
            "acpl_win_mid": sum_won_mid / cnt_won if cnt_won else 0,
            "acpl_loss_mid": sum_loss_mid / cnt_loss if cnt_loss else 0,
            "timeouts": timeouts or 0,
            "timeout_pct": (timeouts or 0) / total * 100,
            "sliv": (sliv_total or 0, sliv_lost or 0),
        })

        # 2. Eval после дебюта
        cur.execute("""
            SELECT ROUND(AVG(
                CASE WHEN white = ? THEN eval_after_opening ELSE -eval_after_opening END
            ), 1)
            FROM games
            WHERE substr(eco, 1, 3) = ? AND is_lag=0 AND is_cheater=0
        """, (PLAYER, eco3))
        r["eval_after_opening"] = cur.fetchone()[0] or 0

        # 3. Проблемные ходы
        cur.execute("""
            SELECT b.move_num, COUNT(*), ROUND(AVG(b.loss_cp))
            FROM blunders b
            JOIN games g ON g.url = b.game_url
            WHERE substr(g.eco, 1, 3) = ? AND b.is_my_blunder = 1
              AND b.is_berserk = 0 AND b.is_instant = 0
              AND g.is_lag=0 AND g.is_cheater=0
            GROUP BY b.move_num HAVING COUNT(*) >= 2
            ORDER BY COUNT(*) DESC LIMIT 5
        """, (eco3,))
        r["bad_moves"] = cur.fetchall()

        # 4. Паттерны
        cur.execute("""
            SELECT b.pattern_tag, COUNT(*),
                   ROUND(100.0*SUM(CASE WHEN g.won=1 THEN 1 ELSE 0 END)/COUNT(*), 1)
            FROM blunders b
            JOIN games g ON g.url = b.game_url
            WHERE substr(g.eco, 1, 3) = ? AND b.is_my_blunder = 1
              AND g.is_lag=0 AND g.is_cheater=0
            GROUP BY b.pattern_tag ORDER BY COUNT(*) DESC
        """, (eco3,))
        r["patterns"] = cur.fetchall()

        # 5. Окно уязвимости
        cur.execute("""
            SELECT
                CASE
                    WHEN b.move_num <= 10 THEN '1-10'
                    WHEN b.move_num <= 15 THEN '11-15'
                    WHEN b.move_num <= 20 THEN '16-20'
                    WHEN b.move_num <= 30 THEN '21-30'
                    ELSE '31+'
                END as window,
                COUNT(*)
            FROM blunders b
            JOIN games g ON g.url = b.game_url
            WHERE substr(g.eco, 1, 3) = ? AND b.is_my_blunder = 1
              AND b.is_berserk = 0 AND b.is_instant = 0
              AND g.is_lag=0 AND g.is_cheater=0
            GROUP BY window
        """, (eco3,))
        r["vulnerability_window"] = cur.fetchall()

        # 6. Линия-убийца
        cur.execute("""
            SELECT g.opening_line, COUNT(*)
            FROM blunders b
            JOIN games g ON g.url = b.game_url
            WHERE substr(g.eco, 1, 3) = ? AND b.is_my_blunder = 1
              AND g.is_lag=0 AND g.is_cheater=0 AND g.opening_line != ''
            GROUP BY g.opening_line ORDER BY COUNT(*) DESC LIMIT 1
        """, (eco3,))
        r["killer_line"] = cur.fetchone()

        # 7. Линии по сливу +3.0
        cur.execute("""
            SELECT opening_line, COUNT(*),
                   SUM(CASE WHEN won=0 AND draw=0 THEN 1 ELSE 0 END)
            FROM games
            WHERE substr(eco, 1, 3) = ? AND max_eval_advantage >= 300
                AND is_lag=0 AND is_cheater=0 AND opening_line != ''
            GROUP BY opening_line HAVING COUNT(*) >= 2
            ORDER BY (CAST(SUM(CASE WHEN won=0 AND draw=0 THEN 1 ELSE 0 END) AS REAL) / COUNT(*)) DESC
            LIMIT 3
        """, (eco3,))
        r["sliv_lines"] = cur.fetchall()

        # 8. Точка невозврата
        cur.execute("""
            SELECT b.move_num, COUNT(*),
                   ROUND(100.0*SUM(CASE WHEN g.won=0 THEN 1 ELSE 0 END)/COUNT(*), 1)
            FROM blunders b
            JOIN games g ON g.url = b.game_url
            WHERE substr(g.eco, 1, 3) = ? AND b.is_my_blunder = 1
              AND b.is_berserk = 0 AND b.is_instant = 0
              AND g.is_lag=0 AND g.is_cheater=0
            GROUP BY b.move_num HAVING COUNT(*) >= 2
            ORDER BY 3 DESC LIMIT 3
        """, (eco3,))
        r["point_of_no_return"] = cur.fetchall()

        # 9. По цвету
        cur.execute("""
            SELECT
                CASE WHEN white = ? THEN 'Белые' ELSE 'Чёрные' END,
                COUNT(*), SUM(won), ROUND(AVG(acpl_middlegame))
            FROM games
            WHERE substr(eco, 1, 3) = ? AND is_lag=0 AND is_cheater=0
            GROUP BY 1
        """, (PLAYER, eco3))
        r["by_color"] = cur.fetchall()

        # 10. По рейтингу
        cur.execute("""
            SELECT
                CASE
                    WHEN opp_rating < 2400 THEN '<2400'
                    WHEN opp_rating < 2500 THEN '2400-2500'
                    WHEN opp_rating < 2600 THEN '2500-2600'
                    WHEN opp_rating < 2700 THEN '2600-2700'
                    ELSE '2700+'
                END as rng,
                COUNT(*), SUM(won), ROUND(AVG(acpl_middlegame))
            FROM games
            WHERE substr(eco, 1, 3) = ? AND is_lag=0 AND is_cheater=0
            GROUP BY rng
            ORDER BY CASE rng WHEN '<2400' THEN 1 WHEN '2400-2500' THEN 2
                              WHEN '2500-2600' THEN 3 WHEN '2600-2700' THEN 4 ELSE 5 END
        """, (eco3,))
        r["by_rating"] = cur.fetchall()

        # 11. Доминирование
        cur.execute("""
            SELECT white, eval_history FROM games
            WHERE substr(eco, 1, 3) = ? AND eval_history IS NOT NULL AND eval_history != '[]'
              AND is_lag=0 AND is_cheater=0
        """, (eco3,))
        dom = {"Белые": {"n": 0, "agg_sum": 0}, "Чёрные": {"n": 0, "agg_sum": 0}}
        for white, raw in cur.fetchall():
            try:
                hist = json.loads(raw)
                if not hist:
                    continue
                agg = 0
                prev = None
                for move, ev in hist:
                    if prev is not None and ev - prev >= 50:
                        agg += 1
                    prev = ev
                color = "Белые" if (white or "").lower() == PLAYER.lower() else "Чёрные"
                dom[color]["n"] += 1
                dom[color]["agg_sum"] += agg
            except Exception:
                continue
        r["dominance"] = {color: (d["agg_sum"] / d["n"] if d["n"] else 0)
                          for color, d in dom.items()}

        # 12. Weekly
        cur.execute("""
            SELECT strftime('%Y-%W', datetime(end_time, 'unixepoch')), COUNT(*), SUM(won)
            FROM games
            WHERE substr(eco, 1, 3) = ? AND is_lag=0 AND is_cheater=0
            GROUP BY 1 ORDER BY 1 DESC LIMIT 6
        """, (eco3,))
        r["weekly"] = list(reversed(cur.fetchall()))

        # 13. Лучшая партия
        cur.execute("""
            SELECT url, opp_rating,
                   ROUND(opp_rating + ((CASE WHEN won=1 THEN 1.0 WHEN draw=1 THEN 0.5 ELSE 0.0 END) - 0.5) * 800)
            FROM games WHERE substr(eco, 1, 3) = ? AND is_lag=0 AND is_cheater=0
            ORDER BY 3 DESC LIMIT 1
        """, (eco3,))
        r["peak_best"] = cur.fetchone()

        # 14. Худшая партия
        if total >= 3:
            cur.execute("""
                SELECT url, opp_rating,
                       ROUND(opp_rating + ((CASE WHEN won=1 THEN 1.0 WHEN draw=1 THEN 0.5 ELSE 0.0 END) - 0.5) * 800)
                FROM games WHERE substr(eco, 1, 3) = ? AND is_lag=0 AND is_cheater=0
                ORDER BY 3 ASC LIMIT 1
            """, (eco3,))
            r["peak_worst"] = cur.fetchone()
        else:
            r["peak_worst"] = None

        # 15. StdDev
        cur.execute("SELECT acpl FROM games WHERE substr(eco, 1, 3) = ? AND acpl > 0", (eco3,))
        vals = sorted([v[0] for v in cur.fetchall()])
        if len(vals) >= 10:
            n = len(vals)
            p5 = vals[int(n * 0.05)]
            p95 = vals[int(n * 0.95)]
            filtered = [v for v in vals if p5 <= v <= p95]
            r["stddev"] = statistics.stdev(filtered) if len(filtered) >= 10 else 0
        else:
            r["stddev"] = 0

        # 16. Деревья
        r["tree_white"], r["tree_black"] = build_opening_tree(conn, eco3, PLAYER)

        # 17. Проблемные позиции
        r["bad_positions"] = get_bad_positions(conn, eco3, limit=5)

        # 18. Совет Кодекса
        r["codex_advice"] = []
        if codex_rules and r["patterns"]:
            pattern_to_rule = {
                "fork_heavy": "chaos_high",
                "lost_piece": "blunder",
                "positional": "middlegame_leak",
                "lost_queen": "timeout_high",
                "missed_mate": "endgame_weak",
            }
            top_pattern = r["patterns"][0][0]
            target_id = pattern_to_rule.get(top_pattern)
            for rule in codex_rules:
                if rule.get("id") == target_id:
                    r["codex_advice"].append(rule)
                    break

        # 19. По стилю
        r["by_style"] = None
        if style_map:
            cur.execute("""
                SELECT opp_username, won FROM games
                WHERE substr(eco, 1, 3) = ? AND is_lag=0 AND is_cheater=0
                  AND opp_username IS NOT NULL
            """, (eco3,))
            style_stats = defaultdict(lambda: {"n": 0, "w": 0})
            for opp, won in cur.fetchall():
                style = style_map.get(opp, "unknown")
                style_stats[style]["n"] += 1
                if won:
                    style_stats[style]["w"] += 1
            r["by_style"] = [
                (style, d) for style, d in style_stats.items()
                if d["n"] >= 3 and not (style == "unknown" and d["n"] / total > 0.2)
            ]

        return r
    except Exception as e:
        print(f"❌ Ошибка при анализе {eco3}: {e}")
        return None
    finally:
        conn.close()