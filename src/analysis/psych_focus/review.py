# ============================================================
# analysis/psych_focus/review.py (v25.0)
# §D2: детерминированный порядок разбора (sorted вместо set→list).
# ============================================================
import os
import json
from .common import _conn, REPORTS_DIR, PLAYER

REVIEWS_DIR = os.path.join(REPORTS_DIR, "reviews")
os.makedirs(REVIEWS_DIR, exist_ok=True)


def _phase_of_move(move_num):
    if move_num <= 10:
        return "opening"
    elif move_num <= 30:
        return "middlegame"
    else:
        return "endgame"


def _format_eval(ev):
    if ev is None:
        return "?"
    return f"{ev/100:+.1f}"


def _review_by_url(url):
    conn = _conn(); cur = conn.cursor()
    cur.execute("""
        SELECT white, black, won, draw, reason, eco, opening, my_rating, opp_rating,
               acpl, acpl_opening, acpl_middlegame, acpl_endgame, accuracy, accuracy_opponent,
               game_length, max_eval_advantage, eval_history, end_time
        FROM games WHERE url=?
    """, (url,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return None

    (white, black, won, draw, reason, eco, opening, my_rating, opp_rating,
     acpl, acpl_op, acpl_mid, acpl_end, accuracy, accuracy_opp, game_len,
     max_eval_adv, raw_hist, end_time) = row
    try:
        hist = json.loads(raw_hist) if raw_hist else []
        hist = [(int(a), float(b)) for a, b in hist if a is not None and b is not None]
    except Exception:
        hist = []

    cur.execute("""
        SELECT move_num, move_uci, loss_cp, eval_before, eval_after, what,
               pattern_tag, time_spent, is_my_blunder
        FROM blunders WHERE game_url = ?
    """, (url,))
    blunders = []
    for b in cur.fetchall():
        blunders.append({
            "move_num": b[0], "move": b[1], "loss": b[2], "eval_before": b[3],
            "eval_after": b[4], "what": b[5], "pattern_tag": b[6],
            "time_spent": b[7], "is_my_blunder": bool(b[8]),
        })
    conn.close()
    return {
        "url": url, "white": white, "black": black, "won": won, "draw": draw,
        "reason": reason, "eco": eco, "opening": opening, "my_rating": my_rating,
        "opp_rating": opp_rating, "acpl": acpl, "acpl_op": acpl_op,
        "acpl_mid": acpl_mid, "acpl_end": acpl_end, "accuracy": accuracy,
        "accuracy_opp": accuracy_opp, "game_len": game_len,
        "max_eval_adv": max_eval_adv, "hist": hist, "blunders": blunders,
        "end_time": end_time,
    }


def _review_to_text(g):
    lines = []

    def w(line=""):
        lines.append(line)

    res = "ПОБЕДА" if g["won"] else ("НИЧЬЯ" if g["draw"] else "ПОРАЖЕНИЕ")
    w("=" * 60); w(f" РАЗБОР ПАРТИИ: {g['white']} vs {g['black']}"); w("=" * 60)
    w(f"URL:        {g['url']}")
    w(f"Результат:  {res} ({g['reason']})")
    w(f"Дебют:      {g['eco']} {g['opening']}")
    w(f"Рейтинги:   {g['my_rating']} vs {g['opp_rating']}")
    w("")
    w("📊 ТОЧНОСТЬ:")
    w(f"  ACPL общий:      {g['acpl']:.0f} CP (accuracy {g['accuracy']:.1f}%)")
    w(f"  ACPL миттельшп.: {g['acpl_mid']:.0f} CP")
    w("")

    if g["blunders"]:
        my_blunders = [b for b in g["blunders"] if b["is_my_blunder"]]
        if my_blunders:
            key = max(my_blunders, key=lambda x: x["loss"])
            w("🎯 КЛЮЧЕВОЙ ХОД (макс. потеря):")
            w(f"  Ход {key['move_num']} ({key['move']}): потеря {key['loss']} CP")
            w(f"  До: {_format_eval(key['eval_before'])} → После: {_format_eval(key['eval_after'])}")
            w(f"  Время: {key['time_spent']} сек")
            w(f"  Что:   {key['what']}")
            w("")
            if key["time_spent"] < 1.0:
                w("  ⚠️ Думал < 1 сек — быстрый ход.")
            else:
                w("  ✅ Думал > 1 сек — не спешка, а просчёт.")
            w("")
            phase = _phase_of_move(key["move_num"])
            if phase == "middlegame":
                w("💡 ЧТО ДЕЛАТЬ (миттельшпиль):")
                w("  1. Перед ходом — пауза 0.2 сек, проверь короля.")
                w("  2. Правило Вектора: куда смотрит его последняя фигура?")
            w("")

        top5 = sorted([b for b in g["blunders"] if b["is_my_blunder"]],
                      key=lambda x: x["loss"], reverse=True)[:5]
        if top5:
            w("📉 ТОП-5 ЗЕВКОВ:")
            w(f"  {'Ход':<6} {'Потеря':<8} {'Время':<8} {'Паттерн':<12} {'Что'}")
            for b in top5:
                w(f"  {b['move_num']:<6} {b['loss']:<8} {b['time_spent']:<8} "
                  f"{b['pattern_tag']:<12} {b['what'][:50]}")
            w("")

    return "\n".join(lines)


def report_game_review(url=None, last=3):
    """
    Разбор партий.
    §D2: если url не задан — берём детерминированно:
      - партия с максимальным сливом перевеса
      - партия с максимальным ACPL миттельшпиля
      - партия с максимальным ACPL общим
    Порядок: sorted(set) — не list(set).
    """
    conn = _conn(); cur = conn.cursor()

    if url:
        urls = [url]
    else:
        selected = set()

        # 1. Максимальный слив перевеса
        cur.execute("""
            SELECT url FROM games
            WHERE is_lag=0 AND is_cheater=0
              AND max_eval_advantage >= 300 AND won=0
            ORDER BY max_eval_advantage DESC LIMIT 1
        """)
        for r in cur.fetchall():
            selected.add(r[0])

        # 2. Максимальный ACPL в миттельшпиле
        cur.execute("""
            SELECT url FROM games
            WHERE is_lag=0 AND is_cheater=0 AND acpl_middlegame > 0
            ORDER BY acpl_middlegame DESC LIMIT 1
        """)
        for r in cur.fetchall():
            selected.add(r[0])

        # 3. Максимальный ACPL общий
        cur.execute("""
            SELECT url FROM games
            WHERE is_lag=0 AND is_cheater=0 AND acpl > 0
            ORDER BY acpl DESC LIMIT 1
        """)
        for r in cur.fetchall():
            selected.add(r[0])

        # §D2: детерминированный порядок
        urls = sorted(selected)[:last]

    conn.close()

    if not urls:
        print("⚠️ Нет партий для разбора.")
        return

    for u in urls:
        g = _review_by_url(u)
        if not g:
            continue
        text = _review_to_text(g)
        slug = f"{g['white'][:15]}_vs_{g['black'][:15]}".replace(" ", "_").replace("/", "_")
        path = os.path.join(REVIEWS_DIR, f"review_{slug}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"✅ {path}")


def run_game_review():
    report_game_review(last=3)