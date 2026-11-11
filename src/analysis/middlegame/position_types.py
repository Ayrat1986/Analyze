# ============================================================
# analysis/middlegame/position_types.py (v19.1)
# ============================================================
from analysis.common import report_context
from .common import _conn, get_base_filter, get_threshold

def _classify_position_type(cm, length, avg_loss):
    CM_CHAOTIC = get_threshold("position_type_chaotic_cm", 15)
    CM_POS = get_threshold("position_type_positional_cm", 4)
    LEN_POS = get_threshold("position_type_positional_min_length", 60)
    TACT_LOSS = get_threshold("position_type_tactical_loss_cp", 250)
    if cm is None or cm == 0: return "unknown"
    if cm >= CM_CHAOTIC: return "chaotic"
    if cm <= CM_POS and length >= LEN_POS: return "positional"
    if (CM_POS + 1) <= cm <= (CM_CHAOTIC - 1) and avg_loss > TACT_LOSS: return "tactical"
    return "mixed"

def report_position_types():
    conn = _conn()
    cur = conn.cursor()
    base = get_base_filter()

    cur.execute(f"""
        SELECT g.url, g.won, g.draw, g.critical_moments, g.game_length,
               g.acpl, g.acpl_middlegame, g.acpl_endgame, g.opp_rating,
               COALESCE(AVG(b.loss_cp), 0) AS avg_blunder_loss, COUNT(b.id) AS blunders_n
        FROM games g
        LEFT JOIN blunders b ON b.game_url = g.url AND b.is_my_blunder = 1 AND b.is_berserk = 0 AND b.is_instant = 0
        WHERE {base} AND g.critical_moments IS NOT NULL AND g.acpl > 0
        GROUP BY g.url
    """)
    rows = cur.fetchall()

    with report_context("position_type_classifier") as w:
        w.w_separator(title="ТИП ПОЗИЦИИ → WINRATE (классификатор партий)")
        
        if not rows:
            w.w("⚠️ Нет данных (нужен critical_moments из 02).")
            conn.close()
            return

        CM_CHAOTIC = get_threshold("position_type_chaotic_cm", 15)
        CM_POS = get_threshold("position_type_positional_cm", 4)
        LEN_POS = get_threshold("position_type_positional_min_length", 60)
        TACT_LOSS = get_threshold("position_type_tactical_loss_cp", 250)

        labels = {
            "chaotic": f"🌪️ Хаотичная (cm ≥ {CM_CHAOTIC})",
            "positional": f"🏛️ Позиционная (cm ≤ {CM_POS}, длина ≥ {LEN_POS})",
            "tactical": f"⚔️ Тактическая (cm {CM_POS + 1}–{CM_CHAOTIC - 1}, ср. потеря > {TACT_LOSS})",
            "mixed": "🎭 Смешанная",
        }
        buckets = {k: {"n": 0, "w": 0, "d": 0, "l": 0, "acpl": 0, "acpl_mid": 0, "acpl_end": 0, "avg_opp": 0, "blunders": 0, "cm_sum": 0} for k in labels}

        for url, won, draw, cm, length, acpl, acpl_mid, acpl_end, opp_rating, avg_bl, bl_n in rows:
            t = _classify_position_type(cm or 0, length or 0, avg_bl or 0)
            if t == "unknown":
                continue  # <-- ВОТ ЭТА СТРОКА БЫЛА ПОТЕРЯНА
                
            b = buckets[t]
            b["n"] += 1
            if won: b["w"] += 1
            if draw: b["d"] += 1
            if not won and not draw: b["l"] += 1
            b["acpl"] += acpl or 0; b["acpl_mid"] += acpl_mid or 0; b["acpl_end"] += acpl_end or 0
            b["avg_opp"] += opp_rating or 0; b["blunders"] += bl_n or 0; b["cm_sum"] += cm or 0

        w.w(f"  Хаотичная:   critical_moments ≥ {CM_CHAOTIC}")
        w.w(f"  Позиционная: critical_moments ≤ {CM_POS} и длина ≥ {LEN_POS} ходов")
        w.w(f"  Тактическая: critical_moments {CM_POS + 1}–{CM_CHAOTIC - 1} и ср. потеря зевка > {TACT_LOSS} CP")
        w.w("  Смешанная:   остальное")
        w.w()

        w.w(f"  {'Тип':<38} {'Партий':<7} {'Win%':<7} {'ACPL':<6} {'Мит':<6} {'Энд':<6} {'Сопер':<6} {'Зев/п':<6} {'cm'}")
        w.w("  " + "-" * 95)

        total_n = sum(b["n"] for b in buckets.values())
        for k, label in labels.items():
            d = buckets[k]
            if d["n"] == 0: continue
            score = (d["w"] + 0.5 * d["d"]) / d["n"] * 100
            n = d["n"]
            w.w(f"  {label:<38} {n:<7} {score:<7.1f} {d['acpl']/n:<6.0f} {d['acpl_mid']/n:<6.0f} {d['acpl_end']/n:<6.0f} {d['avg_opp']/n:<6.0f} {d['blunders']/n:<6.1f} {d['cm_sum']/n:<.1f}")

        w.w()
        w.w(f"Всего классифицировано: {total_n}")
        w.w()

        w.w("🎯 ВЕРДИКТ:")
        worst_k = None; worst_score = 999; best_k = None; best_score = -1
        for k, d in buckets.items():
            if d["n"] < 10: continue
            score = (d["w"] + 0.5 * d["d"]) / d["n"] * 100
            if score < worst_score: worst_score = score; worst_k = k
            if score > best_score: best_score = score; best_k = k

        if worst_k and best_k and worst_k != best_k:
            w.w(f"  Хуже всего: {labels[worst_k]} — {worst_score:.0f}% очков.")
            w.w(f"  Лучше всего: {labels[best_k]} — {best_score:.0f}%.")
            if worst_k == "chaotic": w.w("  💡 В хаосе ты теряешь контроль. При +1.0 — пауза 2 сек, ищи размен.")
            elif worst_k == "tactical": w.w("  💡 В тактических позициях много зевков. Тренируй тактику.")
            elif worst_k == "positional": w.w("  💡 В позиционных ты скучаешь. Держи план: цель → средство.")
            else: w.w("  💡 Смешанные партии — самая большая группа. Работай над универсальностью.")
    conn.close()