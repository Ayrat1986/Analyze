# ============================================================
# analysis/cache.py — работа с кэшем Stockfish-анализа
# ============================================================
import os
import json


# Все поля, которые обязаны быть в каждой записи кэша
V10_FIELDS = (
    "acpl_opponent_normal", "acpl_opponent_total", "accuracy_opponent", "opp_blunders_total",
    "eval_final", "max_eval_advantage", "min_eval_advantage",
    "berserk_move_enter", "berserk_moves_count",
    "is_true_berserk", "opening", "eco", "time_thresholds_version",
    "acpl_opening", "acpl_middlegame", "acpl_endgame",
    "timeout_at_move", "timeout_with_clock", "eval_after_opening",
    "momentum_after_blunder", "moves_in_winning_position", "opening_line",
    "pgn", "clocks", "eval_history", "critical_moments", "time_control",
    # Sprint C
    "flag_result", "my_clock_at_timeout", "opp_clock_at_timeout",
)


def game_cache_ok(r: dict) -> bool:
    """Проверка одной записи: все поля на месте?"""
    if not all(f in r for f in V10_FIELDS):
        return False
    for b in r.get("blunders", []):
        for bf in ("is_my_blunder", "pattern_tag", "eval_swing",
                   "next_move_time", "is_next_move_blunder", "missed_threat"):
            if bf not in b:
                return False
    return True


def cache_needs_recalc(cache: dict) -> bool:
    """
    Проверяет, нужен ли пересчёт всего кэша.

    1. Если кэш пуст > пересчёт.
    2. Если хоть одно поле V10_FIELDS отсутствует в первых 5 записях > пересчёт.
    3. ПАТЧ v18.4: если в кэше 50+ «моих» зевков, но next_move_time НИ У ОДНОГО
       не заполнен — это кэш v18.2 (сломанная формула). Пересчёт.
    """
    if not cache:
        return True

    # 1. Стандартная проверка наличия полей
    for i, r in enumerate(cache.values()):
        if i >= 5:
            break
        for f in V10_FIELDS:
            if f not in r:
                return True
        for b in r.get("blunders", []):
            for bf in ("is_my_blunder", "pattern_tag", "eval_swing",
                       "next_move_time", "is_next_move_blunder", "missed_threat"):
                if bf not in b:
                    return True

    # 2. ПАТЧ: проверяем, что next_move_time РЕАЛЬНО заполнен
    total_blunders = 0
    filled_nmt = 0
    for r in cache.values():
        for b in r.get("blunders", []):
            if not b.get("is_my_blunder"):
                continue
            total_blunders += 1
            if b.get("next_move_time") is not None:
                filled_nmt += 1
                if filled_nmt >= 20:
                    return False  # нашли примеры — кэш новый

    if total_blunders >= 50 and filled_nmt == 0:
        print(f"   ?? В кэше {total_blunders} зевков, но next_move_time не заполнен ни у одного.")
        print(f"      Это старый кэш v18.2 (сломанная формула) — нужен пересчёт.")
        return True

    return False


def load_cache(path: str) -> dict:
    """Читает JSON-кэш. При ошибке — пустой dict."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            print("?? Кэш повреждён — начинаем с нуля")
            return {}
        return data
    except json.JSONDecodeError as e:
        print(f"?? Кэш повреждён (JSON): {e}")
        tmp = path + ".tmp"
        if os.path.exists(tmp):
            try:
                with open(tmp, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}
    except Exception as e:
        print(f"?? Кэш не загружен: {e}")
        return {}


def save_cache(path: str, cache: dict) -> None:
    """Атомарная запись: сначала .tmp, потом os.replace."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)