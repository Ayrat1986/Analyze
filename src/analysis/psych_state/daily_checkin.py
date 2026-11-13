# ============================================================
# analysis/psych_state/daily_checkin.py (v25.0)
# §28: удалён report_daily_checkin (мёртвый модуль — 0 записей).
# Оставлены _parse_checkin и write_checkin (для 09_psych_state.py --checkin).
# ============================================================
import sqlite3
from datetime import datetime
from .common import _conn


def _parse_checkin(s):
    aliases = {
        "сон": "sleep_hours", "sleep": "sleep_hours",
        "настроение": "mood", "mood": "mood",
        "энергия": "energy", "энер": "energy", "energy": "energy",
        "стресс": "stress", "stress": "stress",
        "заметка": "note", "note": "note",
    }
    result = {}
    for part in s.split(","):
        part = part.strip()
        if not part or "=" not in part: continue
        k, v = part.split("=", 1)
        key = aliases.get(k.strip().lower())
        if not key:
            print(f"⚠️ Неизвестный ключ: {k.strip()!r} (пропущен)")
            continue
        try:
            if key == "note": result[key] = v.strip()
            elif key == "sleep_hours": result[key] = float(v.strip().replace(",", "."))
            else: result[key] = int(v.strip())
        except ValueError:
            print(f"⚠️ Неверное значение для {k.strip()}: {v.strip()!r}")
    return result


def write_checkin(data):
    conn = _conn()
    today = datetime.now().strftime("%Y-%m-%d")
    now_ts = int(datetime.now().timestamp())
    conn.execute("""
        INSERT INTO checkins (date, sleep_hours, mood, energy, stress, note, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(date) DO UPDATE SET
            sleep_hours = COALESCE(excluded.sleep_hours, checkins.sleep_hours),
            mood = COALESCE(excluded.mood, checkins.mood),
            energy = COALESCE(excluded.energy, checkins.energy),
            stress = COALESCE(excluded.stress, checkins.stress),
            note = COALESCE(excluded.note, checkins.note)
    """, (today, data.get("sleep_hours"), data.get("mood"), data.get("energy"), data.get("stress"), data.get("note"), now_ts))
    conn.commit()
    conn.close()
    print(f"✅ Чек-ин на {today}: {data}")