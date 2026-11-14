# ============================================================
# analysis/cache.py — работа с кэшем Stockfish-анализа (v25.1)
# FIX: Итерация по ключам словаря, чтобы не проверять _schema_version.
# ============================================================
import os
import json


# Версия схемы кэша. Меняется при поломке формата (не при фиксах).
CACHE_SCHEMA_VERSION = 3

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
    "flag_result", "my_clock_at_timeout", "opp_clock_at_timeout",
)

BLUNDER_FIELDS = (
    "is_my_blunder", "pattern_tag", "eval_swing",
    "next_move_time", "is_next_move_blunder", "missed_threat",
)


def game_cache_ok(r: dict) -> bool:
    """
    Проверка одной записи.
    """
    if not isinstance(r, dict):
        return False

    # 1. Все поля на месте
    if not all(f in r for f in V10_FIELDS):
        return False

    # 2. acpl > 0 (фикс §21)
    acpl = r.get("acpl", 0)
    try:
        if float(acpl) <= 0:
            return False
    except (TypeError, ValueError):
        return False

    # 3. blunders корректны
    blunders = r.get("blunders", [])
    if not isinstance(blunders, list):
        return False
    for b in blunders:
        if not isinstance(b, dict):
            return False
        for bf in BLUNDER_FIELDS:
            if bf not in b:
                return False

    return True


def cache_needs_recalc(cache: dict) -> bool:
    """
    Проверяет, нужен ли пересчёт всего кэша.
    """
    if not cache:
        return True

    # 2. Версия схемы (если поле появится в будущем)
    if "_schema_version" in cache:
        try:
            if int(cache["_schema_version"]) != CACHE_SCHEMA_VERSION:
                return True
        except (TypeError, ValueError):
            return True

    # 3. Проверка полей в первых 5 записях
    sample = []
    for key, r in cache.items():
        if key.startswith("_"):
            continue
        if len(sample) >= 5:
            break
        sample.append(r)
        for f in V10_FIELDS:
            if f not in r:
                return True
        for b in r.get("blunders", []):
            for bf in BLUNDER_FIELDS:
                if bf not in b:
                    return True

    # 4. Хотя бы в одной из sample acpl > 0 (иначе — кэш сломан)
    if sample:
        has_positive = False
        for r in sample:
            try:
                if float(r.get("acpl", 0)) > 0:
                    has_positive = True
                    break
            except (TypeError, ValueError):
                continue
        if not has_positive:
            print(f"   ?? В первых {len(sample)} записях acpl = 0. Кэш битый — пересчёт.")
            return True

    # 5. Патч v18.4: next_move_time
    total_blunders = 0
    filled_nmt = 0
    for key, r in cache.items():
        if key.startswith("_"):
            continue
        for b in r.get("blunders", []):
            if not b.get("is_my_blunder"):
                continue
            total_blunders += 1
            if b.get("next_move_time") is not None:
                filled_nmt += 1
                if filled_nmt >= 20:
                    return False

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
        
        # ФИКС: Добавляем маркер версии, если его нет
        if "_schema_version" not in data:
            data["_schema_version"] = CACHE_SCHEMA_VERSION
            print(f"🔧 Кэш обновлен до версии {CACHE_SCHEMA_VERSION}")
            
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
    """
    Атомарная запись: сначала .tmp, потом os.replace.
    §17: компактный JSON (без indent) — экономия 50% размера.
    """
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)