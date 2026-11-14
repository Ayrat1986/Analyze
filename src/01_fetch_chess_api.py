# ============================================================
# 01_fetch_chess_api.py — v25.5 (Fix: Sync Cache vs SQLite DB)
#
# ЧТО ИСПРАВЛЕНО:
#   - Сверка партий теперь идет не только по JSON-кэшу, но и напрямую
#     с базой данных SQLite (chess.db). Если партии скачались в JSON,
#     но еще не проанализированы в БД — скрипт это увидит и запустит анализ!
#   - Вывод времени самой свежей партии теперь дублируется в локальном
#     времени (МСК/Казань, UTC+3), чтобы не путаться с UTC.
#   - Надежный автозапуск 02_analyze_stockfish.py через subprocess.
# ============================================================
from curl_cffi import requests
import time
import os
import sys
import json
import sqlite3
import subprocess
import traceback
from datetime import datetime, timezone, timedelta
import _common

CACHE_FILE = str(_common.BASE_DIR / "data" / "chess_api_cache.json")
DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")
PLAYER_RAW = _common.CONFIG.get("player", "").strip()
PLAYER = PLAYER_RAW

TIME_CLASS = "bullet"
MAX_BULLET_BASE_TIME = 120
DAYS_TO_FETCH = 365
CACHE_ROTATION_DAYS = 400

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

_STATS = {"http_ok": 0, "http_err": 0, "http_429": 0, "http_404": 0}


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


def get_db_game_urls() -> set:
    """Возвращает множество URL партий, которые УЖЕ записаны в SQLite (chess.db)."""
    if not os.path.exists(DB_FILE):
        return set()
    try:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute("SELECT url FROM games WHERE url IS NOT NULL")
        urls = {row[0] for row in cur.fetchall()}
        conn.close()
        return urls
    except Exception as e:
        print(f"⚠️ Не удалось прочитать список партий из БД ({e}) — считаем БД пустой.")
        return set()


def get_api_data(url: str, cache: dict, retries: int = 3, force: bool = False):
    """
    Возвращает JSON или None.
    Cache-buster (?t=...) и Cache-Control: no-cache для force-запросов.
    """
    if not force and url in cache:
        return cache[url]

    req_url = url
    if force:
        req_url = f"{url}{'&' if '?' in url else '?'}t={int(time.time())}"

    headers = HEADERS.copy()
    headers["Cache-Control"] = "no-cache"
    headers["Pragma"] = "no-cache"

    last_error = None
    for attempt in range(retries):
        try:
            response = requests.get(
                req_url, headers=headers, impersonate="safari184",
                verify=False, timeout=30,
            )
            if response.status_code == 200:
                _STATS["http_ok"] += 1
                try:
                    data = response.json()
                    cache[url] = data
                    return data
                except Exception as e:
                    print(f"  ⚠️ Ошибка парсинга JSON на {url[-40:]}: {e}")
                    last_error = f"JSON error: {e}"
                    time.sleep(2)
                    continue
            elif response.status_code == 429:
                _STATS["http_429"] += 1
                print(f"  ⚠️ 429 на {url[-40:]}. Пауза 10 сек...")
                time.sleep(10)
                last_error = "429 rate limit"
                continue
            elif response.status_code == 404:
                _STATS["http_404"] += 1
                print(f"  ⚠️ 404 на {url[-40:]}")
                return None
            else:
                _STATS["http_err"] += 1
                print(f"  ⚠️ HTTP {response.status_code} на {url[-40:]}")
                time.sleep(2)
                last_error = f"HTTP {response.status_code}"
        except Exception as e:
            _STATS["http_err"] += 1
            print(f"  ⚠️ Ошибка сети на {url[-40:]}: {e}")
            time.sleep(2)
            last_error = str(e)

    if last_error:
        print(f"  ❌ Не удалось получить {url[-40:]}: {last_error}")
    return None


