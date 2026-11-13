# ============================================================
# analysis/coach/codex.py — v25.0
# §17: SpeedR берется из core.метрики.
# §28: убрано чтение metrics.json (positional_weaknesses удален).
# ============================================================
import os
import sqlite3
import json
import random
import statistics
from datetime import datetime, timezone, timedelta

import _common
from core.метрики import game_rating, speed_rating

try:
    from _chess_utils import parse_time_spent
except ImportError:
    parse_time_spent = None

DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")
RULES_FILE = str(_common.BASE_DIR / "data" / "codex_rules.json")
REPORTS_DIR = str(_common.REPORTS_DIR)
PLAYER = _common.CONFIG.get("player", "")


def _conn():
    return sqlite3.connect(DB_FILE)


def _compute_avg_time_window(cur, days=90):
    """Среднее время на ход по окну (через clocks)."""
    if parse_time_spent is None:
        return 0
    ts = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
    cur.execute("""
        SELECT clocks, white FROM games
        WHERE is_lag=0 AND is_cheater=0 AND end_time >= ?
          AND acpl > 0 AND clocks IS NOT NULL AND clocks != '[]'
    """, (ts,))
    player = (PLAYER or "").lower()
    all_times = []
    for clocks_raw, white in cur.fetchall():
        try:
            clocks = json.loads(clocks_raw)
            if not clocks:
                continue
        except Exception:
            continue
        player_is_white = (white or "").lower() == player
        times = parse_time_spent(clocks, player_is_white)
        if times:
            all_times.append(sum(times) / len(times))
    return statistics.mean(all_times) if all_times else 0


def _compute_aggression_2700(cur):
    """Среднее число скачков eval >= 50 CP на игру против 2700+."""
    cur.execute("""
        SELECT eval_history FROM games
        WHERE is_lag=0 AND is_cheater=0 AND opp_rating >= 2700
          AND eval_history IS NOT NULL AND eval_history != '[]'
    """)
    agg_values = []
    for (raw,) in cur.fetchall():
        try:
            hist = json.loads(raw)
        except Exception:
            continue
        if not hist:
            continue
        agg = 0
        prev = None
        for move, ev in hist:
            if prev is not None and ev - prev >= 50:
                agg += 1
            prev = ev
        agg_values.append(agg)
    return statistics.mean(agg_values) if agg_values else None


