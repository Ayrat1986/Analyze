# ============================================================
# analysis/dashboard_aggression.py — Агрессия (v25.0)
# Фикс §22: кэш валидируется по mtime(chess.db) + TTL 24ч.
# ============================================================
import os
import json
import time
from collections import defaultdict

from analysis.common import (
    _conn, PLAYER, RATING_BUCKET_LABELS, rating_bucket, DB_FILE,
)
from _chess_utils import parse_time_spent

CACHE_FILE = str(os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "agg_cache.json"
))
CACHE_TTL_SEC = 86400  # 24 часа


def _cache_is_fresh() -> bool:
    """
    v25.0 (§22): кэш свежий, только если:
      1) TTL 24ч не истёк
      2) файл кэша новее, чем chess.db
    Если chess.db была обновлена после кэша — пересчёт.
    """
    if not os.path.exists(CACHE_FILE):
        return False
    cache_mtime = os.path.getmtime(CACHE_FILE)
    if (time.time() - cache_mtime) > CACHE_TTL_SEC:
        return False
    if os.path.exists(DB_FILE):
        db_mtime = os.path.getmtime(DB_FILE)
        if cache_mtime < db_mtime:
            return False
    return True


def get_all_aggression_stats():
    if _cache_is_fresh():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"  ⚠️ agg_cache.json битый ({e}), пересчёт")

    try:
        import chess
        import chess.pgn
        import io
    except ImportError:
        print("  ⚠️ python-chess не установлен — агрессия пропущена")
        return {}

    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT white, pgn, won, draw, clocks, eco, opp_rating, opening
        FROM games
        WHERE is_lag=0 AND is_cheater=0
          AND pgn IS NOT NULL AND pgn != ''
    """)
    rows = cur.fetchall()
    conn.close()

    by_rating = {label: {"n": 0, "w": 0, "d": 0, "agg": 0, "moves": 0,
                         "time_sum": 0, "time_cnt": 0}
                 for label in RATING_BUCKET_LABELS}
    by_opening = defaultdict(lambda: {"n": 0, "w": 0, "d": 0, "agg": 0, "moves": 0,
                                      "time_sum": 0, "time_cnt": 0, "opening": ""})
    by_phase = {
        "opening":    {"n": 0, "w": 0, "d": 0, "agg": 0, "moves": 0, "time_sum": 0, "time_cnt": 0},
        "middlegame": {"n": 0, "w": 0, "d": 0, "agg": 0, "moves": 0, "time_sum": 0, "time_cnt": 0},
        "endgame":    {"n": 0, "w": 0, "d": 0, "agg": 0, "moves": 0, "time_sum": 0, "time_cnt": 0},
    }
    by_moves = {k: {"n": 0, "w": 0, "d": 0, "agg": 0, "moves": 0, "time_sum": 0, "time_cnt": 0}
                for k in ["11-15", "16-20", "21-25", "26-30"]}

    for white, pgn, won, draw, clocks_raw, eco, opp_rating, opening_str in rows:
        try:
            game = chess.pgn.read_game(io.StringIO(pgn))
            if not game:
                continue
        except Exception:
            continue

        player_is_white = (white or "").lower() == PLAYER.lower()
        times = []
        if clocks_raw:
            try:
                clocks = json.loads(clocks_raw)
                if clocks:
                    times = parse_time_spent(clocks, player_is_white)
            except Exception:
                pass

        r_bucket = rating_bucket(opp_rating)
        eco_key = eco or "Unknown"
        board = game.board()
        our_move_idx = 0
        reached_mid = False
        reached_end = False
        reached_moves = set()

        for node in game.mainline():
            is_my_move = (board.turn and player_is_white) or (not board.turn and not player_is_white)
            move_num = board.fullmove_number

            if is_my_move:
                if move_num <= 10:
                    phase = "opening"
                elif move_num <= 30:
                    phase = "middlegame"
                    reached_mid = True
                else:
                    phase = "endgame"
                    reached_end = True

                phase_key = None
                if 11 <= move_num <= 15:
                    phase_key = "11-15"
                elif 16 <= move_num <= 20:
                    phase_key = "16-20"
                elif 21 <= move_num <= 25:
                    phase_key = "21-25"
                elif 26 <= move_num <= 30:
                    phase_key = "26-30"
                if phase_key:
                    reached_moves.add(phase_key)

                is_capture = board.is_capture(node.move)
                board.push(node.move)
                is_check = board.is_check()
                agg_val = (1 if is_capture else 0) + (1 if is_check else 0)
                t_val = times[our_move_idx] if our_move_idx < len(times) else None

                for d in [by_phase[phase],
                          by_rating.get(r_bucket, {}),
                          by_opening[eco_key]]:
                    if d:
                        d["moves"] += 1
                        d["agg"] += agg_val
                        if t_val is not None:
                            d["time_sum"] += t_val
                            d["time_cnt"] += 1
                if phase_key and phase_key in by_moves:
                    d = by_moves[phase_key]
                    d["moves"] += 1
                    d["agg"] += agg_val
                    if t_val is not None:
                        d["time_sum"] += t_val
                        d["time_cnt"] += 1

                if eco_key in by_opening:
                    by_opening[eco_key]["opening"] = opening_str or "Unknown"
                our_move_idx += 1
            else:
                board.push(node.move)

        if r_bucket in by_rating:
            by_rating[r_bucket]["n"] += 1
            if won:
                by_rating[r_bucket]["w"] += 1
            if draw:
                by_rating[r_bucket]["d"] += 1

        by_opening[eco_key]["n"] += 1
        if won:
            by_opening[eco_key]["w"] += 1
        if draw:
            by_opening[eco_key]["d"] += 1

        by_phase["opening"]["n"] += 1
        if won:
            by_phase["opening"]["w"] += 1
        if draw:
            by_phase["opening"]["d"] += 1
        if reached_mid:
            by_phase["middlegame"]["n"] += 1
            if won:
                by_phase["middlegame"]["w"] += 1
            if draw:
                by_phase["middlegame"]["d"] += 1
        if reached_end:
            by_phase["endgame"]["n"] += 1
            if won:
                by_phase["endgame"]["w"] += 1
            if draw:
                by_phase["endgame"]["d"] += 1

        for pk in reached_moves:
            by_moves[pk]["n"] += 1
            if won:
                by_moves[pk]["w"] += 1
            if draw:
                by_moves[pk]["d"] += 1

    result = {
        "by_rating": by_rating,
        "by_opening": dict(by_opening),
        "by_phase": by_phase,
        "by_moves": by_moves,
        "_cached_at": time.time(),
    }
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return result


_STATS_CACHE = None


def _get_stats():
    global _STATS_CACHE
    if _STATS_CACHE is None:
        _STATS_CACHE = get_all_aggression_stats()
    return _STATS_CACHE


def _format_agg_data(data, key_name="label"):
    res = []
    for k, d in data.items():
        if d["n"] < 5:
            continue
        item = {
            key_name: k,
            "games": d["n"],
            "win_rate": round((d["w"] + 0.5 * d["d"]) / d["n"] * 100, 1),
            "aggression": round((d["agg"] / d["moves"] * 100) if d["moves"] else 0, 1),
            "avg_time": round((d["time_sum"] / d["time_cnt"]) if d["time_cnt"] else 0, 2),
        }
        if "opening" in d:
            item["opening"] = d["opening"][:30]
        res.append(item)
    return res


def aggression_by_rating():
    return _format_agg_data(_get_stats()["by_rating"], "rating")


def aggression_by_opening():
    stats = _get_stats()
    sorted_eco = sorted(stats["by_opening"].items(),
                        key=lambda x: x[1]["n"], reverse=True)[:15]
    return _format_agg_data(dict(sorted_eco), "eco")


def aggression_by_phase():
    res = []
    labels = {"opening": "Дебют (1-10)",
              "middlegame": "Миттельшпиль (11-30)",
              "endgame": "Эндшпиль (31+)"}
    for k, label in labels.items():
        d = _get_stats()["by_phase"][k]
        if d["n"] < 5:
            continue
        res.append({
            "phase": label,
            "games": d["n"],
            "win_rate": round((d["w"] + 0.5 * d["d"]) / d["n"] * 100, 1),
            "aggression": round((d["agg"] / d["moves"] * 100) if d["moves"] else 0, 1),
            "avg_time": round((d["time_sum"] / d["time_cnt"]) if d["time_cnt"] else 0, 2),
        })
    return res


def aggression_by_moves():
    res = []
    for label in ["11-15", "16-20", "21-25", "26-30"]:
        d = _get_stats()["by_moves"][label]
        if d["n"] < 5:
            continue
        res.append({
            "range": label,
            "games": d["n"],
            "win_rate": round((d["w"] + 0.5 * d["d"]) / d["n"] * 100, 1),
            "aggression": round((d["agg"] / d["moves"] * 100) if d["moves"] else 0, 1),
            "avg_time": round((d["time_sum"] / d["time_cnt"]) if d["time_cnt"] else 0, 2),
        })
    return res