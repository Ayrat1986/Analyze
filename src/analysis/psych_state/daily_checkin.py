# ============================================================
# analysis/psych_state/daily_checkin.py (v19.1)
# ============================================================
import os
from datetime import datetime, timedelta
from core.пороги import get as get_threshold
from analysis.common import report_context
from .common import _conn, REPORTS_DIR

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

def report_daily_checkin():
    conn = _conn(); cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='checkins'")
    if not cur.fetchone():
        with report_context("daily_checkin") as w:
            w.w("⚠️ Таблица checkins не найдена. Запусти 03_migrate_sqlite.py.")
        conn.close(); return

    lookback = get_threshold("checkin_lookback_days", 90)
    min_pairs = get_threshold("checkin_min_pairs", 5)
    cutoff = int((datetime.now() - timedelta(days=lookback)).timestamp())

    cur.execute("""
        SELECT c.date, c.sleep_hours, c.mood, c.energy, c.stress, c.note,
               COUNT(g.url) AS games_n, AVG(g.acpl) AS avg_acpl, SUM(g.won) AS wins, SUM(g.draw) AS draws
        FROM checkins c
        LEFT JOIN games g ON date(g.end_time, 'unixepoch', '+3 hours') = c.date AND g.is_lag=0 AND g.is_cheater=0
        WHERE c.created_at >= ?
        GROUP BY c.date ORDER BY c.date DESC
    """, (cutoff,))
    rows = cur.fetchall()
    
    days_with_games = [r for r in rows if (r[6] or 0) > 0]

    with report_context("daily_checkin") as w:
        w.w_separator(title="DAILY CHECK-IN")
        w.w(f"Окно: {lookback} дней | Чек-инов: {len(rows)} | С играми: {len(days_with_games)}\n")

        if len(days_with_games) < min_pairs:
            w.w(f"⚠️ Мало данных для корреляции: {len(days_with_games)} дней (нужно ≥ {min_pairs}).")

        def bucket_stats(getter, buckets, label_fn):
            stats = {label: {"n": 0, "acpl_sum": 0.0} for label in buckets}
            for date, sleep, mood, energy, stress, note, games_n, acpl, wins, draws in days_with_games:
                val = getter(sleep, mood, energy, stress)
                if val is None: continue
                label = label_fn(val)
                if label in stats:
                    stats[label]["n"] += 1
                    stats[label]["acpl_sum"] += acpl or 0
            return stats

        def print_table(stats, labels, title):
            w.w(f"📊 {title}:")
            for label in labels:
                d = stats[label]
                if d["n"] == 0: continue
                avg = d["acpl_sum"] / d["n"]
                w.w(f"  {label:<12} Дней: {d['n']:<4} ACPL: {avg:.1f}")
            w.w()

        print_table(bucket_stats(lambda s, m, e, st: s, ["<6", "6-7", "7-8", "8+"], lambda v: "<6" if v < 6 else ("6-7" if v < 7 else ("7-8" if v < 8 else "8+"))), ["<6", "6-7", "7-8", "8+"], "СОН")
        print_table(bucket_stats(lambda s, m, e, st: e, ["1-3", "4-6", "7-10"], lambda v: "1-3" if v <= 3 else ("4-6" if v <= 6 else "7-10")), ["1-3", "4-6", "7-10"], "ЭНЕРГИЯ")

        w.w("💡 Как вводить: python src/09_psych_state.py --checkin \"сон=7,энергия=6\"")
        
    conn.close()

def run_daily_checkin():
    report_daily_checkin()