def get_metrics(conn):
    cur = conn.cursor()
    metrics = {}

    cur.execute("SELECT ROUND(AVG(critical_moments), 1) FROM games "
                "WHERE is_lag=0 AND is_cheater=0 AND critical_moments IS NOT NULL")
    metrics["avg_chaos_index"] = cur.fetchone()[0] or 0

    cur.execute("SELECT ROUND(AVG(acpl_middlegame), 1) FROM games "
                "WHERE is_lag=0 AND is_cheater=0")
    metrics["acpl_middlegame"] = cur.fetchone()[0] or 0

    cur.execute("SELECT ROUND(AVG(acpl_opening), 1) FROM games "
                "WHERE is_lag=0 AND is_cheater=0")
    metrics["acpl_opening"] = cur.fetchone()[0] or 0

    cur.execute("SELECT ROUND(AVG(acpl_endgame), 1) FROM games "
                "WHERE is_lag=0 AND is_cheater=0 AND acpl_endgame > 0 "
                "AND reason NOT LIKE '%просроч%' AND reason NOT LIKE '%time%'")
    metrics["acpl_endgame"] = cur.fetchone()[0] or 0

    cur.execute("SELECT COUNT(*), SUM(CASE WHEN reason = 'просрочка' THEN 1 ELSE 0 END) "
                "FROM games WHERE is_lag=0 AND is_cheater=0 AND max_eval_advantage >= 300")
    total_adv, timeout_adv = cur.fetchone()
    metrics["timeout_losses_percent"] = (timeout_adv / total_adv * 100) if total_adv else 0

    for rng, lo, hi in [("2400", 2400, 2500), ("2600", 2600, 2700)]:
        cur.execute(
            f"SELECT COUNT(*), SUM(won) FROM games WHERE is_lag=0 AND is_cheater=0 "
            f"AND opp_rating >= {lo} AND opp_rating < {hi}")
        total, wins = cur.fetchone()
        metrics[f"winrate_{rng}"] = (wins / total * 100) if total else 0

    cur.execute("SELECT COUNT(*) FROM blunders b JOIN games g ON g.url=b.game_url "
                "WHERE g.is_lag=0 AND g.is_cheater=0 AND b.is_my_blunder=1 "
                "AND b.is_berserk=0 AND b.is_instant=0")
    total_blunders = cur.fetchone()[0] or 1
    cur.execute("SELECT COUNT(*) FROM ("
                "SELECT b1.game_url, b1.move_num FROM blunders b1 "
                "JOIN games g ON g.url=b1.game_url "
                "JOIN blunders b2 ON b1.game_url=b2.game_url "
                "WHERE g.is_lag=0 AND g.is_cheater=0 "
                "AND b1.is_my_blunder=1 AND b2.is_my_blunder=1 "
                "AND b1.is_berserk=0 AND b1.is_instant=0 "
                "AND b2.is_berserk=0 AND b2.is_instant=0 "
                "AND b2.move_num > b1.move_num AND (b2.move_num - b1.move_num) <= 5)")
    cascades = cur.fetchone()[0] or 0
    metrics["cascade_tilt_percent"] = (cascades / total_blunders * 100) if total_blunders else 0

    cur.execute("SELECT ROUND(AVG(momentum_after_blunder), 1) FROM games "
                "WHERE is_lag=0 AND is_cheater=0 AND momentum_after_blunder > 0")
    metrics["momentum_after_blunder"] = cur.fetchone()[0] or 0

    for eco in ["D04", "B18"]:
        cur.execute(
            f"SELECT COUNT(*), SUM(won) FROM games WHERE is_lag=0 AND is_cheater=0 "
            f"AND substr(eco,1,3) = '{eco}'")
        total, wins = cur.fetchone()
        metrics[f"winrate_{eco}"] = (wins / total * 100) if total else 0

    for hour in ["19", "02"]:
        cur.execute(
            f"SELECT ROUND(AVG(acpl), 1) FROM games WHERE is_lag=0 AND is_cheater=0 "
            f"AND strftime('%H', datetime(end_time, 'unixepoch', '+3 hours')) = '{hour}'")
        metrics[f"acpl_{hour}"] = cur.fetchone()[0] or 0

    # metrics.json больше не пишется (positional_weaknesses удалён в v25.0).
    # Правила Кодекса не используют open_king_percent / isolated_pawn_acpl.

    cur.execute("""
        SELECT CASE WHEN rn <= 5 THEN '1-5' WHEN rn <= 10 THEN '6-10'
                    WHEN rn <= 20 THEN '11-20' WHEN rn <= 30 THEN '21-30'
                    WHEN rn <= 50 THEN '31-50' WHEN rn <= 100 THEN '51-100'
                    ELSE '101+' END AS bucket,
               AVG(acpl) AS avg_acpl, COUNT(*) AS cnt
        FROM (SELECT acpl, ROW_NUMBER() OVER (
                  PARTITION BY date(end_time, 'unixepoch', '+3 hours')
                  ORDER BY end_time) AS rn
              FROM games WHERE is_lag=0 AND is_cheater=0 AND acpl > 0)
        GROUP BY bucket
    """)
    res = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
    for b_name in ["1-5", "6-10", "11-20", "21-30", "31-50", "51-100", "101+"]:
        if b_name in res and res[b_name][1] > 0:
            metrics[f"acpl_bucket_{b_name.replace('-', '_').replace('+', '')}"] = res[b_name][0]

    start_acpl, start_n = res.get("1-5", (0, 0))
    worst_drop = None
    for b_name in ["101+", "51-100", "31-50", "21-30", "11-20", "6-10"]:
        if b_name in res and res[b_name][1] > 0 and start_n > 0:
            drop = res[b_name][0] - start_acpl
            if worst_drop is None or drop > worst_drop:
                worst_drop = drop
    metrics["endurance_drop"] = worst_drop

    # avg_time, delta (активируют правила delta_high, delta_low, avg_time_high)
    avg_time = _compute_avg_time_window(cur, days=90)
    if avg_time > 0:
        metrics["avg_time"] = round(avg_time, 2)
        ts_90 = int((datetime.now(timezone.utc) - timedelta(days=90)).timestamp())
        cur.execute("SELECT ROUND(AVG(acpl), 1) FROM games "
                    "WHERE is_lag=0 AND is_cheater=0 AND end_time >= ? AND acpl > 0", (ts_90,))
        acpl_90 = cur.fetchone()[0] or 0
        if acpl_90 > 0:
            game_r = game_rating(acpl_90)
            speed_r = speed_rating(avg_time)  # §17: из ядра
            metrics["delta"] = round(game_r - speed_r, 1)
        else:
            metrics["delta"] = None
    else:
        metrics["avg_time"] = None
        metrics["delta"] = None

    metrics["aggression_2700"] = _compute_aggression_2700(cur)

    return metrics


