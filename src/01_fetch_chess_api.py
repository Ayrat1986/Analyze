# ============================================================
# 01_fetch_chess_api.py
# ============================================================
from curl_cffi import requests
import time
import os
import json
from datetime import datetime, timezone, timedelta
import _common

CACHE_FILE = str(_common.BASE_DIR / "data" / "chess_api_cache.json")
PLAYER = _common.CONFIG.get("player", "Ayrat_1986")
EMAIL = _common.CONFIG.get("email", "")

# Настройки фильтрации
TIME_CLASS = "bullet"
MAX_BULLET_BASE_TIME = 120
DAYS_TO_FETCH = 95
CACHE_ROTATION_DAYS = 120

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}


# ---------- КЭШ ----------
def load_cache() -> dict:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Кэш повреждён, начинаем с нуля: {e}")
            return {}
    return {}


def save_cache(cache: dict) -> None:
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    tmp = CACHE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    os.replace(tmp, CACHE_FILE)


# ---------- HTTP ----------
def get_api_data(url: str, cache: dict, retries: int = 3, force: bool = False):
    """Возвращает JSON или None. Уважает кэш (если не force)."""
    if not force and url in cache:
        return cache[url]

    for attempt in range(retries):
        try:
            response = requests.get(
                url, headers=HEADERS, impersonate="safari184",
                verify=False, timeout=30,
            )
            if response.status_code == 200:
                data = response.json()
                cache[url] = data
                return data
            elif response.status_code == 429:
                print("  ⚠️ Лимит запросов (429). Пауза 10 сек...")
                time.sleep(10)
                continue
            elif response.status_code == 404:
                return None
            else:
                time.sleep(2)
        except Exception as e:
            print(f"  ⚠️ Ошибка сети: {e}")
            time.sleep(2)
    return None


# ---------- FETCH ----------
def fetch_all_games(player: str, cache: dict) -> list:
    """Качает свежие месяцы + фильтрует bullet <= 120 сек. Возвращает games."""
    print(f"Загрузка архивов для {player}...")
    archives_url = f"https://api.chess.com/pub/player/{player}/games/archives"
    data = get_api_data(archives_url, cache, force=True)
    if not data or "archives" not in data:
        print("❌ Не удалось получить список архивов.")
        return []

    archives = data["archives"]
    print(f"✅ Найдено месяцев в архиве: {len(archives)}")

    now_utc = datetime.now(timezone.utc)
    current_month_url = f"https://api.chess.com/pub/player/{player}/games/{now_utc.year}/{now_utc.month:02d}"
    prev_month_date = now_utc.replace(day=1) - timedelta(days=1)
    prev_month_url = f"https://api.chess.com/pub/player/{player}/games/{prev_month_date.year}/{prev_month_date.month:02d}"

    # ВСЕГДА качаем текущий и предыдущий месяц первыми
    fetch_urls = []
    seen_urls = set()
    for u in (current_month_url, prev_month_url):
        if u not in seen_urls:
            fetch_urls.append(u)
            seen_urls.add(u)
    # Остальные архивы — от старых к новым
    for u in reversed(archives):
        if u not in seen_urls:
            fetch_urls.append(u)
            seen_urls.add(u)

    cutoff_90_utc = int((now_utc - timedelta(days=91)).timestamp())
    all_games, existing_urls = [], set()

    for url in fetch_urls:
        parts = url.split("/")
        if len(parts) < 2:
            continue
        month_str = f"{parts[-2]}/{parts[-1]}"

        is_recent = (url == current_month_url or url == prev_month_url)
        try:
            year, month = int(parts[-2]), int(parts[-1])
            archive_date = datetime(year, month, 1, tzinfo=timezone.utc)
            if archive_date < now_utc - timedelta(days=100) and not is_recent:
                continue  # слишком старые — не качаем (не break!)
        except ValueError:
            pass

        print(f"  Загрузка месяца: {month_str} {'(force)' if is_recent else ''} ...")
        month_data = get_api_data(url, cache, force=is_recent)
        if not month_data:
            print(f"    ⚠️ пустой ответ")
            continue

        games_in_month = month_data.get("games", [])
        if is_recent and not games_in_month:
            print(f"    ⚠️ {month_str}: 0 партий в ответе (возможно, API лагает)")

        for g in games_in_month:
            g_url = g.get("url")
            if g_url in existing_urls:
                continue
            if g.get("end_time", 0) < cutoff_90_utc:
                continue
            if g.get("time_class") != TIME_CLASS:
                continue
            tc = g.get("time_control", "")
            if tc:
                try:
                    if int(tc.split("+")[0]) > MAX_BULLET_BASE_TIME:
                        continue
                except ValueError:
                    pass
            all_games.append(g)
            existing_urls.add(g_url)

    print(f"✅ Всего подходящих партий (bullet): {len(all_games)}")
    return all_games


