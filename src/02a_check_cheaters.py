# ============================================================
# 02a_check_cheaters.py — v19.8
# FIX: Защита от пустого/битого chess_api_cache.json (JSONDecodeError)
#      и резервный сбор соперников из SQLite (chess.db).
# ============================================================
from curl_cffi import requests
import time
import os
import re
import json
import sqlite3
import argparse
from datetime import datetime, timezone, timedelta

import _common
from _chess_utils import _HARDCODED_CHEATERS

CACHE_FILE = str(_common.BASE_DIR / "data" / "chess_api_cache.json")
DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")
CHEATERS_FILE = str(_common.BASE_DIR / "data" / "cheaters.txt")
CHECKED_FILE = str(_common.BASE_DIR / "data" / "checked_players.txt")
PLAYER = _common.CONFIG.get("player", "")
EMAIL = _common.CONFIG.get("email", "")
DAYS_TO_FETCH = 365

HEADERS = {"User-Agent": f"MyChessExport/1.0 (contact: {EMAIL})"}


# ============================================================
# CHEATERS — dict{opp: date}
# ============================================================
def load_known_cheaters_dict() -> dict:
    """
    Читает data/cheaters.txt.
    Возвращает {nick: "YYYY-MM-DD"}.
    Fallback: _HARDCODED_CHEATERS с датой 2026-01-01.
    """
    if not os.path.exists(CHEATERS_FILE):
        return {c: "2026-01-01" for c in _HARDCODED_CHEATERS}

    result = {}
    with open(CHEATERS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            raw = line.strip()
            if not raw:
                continue
            parts = raw.split("#", 1)
            nick = parts[0].strip().lower()
            if not nick:
                continue
            if nick.startswith("=") or "найденные" in nick or "читеров не" in nick:
                continue
            date_str = "2026-01-01"
            if len(parts) > 1:
                comment = parts[1]
                m = re.search(r"(\d{4}-\d{2}-\d{2})", comment)
                if m:
                    date_str = m.group(1)
            result[nick] = date_str

    return result if result else {c: "2026-01-01" for c in _HARDCODED_CHEATERS}


def save_cheaters(cheaters: dict) -> None:
    """
    Сохраняет dict{opp: date} в cheaters.txt.
    НЕ перезаписывает старые даты.
    """
    os.makedirs(os.path.dirname(CHEATERS_FILE), exist_ok=True)
    with open(CHEATERS_FILE, "w", encoding="utf-8") as f:
        f.write("НАЙДЕННЫЕ ЧИТЕРЫ:\n" + "=" * 30 + "\n")
        for c in sorted(cheaters.keys()):
            date_str = cheaters[c]
            f.write(f"{c} # добавлен {date_str}\n")


# ============================================================
# CHECKED — set (без дат)
# ============================================================
def load_checked_players() -> set:
    if not os.path.exists(CHECKED_FILE):
        return set()
    result = set()
    with open(CHECKED_FILE, "r", encoding="utf-8") as f:
        for line in f:
            s = line.split("#")[0].strip().lower()
            if s:
                result.add(s)
    return result


def save_checked(checked: set) -> None:
    today = datetime.now().strftime("%Y-%m-%d")
    os.makedirs(os.path.dirname(CHECKED_FILE), exist_ok=True)
    with open(CHECKED_FILE, "w", encoding="utf-8") as f:
        for c in sorted(checked):
            f.write(f"{c} # проверен {today}\n")


# ============================================================
# ОППОНЕНТЫ
# ============================================================
def get_opponents_from_db(days: int = DAYS_TO_FETCH) -> set:
    """Резервный сбор соперников из SQLite (chess.db), если JSON-кэш пуст или битый."""
    if not os.path.exists(DB_FILE):
        return set()
    try:
        cutoff_ts = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
        player_lower = PLAYER.lower()
        opponents = set()
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute("SELECT white, black FROM games WHERE end_time >= ?", (cutoff_ts,))
        for w, b in cur.fetchall():
            w_l = (w or "").lower()
            b_l = (b or "").lower()
            if w_l == player_lower and b_l:
                opponents.add(b_l)
            elif b_l == player_lower and w_l:
                opponents.add(w_l)
        conn.close()
        return opponents
    except Exception as e:
        print(f"⚠️ Не удалось прочитать соперников из БД: {e}")
        return set()


def get_opponents_from_cache(days: int = DAYS_TO_FETCH) -> set:
    if not os.path.exists(CACHE_FILE):
        print(f"⚠️ Нет {CACHE_FILE}. Запусти 01_fetch_chess_api.py.")
        return get_opponents_from_db(days)

    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cache = json.load(f)
    except (json.JSONDecodeError, Exception) as e:
        print(f"❌ Файл кэша {CACHE_FILE} пуст или повреждён ({e}).")
        print("   💡 Запусти 01_fetch_chess_api.py, чтобы пересоздать кэш.")
        db_opps = get_opponents_from_db(days)
        if db_opps:
            print(f"   🔄 Беру резервный список соперников из chess.db: {len(db_opps)}")
        return db_opps

    player_lower = PLAYER.lower()
    archives_url = f"https://api.chess.com/pub/player/{player_lower}/games/archives"

    archives_data = cache.get(archives_url)
    if not archives_data:
        alt_url = f"https://api.chess.com/pub/player/{PLAYER}/games/archives"
        archives_data = cache.get(alt_url)
        if archives_data:
            archives_url = alt_url

    if not archives_data:
        print("⚠️ В кэше нет списка архивов (возможно, нужно запустить 01_fetch_chess_api.py).")
        return get_opponents_from_db(days)

    cutoff_ts = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
    opponents = set()

    now_utc = datetime.now(timezone.utc)
    current_month_url = f"https://api.chess.com/pub/player/{player_lower}/games/{now_utc.year}/{now_utc.month:02d}"
    prev_month_date = now_utc.replace(day=1) - timedelta(days=1)
    prev_month_url = f"https://api.chess.com/pub/player/{player_lower}/games/{prev_month_date.year}/{prev_month_date.month:02d}"

    all_urls = [current_month_url, prev_month_url] + list(reversed(archives_data.get("archives", [])))
    seen_urls = set()

    for url in all_urls:
        if url in seen_urls:
            continue
        seen_urls.add(url)

        data = cache.get(url)
        if not data:
            mixed_url = url.replace(player_lower, PLAYER)
            data = cache.get(mixed_url)

        if not data:
            continue

        for g in data.get("games", []):
            if g.get("end_time", 0) < cutoff_ts:
                continue
            white = g.get("white", {}).get("username", "").lower()
            black = g.get("black", {}).get("username", "").lower()

            if white == player_lower:
                if black:
                    opponents.add(black)
            elif black == player_lower:
                if white:
                    opponents.add(white)

    return opponents


def check_one(opp: str) -> tuple[str, str | None]:
    try:
        url = f"https://api.chess.com/pub/player/{opp}"
        res = requests.get(
            url, headers=HEADERS, impersonate="safari184",
            verify=False, timeout=15,
            # Причина: обход ошибки curl(77) на Windows (корпоративный антивирус).
        )
        if res.status_code == 200:
            data = res.json()
            status = (data.get("status") or "").lower()
            if "fair_play" in status or "closed" in status:
                return "cheater", status
            return "ok", status
        if res.status_code == 429:
            return "rate_limit", None
        if res.status_code == 404:
            return "ok", "404"
        return "error", f"HTTP {res.status_code}"
    except Exception as e:
        return "error", str(e)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Перепроверить всех")
    parser.add_argument("--limit", type=int, default=0, help="Макс. новых за запуск")
    args = parser.parse_args()

    print("=" * 60)
    print(" 02a_check_cheaters.py — v19.8 (safe cache + DB fallback)")
    print("=" * 60)

    if not PLAYER:
        print("⚠️ В config.json нет 'player' — прерываю.")
        return

    opponents = get_opponents_from_cache(DAYS_TO_FETCH)
    print(f"🎯 Соперников за {DAYS_TO_FETCH} дней: {len(opponents)}")

    existing_cheaters = load_known_cheaters_dict()
    checked = set() if args.force else load_checked_players()

    to_check = [
        o for o in opponents
        if o not in existing_cheaters and o not in checked
    ]
    if args.limit:
        to_check = to_check[: args.limit]

    print(f"🚫 Уже в cheaters.txt: {len(existing_cheaters)}")
    print(f"✅ Уже проверено: {len(checked)}")
    print(f"🔄 К проверке сейчас: {len(to_check)}")

    if not to_check:
        print("✅ Все соперники уже проверены. Готово.")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    new_cheaters = {}
    new_checked = set()
    rate_limited = False

    for i, opp in enumerate(to_check, 1):
        if i % 10 == 0 or i == 1:
            print(f"  ... {i}/{len(to_check)}")
        status, extra = check_one(opp)
        if status == "cheater":
            new_cheaters[opp] = today
            print(f"  🚨 {opp}: {extra}")
        elif status == "ok":
            new_checked.add(opp)
        elif status == "rate_limit":
            print(f"  ⚠️ 429 на {opp}. Пауза 60 сек...")
            time.sleep(60)
            rate_limited = True
            status2, extra2 = check_one(opp)
            if status2 == "cheater":
                new_cheaters[opp] = today
            elif status2 == "ok":
                new_checked.add(opp)
        else:
            print(f"  ⚠️ {opp}: {extra}")

        time.sleep(0.8)

    all_cheaters = {**existing_cheaters, **new_cheaters}
    all_checked = checked | new_checked

    save_cheaters(all_cheaters)
    save_checked(all_checked)

    print(f"\n✅ Готово.")
    print(f"   Новых читеров: {len(new_cheaters)}")
    print(f"   Новых проверено: {len(new_checked)}")
    print(f"   Всего читеров в файле: {len(all_cheaters)}")
    if rate_limited:
        print("   ⚠️ Был rate limit, часть могла не провериться — запусти снова")


if __name__ == "__main__":
    main()