def check_rules(metrics):
    if not os.path.exists(RULES_FILE):
        return []
    with open(RULES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    matched = []
    for rule in data.get("rules", []):
        if "trigger" not in rule:
            continue
        metric = rule["trigger"]["metric"]
        if metric not in metrics:
            continue
        val = metrics[metric]
        if val is None:
            continue
        op = rule["trigger"]["operator"]
        th = rule["trigger"]["value"]
        is_triggered = False
        if op == ">" and val > th:
            is_triggered = True
        elif op == ">=" and val >= th:
            is_triggered = True
        elif op == "<" and val < th:
            is_triggered = True
        elif op == "<=" and val <= th:
            is_triggered = True
        if is_triggered:
            matched.append({
                "name": rule["name"],
                "advice": rule["advice"],
                "mantra": rule.get("mantra", ""),
                "metric_val": val,
                "priority": rule.get("priority", 1),
                "tag": rule.get("tag", "Разное"),
            })
    return matched


def report_codex_advice():
    if not os.path.exists(DB_FILE):
        print(f"⚠️ codex_advice пропущен.")
        return
    conn = _conn()
    metrics = get_metrics(conn)
    all_matched = check_rules(metrics)
    by_tag = {}
    for r in all_matched:
        by_tag.setdefault(r["tag"], []).append(r)
    sorted_tags = sorted(by_tag.keys(), key=lambda t: max(r["priority"] for r in by_tag[t]), reverse=True)
    final_selection = []
    for tag in sorted_tags:
        rules_in_tag = sorted(by_tag[tag], key=lambda x: x["priority"], reverse=True)
        final_selection.append(random.choice(rules_in_tag[:3]))
    final_selection = final_selection[:5]

    path = os.path.join(REPORTS_DIR, "codex_advice.txt")
    with open(path, "w", encoding="utf-8") as f:
        def w(line=""):
            print(line)
            f.write(line + "\n")
        w("=" * 60)
        w(" 🧠 СОВЕТЫ AI-ТРЕНЕРА")
        w("=" * 60)
        w(f"Сформирован: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        w()
        if not final_selection:
            w("✅ Сегодня все показатели в норме.")
        else:
            w("🚨 ТОП-5 КРИТИЧНЫХ ПРАВИЛ КОДЕКСА:")
            for r in final_selection:
                w(f"\n[{r['tag']}] {r['name']} (Текущее: {r['metric_val']:.1f})")
                w(f"  💡 {r['advice']}")
                if r['mantra']:
                    w(f"  🗣️ Мантра: «{r['mantra']}»")
        w()
        w("=" * 60)
        w(" 💡 ПРАВИЛО ДНЯ:")
        w("=" * 60)
        w("  «Играй не против соперника, а против хаоса в своей голове».")

        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM games WHERE is_lag=0 AND is_cheater=0 AND won=1")
        total_wins = cur.fetchone()[0] or 0
        cur.execute("SELECT COUNT(*) FROM games WHERE is_lag=0 AND is_cheater=0 "
                    "AND won=1 AND reason LIKE '%просроч%'")
        flag_wins = cur.fetchone()[0] or 0
        flag_ratio = (flag_wins / total_wins * 100) if total_wins > 0 else 0

        if flag_ratio > 30:
            w("\n🧠 [Блок 12, п.6] Техника эндшпиля и флаги:")
            w(f"  • {flag_ratio:.1f}% твоих побед ({flag_wins} из {total_wins}) — это победы по флагу.")
            w("  • В этих партиях ты сознательно играешь на время, а не на мат.")
            w("  • Твоя задача — не «учить мат ладьёй», а контролировать время, "
              "когда у соперника осталось < 10 секунд.")
    conn.close()
    print(f"\n✅ {path}")