# ---------- HELPER ДЛЯ DOMAIN-СКРИПТОВ ----------
def get_games_from_cache(
    player: str = PLAYER,
    days: int = DAYS_TO_FETCH,
    time_class: str = TIME_CLASS,
    max_base: int = MAX_BULLET_BASE_TIME,
    require_pgn: bool = True,
) -> list:
    """
    Читает chess_api_cache.json, возвращает отфильтрованные games.
    Заменяет download_games() из старого 02_fetch_time.py.
    Никаких HTTP-запросов — только чтение кэша.
    """
    if not os.path.exists(CACHE_FILE):
        print(f"⚠️ Нет {CACHE_FILE}. Сначала запусти 01_fetch_chess_api.py.")
        return []

    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        cache = json.load(f)

    archives_url = f"https://api.chess.com/pub/player/{player}/games/archives"
    if archives_url not in cache:
        print("⚠️ В кэше нет списка архивов. Запусти 01_fetch_chess_api.py.")
        return []

    archives = cache[archives_url].get("archives", [])
    
    # Добавляем текущий и предыдущий месяц (они могут быть не в archives)
    now_utc = datetime.now(timezone.utc)
    current_month_url = f"https://api.chess.com/pub/player/{player}/games/{now_utc.year}/{now_utc.month:02d}"
    prev_month_date = now_utc.replace(day=1) - timedelta(days=1)
    prev_month_url = f"https://api.chess.com/pub/player/{player}/games/{prev_month_date.year}/{prev_month_date.month:02d}"
    
    all_urls = [current_month_url, prev_month_url] + list(reversed(archives))
    
    cutoff_ts = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())

    games, seen = [], set()
    for archive_url in all_urls:
        if archive_url not in cache:
            continue
        for g in cache[archive_url].get("games", []):
            g_url = g.get("url")
            if g_url in seen:
                continue
            if g.get("end_time", 0) < cutoff_ts:
                continue
            if g.get("time_class") != time_class:
                continue
            tc = g.get("time_control", "")
            if tc:
                try:
                    if int(tc.split("+")[0]) > max_base:
                        continue
                except ValueError:
                    pass
            if require_pgn and not g.get("pgn"):
                continue
            games.append(g)
            seen.add(g_url)

    return games


# ============================================================
# TEMP: переедет в 10_psych_rating.py на фазе 9.
# ============================================================
def get_peak_for_interval(games, player, days_ago_min, days_ago_max):
    now_utc = datetime.now(timezone.utc)
    cutoff_newest = int((now_utc - timedelta(days=days_ago_min)).timestamp())
    cutoff_oldest = int((now_utc - timedelta(days=days_ago_max)).timestamp())
    interval = [g for g in games if cutoff_oldest < g.get("end_time", 0) <= cutoff_newest]
    if not interval:
        return 0, 0

    max_rating = 0
    opp_ratings = []
    for g in interval:
        white, black = g.get("white", {}), g.get("black", {})
        is_white = white.get("username", "").lower() == player.lower()
        my_rating = white.get("rating", 0) if is_white else black.get("rating", 0)
        opp_rating = black.get("rating", 0) if is_white else white.get("rating", 0)
        if my_rating > max_rating:
            max_rating = my_rating
        if opp_rating > 0:
            opp_ratings.append(opp_rating)

    avg_opp = sum(opp_ratings) / len(opp_ratings) if opp_ratings else 0
    return max_rating, avg_opp


