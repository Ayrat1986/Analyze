# ============================================================
# analysis/opponents/position_type.py — v20.2 (Стиль из БД)
# ============================================================
import os
import statistics
from collections import defaultdict
from .common import _conn, REPORTS_DIR, PLAYER
from _chess_utils import rating_cat
from core.пороги import get as get_threshold
from analysis.common import RATING_BUCKET_LABELS

def classify_position_type(cm, length, avg_loss):
    CM_CHAOTIC = get_threshold("position_type_chaotic_cm", 15)
    CM_POS = get_threshold("position_type_positional_cm", 4)
    LEN_POS = get_threshold("position_type_positional_min_length", 60)
    TACT_LOSS = get_threshold("position_type_tactical_loss_cp", 250)
    if cm is None or cm == 0: return "unknown"
    if cm >= CM_CHAOTIC: return "chaotic"
    if cm <= CM_POS and length >= LEN_POS: return "positional"
    if (CM_POS + 1) <= cm <= (CM_CHAOTIC - 1) and avg_loss > TACT_LOSS: return "tactical"
    return "mixed"

def report_style_position_type():
    conn = _conn(); path = os.path.join(REPORTS_DIR, "style_position_type.txt")
    cur = conn.cursor()

    cur.execute("SELECT game_url, AVG(loss_cp) FROM blunders WHERE is_my_blunder=1 AND is_berserk=0 AND is_instant=0 GROUP BY game_url")
    avg_loss_by_game = {url: loss for url, loss in cur.fetchall()}

    cur.execute("""
        SELECT url, won, draw, opp_rating, acpl, accuracy, critical_moments, game_length, opp_style
        FROM games WHERE is_lag=0 AND is_cheater=0 AND critical_moments IS NOT NULL AND acpl > 0 AND opp_style IS NOT NULL
    """)
    games = cur.fetchall()
    conn.close()

    stats = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: {"n": 0, "w": 0, "d": 0, "acpls": [], "accs": []})))
    total_games = 0

    for url, won, draw, opp_rating, acpl, accuracy, cm, length, style in games:
        if not style or style == "unknown": continue
        pos_type = classify_position_type(cm, length, avg_loss_by_game.get(url, 0))
        if pos_type == "unknown": continue

        r_cat = rating_cat(opp_rating)
        s = stats[style][pos_type][r_cat]
        s["n"] += 1
        if won: s["w"] += 1
        if draw: s["d"] += 1
        s["acpls"].append(acpl or 0); s["accs"].append(accuracy or 0)
        total_games += 1

    with open(path, "w", encoding="utf-8") as f:
        def w(line=""): print(line); f.write(line + "\n")
        w("=" * 70); w(" 🎭 СТИЛЬ × ТИП ПОЗИЦИИ × РЕЙТИНГ"); w("=" * 70)
        w(f"Всего партий: {total_games}"); w()

        w("📊 СЕКЦИЯ 1: КАКИЕ ТИПЫ ПОЗИЦИЙ СОЗДАЁТ КАЖДЫЙ СТИЛЬ")
        w(f"  {'Стиль':<12} {'Хаос':<14} {'Тактика':<14} {'Позиция':<14} {'Смешанная':<12}")
        w("  " + "-" * 70)
        for style in ["aggressive", "tactical", "positional", "universal"]:
            if style not in stats: continue
            row = f"  {style:<12}"
            n_style = sum(sum(s["n"] for s in stats[style][pt].values()) for pt in stats[style])
            for pos_type in ["chaotic", "tactical", "positional", "mixed"]:
                if pos_type not in stats[style]:
                    row += f" {'0':<14}"
                    continue
                n_sp = sum(s["n"] for s in stats[style][pos_type].values())
                pct = n_sp / n_style * 100 if n_style else 0
                row += f" {pct:>4.0f}% ({n_sp:>3})"
            w(row)
        w()

        w("📊 СЕКЦИЯ 2: ВИНРЕЙТ ПО СТИЛЮ × ТИПУ ПОЗИЦИИ × РЕЙТИНГУ (n >= 5)")
        w()
        rating_labels = RATING_BUCKET_LABELS
        pos_labels = {"chaotic": "🌪️ Хаос", "tactical": "⚔️ Тактика", "positional": "🏛️ Позиция", "mixed": "🎭 Смешан"}

        for style in ["aggressive", "tactical", "positional", "universal"]:
            if style not in stats: continue
            w(f"\n🎯 Стиль: {style.upper()}")
            w(f"  {'Тип':<16} " + " ".join(f"{r:<11}" for r in rating_labels))
            w("  " + "-" * 82)
            for pos_type in ["chaotic", "tactical", "positional", "mixed"]:
                if pos_type not in stats[style]: continue
                row = f"  {pos_labels[pos_type]:<16} "
                has_any = False
                for r_cat in rating_labels:
                    s = stats[style][pos_type].get(r_cat)
                    if not s or s["n"] < 5:
                        row += f"{'—':<11} "
                    else:
                        wr = (s["w"] + 0.5 * s["d"]) / s["n"] * 100
                        row += f"{wr:>4.1f}%({s['n']:>2}) "
                        has_any = True
                if has_any: w(row)

        w()
        w("📊 СЕКЦИЯ 3: ТОЧНОСТЬ И ACPL ПО СТИЛЮ × ТИПУ (n >= 10)")
        w(f"  {'Стиль':<12} {'Тип':<14} {'N':<5} {'Acc':<8} {'ACPL':<8} {'Win%'}")
        w("  " + "-" * 55)
        for style in ["aggressive", "tactical", "positional", "universal"]:
            if style not in stats: continue
            for pos_type in ["chaotic", "tactical", "positional", "mixed"]:
                if pos_type not in stats[style]: continue
                all_accs, all_acpls = [], []
                n_tot = w_tot = d_tot = 0
                for s in stats[style][pos_type].values():
                    all_accs.extend(s["accs"]); all_acpls.extend(s["acpls"])
                    n_tot += s["n"]; w_tot += s["w"]; d_tot += s["d"]
                if n_tot < 10: continue
                avg_acc = statistics.mean(all_accs) if all_accs else 0
                avg_acpl = statistics.mean(all_acpls) if all_acpls else 0
                wr = (w_tot + 0.5 * d_tot) / n_tot * 100
                mark = " ⚠️" if wr < 30 else (" ✅" if wr > 60 else "")
                w(f"  {style:<12} {pos_labels[pos_type]:<14} {n_tot:<5} "
                  f"{avg_acc:>5.1f}%  {avg_acpl:<6.1f} {wr:>5.1f}%{mark}")

        w()
        w("🎯 СЕКЦИЯ 4: ЛУЧШИЕ И ХУДШИЕ КОМБИНАЦИИ (n >= 10)")
        all_combos = []
        for style in stats:
            for pos_type in stats[style]:
                for r_cat in stats[style][pos_type]:
                    s = stats[style][pos_type][r_cat]
                    if s["n"] < 10: continue
                    wr = (s["w"] + 0.5 * s["d"]) / s["n"] * 100
                    avg_acpl = statistics.mean(s["acpls"]) if s["acpls"] else 0
                    all_combos.append({"style": style, "pos": pos_type, "rating": r_cat, "n": s["n"], "wr": wr, "acpl": avg_acpl})
        all_combos.sort(key=lambda x: x["wr"])

        w("\n❌ ХУДШИЕ 10:")
        for c in all_combos[:10]:
            w(f"  {c['style']:<12} {c['pos']:<12} {c['rating']:<12} {c['n']:<5} {c['wr']:>5.1f}%   {c['acpl']:.1f}")
        w("\n✅ ЛУЧШИЕ 10:")
        for c in all_combos[-10:]:
            w(f"  {c['style']:<12} {c['pos']:<12} {c['rating']:<12} {c['n']:<5} {c['wr']:>5.1f}%   {c['acpl']:.1f}")

        w()
        w("🎯 ИТОГОВЫЙ ВЕРДИКТ:")
        if all_combos:
            worst, best = all_combos[0], all_combos[-1]
            w(f"  Хуже всего: {worst['style']} × {worst['pos']} × {worst['rating']} ({worst['wr']:.0f}%, {worst['n']} партий)")
            w(f"  Лучше всего: {best['style']} × {best['pos']} × {best['rating']} ({best['wr']:.0f}%, {best['n']} партий)")
            w()
            w("💡 Как использовать:")
            w("  • Если агрессор создаёт хаос — твоя задача сушить (менять фигуры).")
            w("  • Если позиционщик создаёт позицию — атакуй сам, не жди.")

    print(f"\n✅ {path}")