def fetch_all_games(player: str, cache: dict) -> list:
    player_lower = player.lower()
    print(f"Загрузка архивов для {player} (URL: {player_lower})...")

    archives_url = f"https://api.chess.com/pub/player/{player_lower}/games/archives"
    data = get_api_data(archives_url, cache, force=True)
    if not data or "archives" not in data:
        print("❌ Не удалось получить список архивов.")
        return []

    archives = data["archives"]
    print(f"✅ Найдено месяцев в архиве: {len(archives)}")

    now_utc = datetime.now(timezone.utc)
    current_month_url = (
        f"https://api.chess.com/pub/player/{player_lower}/games/"
        f"{now_utc.year}/{now_utc.month:02d}"
    )
    prev_month_date = now_utc.replace(day=1) - timedelta(days=1)
    prev_month_url = (
        f"https://api.chess.com/pub/player/{player_lower}/games/"
        f"{prev_month_date.year}/{prev_month_date.month:02d}"
    )

    fetch_urls = []
    seen_urls = set()
    for u in (current_month_url, prev_month_url):
        if u not in seen_urls:
            fetch_urls.append(u)
            seen_urls.add(u)
    for u in reversed(archives):
        if u not in seen_urls:
            fetch_urls.append(u)
            seen_urls.add(u)

    cutoff_utc = int((now_utc - timedelta(days=DAYS_TO_FETCH)).timestamp())
    all_games, existing_urls = [], set()

    counters = {"raw": 0, "time_class": 0, "time_control": 0, "old": 0, "dup": 0, "kept": 0}
    fetched_months = 0
    empty_months = []

    for url in fetch_urls:
        parts = url.split("/")
        if len(parts) < 2:
            continue
        month_str = f"{parts[-2]}/{parts[-1]}"
        is_recent = url in (current_month_url, prev_month_url)

        try:
            year, month = int(parts[-2]), int(parts[-1])
            archive_date = datetime(year, month, 1, tzinfo=timezone.utc)
            if archive_date < now_utc - timedelta(days=DAYS_TO_FETCH + 10) and not is_recent:
                continue
        except ValueError:
            pass

        print(f"  Загрузка месяца: {month_str} {'(force)' if is_recent else ''} ...")
        month_data = get_api_data(url, cache, force=is_recent)
        if not month_data:
            print(f"    ⚠️ пустой ответ")
            empty_months.append(month_str)
            continue
        fetched_months += 1

        games_in_month = month_data.get("games", [])
        if is_recent and not games_in_month:
            print(f"    ⚠️ {month_str}: 0 партий в ответе (возможно, API лагает)")

        for g in games_in_month:
            counters["raw"] += 1
            g_url = g.get("url")
            if not g_url:
                continue
            if g_url in existing_urls:
                counters["dup"] += 1
                continue
            if g.get("end_time", 0) < cutoff_utc:
                counters["old"] += 1
                continue
            if g.get("time_class") != TIME_CLASS:
                counters["time_class"] += 1
                continue
            tc = g.get("time_control", "")
            if tc:
                try:
                    if int(tc.split("+")[0]) > MAX_BULLET_BASE_TIME:
                        counters["time_control"] += 1
                        continue
                except ValueError:
                    pass
            all_games.append(g)
            existing_urls.add(g_url)
            counters["kept"] += 1

    print(f"📊 Месяцев получено: {fetched_months}, пустых: {len(empty_months)}")
    if empty_months:
        print(f"   Пустые: {', '.join(empty_months[:5])}{'...' if len(empty_months) > 5 else ''}")
    
    if all_games:
        latest_end_time = max(g.get("end_time", 0) for g in all_games)
        dt_utc = datetime.fromtimestamp(latest_end_time, timezone.utc)
        dt_local = dt_utc.astimezone(timezone(timedelta(hours=3)))
        print(
            f"📅 Самая свежая партия в ответе API: "
            f"{dt_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC "
            f"({dt_local.strftime('%d.%m.%Y %H:%M:%S')} МСК)"
        )

    print(
        f"📊 Отсев: raw={counters['raw']} | "
        f"time_class≠{TIME_CLASS}={counters['time_class']} | "
        f"base>{MAX_BULLET_BASE_TIME}с={counters['time_control']} | "
        f"старше {DAYS_TO_FETCH}д={counters['old']} | "
        f"дубли={counters['dup']} | "
        f"✅ kept={counters['kept']}"
    )

    print(f"✅ Всего подходящих партий (bullet за {DAYS_TO_FETCH} дней): {len(all_games)}")
    return all_games