def calculate_stats(games, player, peak_for_anchor, avg_opp_for_anchor=None):
    """
    Считает статистику для окна: win_rate, avg_opp, perf_rating,
    ЯКОРЬ (anchor_min, anchor_peak, anchor_formula, anchor_final).
    """
    total = len(games)
    if total == 0:
        return None

    wins, losses, draws = 0, 0, 0
    ratings, win_ratings, loss_ratings = [], [], []
    my_ratings_with_time = []

    for g in games:
        white, black = g.get("white", {}), g.get("black", {})
        is_white = white.get("username", "").lower() == player.lower()

        my_rating = white.get("rating", 0) if is_white else black.get("rating", 0)
        if my_rating > 0:
            my_ratings_with_time.append((g.get("end_time", 0), my_rating))

        opp_rating = black.get("rating", 0) if is_white else white.get("rating", 0)
        if opp_rating > 0:
            ratings.append(opp_rating)

        my_result = white.get("result") if is_white else black.get("result")
        if my_result == "win":
            wins += 1
            if opp_rating > 0:
                win_ratings.append(opp_rating)
        elif my_result in ["checkmated", "timeout", "resigned", "abandoned", "lose"]:
            losses += 1
            if opp_rating > 0:
                loss_ratings.append(opp_rating)
        else:
            draws += 1

    actual_avg_opp = sum(ratings) / len(ratings) if ratings else 0
    score_points = wins + (0.5 * draws)
    perf_rating = actual_avg_opp + ((score_points - (total * 0.5)) * 800 / total) if total > 0 else 0

    my_sorted = sorted(my_ratings_with_time, key=lambda x: x[0])
    my_vals = [r for _, r in my_sorted]
    avg_my = sum(my_vals) / len(my_vals) if my_vals else 0
    first_my = my_sorted[0][1] if my_sorted else 0
    last_my = my_sorted[-1][1] if my_sorted else 0
    gap = avg_my - actual_avg_opp if (avg_my and actual_avg_opp) else 0

    # --- ЯКОРЬ ---
    min_window = min(my_vals) if my_vals else 0
    anchor_peak = peak_for_anchor - 150
    anchor_formula = actual_avg_opp * 0.98 if actual_avg_opp > 0 else 0
    anchor_final = (min_window + anchor_peak + anchor_formula) / 3

    return {
        "total": total, "wins": wins, "losses": losses, "draws": draws,
        "win_rate": (wins / total) * 100,
        "loss_rate": (losses / total) * 100,
        "draw_rate": (draws / total) * 100,
        "avg_opp": actual_avg_opp,
        "avg_win": sum(win_ratings) / len(win_ratings) if win_ratings else 0,
        "avg_loss": sum(loss_ratings) / len(loss_ratings) if loss_ratings else 0,
        "max_rating": max(my_vals) if my_vals else 0,
        "perf_rating": perf_rating,
        "avg_my_rating": avg_my,
        "first_my_rating": first_my,
        "last_my_rating": last_my,
        "gap": gap,
        "anchor_min": min_window,
        "anchor_peak": anchor_peak,
        "anchor_formula": anchor_formula,
        "anchor_final": anchor_final,
        "peak_in_window": peak_for_anchor,
    }


# ---------- РОТАЦИЯ ----------
def rotate_cache(cache: dict, cutoff_days: int = CACHE_ROTATION_DAYS) -> dict:
    """Удаляет месячные URL, где нет ни одной игры за последние cutoff_days."""
    cutoff = int((datetime.now(timezone.utc) - timedelta(days=cutoff_days)).timestamp())
    rotated = {}
    for url, data in cache.items():
        if "archives" in url:
            rotated[url] = data
        elif isinstance(data, dict) and data.get("games"):
            if any(g.get("end_time", 0) >= cutoff for g in data["games"]):
                rotated[url] = data
    return rotated


# ---------- MAIN ----------
def main():
    print("=" * 60)
    print(" FETCH CHESS.COM API → data/chess_api_cache.json")
    print("=" * 60)

    if not PLAYER:
        print("⚠️ В config.json не указан 'player' — прерываю.")
        return

    cache = load_cache()
    print(f"📂 В кэше уже: {len(cache)} URL")

    all_games = fetch_all_games(PLAYER, cache)
    if not all_games:
        print("❌ Не удалось загрузить партии.")
        return

    print(f"🧹 Ротация кэша (> {CACHE_ROTATION_DAYS} дней)...")
    old_size = len(cache)
    cache = rotate_cache(cache)
    save_cache(cache)
    print(f"🧹 Кэш: {old_size} → {len(cache)} URL")

    print(f"\n✅ Готово. Кэш: {CACHE_FILE}")


if __name__ == "__main__":
    main()