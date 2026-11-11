# ============================================================
# 02a_check_cheaters.py — v19.6
# Исправлено: сохранение дат в cheaters.txt (не перезаписывать старые)
# ============================================================
from curl_cffi import requests
import time
import os
import json
import argparse
from datetime import datetime, timezone, timedelta
from importlib import import_module

import _common
from _chess_utils import _HARDCODED_CHEATERS

CACHE_FILE = str(_common.BASE_DIR / "data" / "chess_api_cache.json")
CHEATERS_FILE = str(_common.BASE_DIR / "data" / "cheaters.txt")
CHECKED_FILE = str(_common.BASE_DIR / "data" / "checked_players.txt")
PLAYER = _common.CONFIG.get("player", "")
EMAIL = _common.CONFIG.get("email", "")
DAYS_TO_FETCH = 95

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
            # Формат: "nick # добавлен 2026-11-06" или просто "nick"
            raw = line.strip()
            if not raw:
                continue
            # Убираем комментарий
            parts = raw.split("#", 1)
            nick = parts[0].strip().lower()
            if not nick:
                continue
            # Пропускаем заголовки
            if nick.startswith("=") or "найденные" in nick or "читеров не" in nick:
                continue
            # Ищем дату в комментарии
            date_str = "2026-01-01"  # fallback
            if len(parts) > 1:
                comment = parts[1]
                # "добавлен 2026-11-06"
                import re
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
# CHECKED — set (без дат, как было)
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
def get_opponents_from_cache(days: int = DAYS_TO_FETCH) -> set:
    if not os.path.exists(CACHE_FILE):
        print(f"⚠️ Нет {CACHE_FILE}. Запусти 01_fetch_chess_api.py.")
        return set()
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        cache = json.load(f)

    archives_url = f"https://api.chess.com/pub/player/{PLAYER}/games/archives"
    if archives_url not in cache:
        return set()

    cutoff_ts = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
    opponents = set()

    for url in cache.get(archives_url, {}).get("archives", []):
        if url not in cache:
            continue
        for g in cache[url].get("games", []):
            if g.get("end_time", 0) < cutoff_ts:
                continue
            white = g.get("white", {}).get("username", "").lower()
            black = g.get("black", {}).get("username", "").lower()
            if white == PLAYER.lower():
                if black:
                    opponents.add(black)
            elif black == PLAYER.lower():
                if white:
                    opponents.add(white)
    return opponents


def check_one(opp: str) -> tuple[str, str | None]:
    try:
        url = f"https://api.chess.com/pub/player/{opp}"
        res = requests.get(
            url, headers=HEADERS, impersonate="safari184",
            verify=False, timeout=15,
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
    print(" 02a_check_cheaters.py — v19.6 (сохранение дат)")
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
    new_cheaters = {}  # {nick: today}
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

    # Объединяем: старые даты + новые
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