def get_games_from_cache(
    player: str = PLAYER,
    days: int = DAYS_TO_FETCH,
    time_class: str = TIME_CLASS,
    max_base: int = MAX_BULLET_BASE_TIME,
    require_pgn: bool = True,
) -> list:
    if not os.path.exists(CACHE_FILE):
        print(f"⚠️ Нет {CACHE_FILE}. Сначала запусти 01_fetch_chess_api.py.")
        return []

    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cache = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ Битый JSON в {CACHE_FILE}: {e}. Запусти 01_fetch_chess_api.py.")
        return []
    except Exception as e:
        print(f"❌ Не удалось прочитать {CACHE_FILE}: {e}.")
        return []

    player_lower = player.lower()
    archives_url = f"https://api.chess.com/pub/player/{player_lower}/games/archives"

    archives_data = cache.get(archives_url)
    if archives_data is None:
        alt_url = f"https://api.chess.com/pub/player/{player}/games/archives"
        archives_data = cache.get(alt_url)
        if archives_data is not None:
            print(f"🔧 Найден archives_url в другом регистре — использую fallback.")
    if archives_data is None:
        print("⚠️ В кэше нет списка архивов. Запусти 01_fetch_chess_api.py.")
        return []

    archives = archives_data.get("archives", [])

    now_utc = datetime.now(timezone.utc)
    current_month_url = (
        f"https://api.chess.com/pub/player/{player_lower}/games/"
        f"{now_utc.year}/{now_utc.month:02d}"
    )
    prev_month_date = now_utc.replace(day=1) - timedelta(days=1)
    prev_month_url = (
        f"https://api.chess.com/pub/player/{player_lower}/games/"
        f"{prev_month_date.year}/{prev_month_date.month:02d}"
    )

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


def rotate_cache(cache: dict, cutoff_days: int = CACHE_ROTATION_DAYS) -> dict:
    cutoff = int((datetime.now(timezone.utc) - timedelta(days=cutoff_days)).timestamp())
    rotated = {}
    for url, data in cache.items():
        if url.startswith("_") or "archives" in url:
            rotated[url] = data
        elif isinstance(data, dict) and data.get("games"):
            if any(g.get("end_time", 0) >= cutoff for g in data["games"]):
                rotated[url] = data
    return rotated


def main():
    print("=" * 60)
    print(" FETCH CHESS.COM API → data/chess_api_cache.json")
    print("=" * 60)

    if not PLAYER:
        print("❌ В config.json не указан 'player' — прерываю.")
        raise SystemExit(1)

    cache = load_cache()
    print(f"📂 В кэше уже: {len(cache)} URL")

    old_cache_urls = set()
    for url, data in cache.items():
        if not isinstance(data, dict):
            continue
        for g in data.get("games", []):
            g_url = g.get("url")
            if g_url:
                old_cache_urls.add(g_url)
    print(f"📂 Партий в JSON-кэше до запроса: {len(old_cache_urls)}")

    db_urls = get_db_game_urls()
    print(f"🗄️ Проанализировано партий в БД (chess.db): {len(db_urls)}")

    try:
        all_games = fetch_all_games(PLAYER, cache)
    except Exception as e:
        print(f"❌ Критическая ошибка fetch: {e}")
        traceback.print_exc()
        raise SystemExit(1)

    if not all_games:
        print("❌ Fetch вернул 0 партий. Причины: 429/403/404/сеть или "
              "0 партий в ответе API.")
        raise SystemExit(1)

    new_in_cache = [g for g in all_games if g.get("url") not in old_cache_urls]
    missing_in_db = [g for g in all_games if g.get("url") not in db_urls]

    print(
        f"📊 Итог: всего в окне {len(all_games)} | "
        f"новых для JSON-кэша: {len(new_in_cache)} | "
        f"ожидают анализа в БД: {len(missing_in_db)}"
    )

    print(f"\n🧹 Ротация кэша (> {CACHE_ROTATION_DAYS} дней)...")
    old_size = len(cache)
    cache = rotate_cache(cache)
    cache["_last_fetch"] = datetime.now(timezone.utc).isoformat()
    cache["_last_new_count"] = len(new_in_cache)
    cache["_last_pending_db_count"] = len(missing_in_db)
    cache["_last_total_count"] = len(all_games)
    save_cache(cache)
    print(f"🧹 Кэш: {old_size} → {len(cache)} URL (включая _meta)")

    print(f"\n✅ Готово. Кэш: {CACHE_FILE}")
    print(f"   HTTP: ok={_STATS['http_ok']}, err={_STATS['http_err']}, "
          f"429={_STATS['http_429']}, 404={_STATS['http_404']}")

    # Если есть партии, которых ещё нет в БД chess.db — запускаем 02_analyze_stockfish.py
    if missing_in_db:
        print(f"\n🚀 Найдено {len(missing_in_db)} партий, которых ещё нет в БД! Запускаю 02_analyze_stockfish.py...")
        analyze_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "02_analyze_stockfish.py")
        if os.path.exists(analyze_script):
            subprocess.run([sys.executable, analyze_script], check=False)
        else:
            print(f"⚠️ Файл {analyze_script} не найден. Запусти его вручную.")
    else:
        print("\n✅ Все скачанные партии уже проанализированы и находятся в БД chess.db!")


if __name__ == "__main__":
    main()