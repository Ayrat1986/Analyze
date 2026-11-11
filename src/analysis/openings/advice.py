# ============================================================
# analysis/openings/advice.py — Советы и резюме (v19.1)
# generate_advice() + build_summary()
# ============================================================


def generate_advice(r):
    """7-9 советов по метрикам одного дебюта."""
    advice = []

    if r['acpl_mid'] > r['acpl_op'] + 15:
        advice.append("Проблема — переход в миттельшпиль. Учи планы на 10–15 ходу.")

    if r.get('acpl_loss_mid') and r.get('acpl_win_mid'):
        diff = r['acpl_loss_mid'] - r['acpl_win_mid']
        if diff > 20:
            advice.append(
                f"В поражениях миттельшпиль ACPL {r['acpl_loss_mid']:.0f}, "
                f"в победах — {r['acpl_win_mid']:.0f}. Разница — {diff:.0f} CP."
            )

    if r['winrate'] < 45:
        advice.append("Winrate ниже 45%. Проверь линии в этом дебюте.")

    if r['timeout_pct'] > 30:
        advice.append(f"Много просрочек ({r['timeout_pct']:.0f}%). Учи план быстрее.")

    if r.get("vulnerability_window"):
        worst = max(r["vulnerability_window"], key=lambda x: x[1])
        if worst[1] >= 3:
            advice.append(
                f"Окно уязвимости: {worst[0]} ходов ({worst[1]} зевков). "
                "Отработай именно этот переход."
            )

    if r.get("killer_line"):
        line, cnt = r["killer_line"]
        if cnt >= 3:
            advice.append(f"Линия-убийца: {line[:50]} ({cnt} зевков). Учи её заново.")

    if r.get("point_of_no_return"):
        move_num, blunders, loss_rate = r["point_of_no_return"][0]
        if loss_rate > 70:
            advice.append(
                f"Точка невозврата: после {move_num}-го хода ты проигрываешь "
                f"{loss_rate:.0f}% ({blunders} зевков). Остановись и упрощай."
            )

    if r.get("sliv_lines"):
        line, total_l, lost = r["sliv_lines"][0]
        pct = lost / total_l * 100 if total_l else 0
        if pct > 50:
            advice.append(
                f"Линия со сливом +3.0: {line[:40]} ({pct:.0f}% слито). "
                "Убери из репертуара."
            )

    if r.get("dominance"):
        w_agg = r["dominance"].get("Белые", 0)
        b_agg = r["dominance"].get("Чёрные", 0)
        if w_agg and b_agg and abs(w_agg - b_agg) > 2:
            worse = "чёрными" if w_agg > b_agg else "белыми"
            advice.append(
                f"Агрессия: белые {w_agg:.1f}, чёрные {b_agg:.1f}. Ты пассивен {worse}."
            )

    if r.get("by_color") and len(r["by_color"]) == 2:
        colors = {c[0]: c for c in r["by_color"]}
        if "Белые" in colors and "Чёрные" in colors:
            w_wr = colors["Белые"][2] / colors["Белые"][1] * 100 if colors["Белые"][1] else 0
            b_wr = colors["Чёрные"][2] / colors["Чёрные"][1] * 100 if colors["Чёрные"][1] else 0
            if abs(w_wr - b_wr) > 15:
                worse = "чёрными" if w_wr > b_wr else "белыми"
                advice.append(
                    f"За белых {w_wr:.0f}%, за чёрных {b_wr:.0f}%. Проблема — игра {worse}."
                )

    for rng, cnt, wins, acpl in r.get("by_rating", []):
        if rng in ("2600-2700", "2700+") and cnt >= 3:
            wr = wins / cnt * 100
            if wr < 40:
                advice.append(f"Против {rng} winrate {wr:.0f}%. Проблема — игра против сильных.")

    return advice


def build_summary(results):
    """📋 РЕЗЮМЕ ПО ВСЕМ ДЕБЮТАМ (в конце файла)."""
    lines = []
    lines.append("\n" + "=" * 60)
    lines.append(" 📋 РЕЗЮМЕ ПО ВСЕМ ДЕБЮТАМ")
    lines.append("=" * 60)

    best = sorted(results, key=lambda x: -x["winrate"])[:3]
    lines.append("\n✅ ТОП-3 ЛУЧШИХ:")
    for r in best:
        lines.append(f"   {r['eco']}: {r['winrate']:.1f}% ({r['total']} партий)")

    worst = sorted(results, key=lambda x: x["winrate"])[:3]
    lines.append("\n❌ ТОП-3 ХУДШИХ:")
    for r in worst:
        lines.append(f"   {r['eco']}: {r['winrate']:.1f}% ({r['total']} партий)")

    sliv_sorted = [r for r in results if r.get("sliv") and r["sliv"][0] >= 5]
    sliv_sorted.sort(key=lambda x: -(x["sliv"][1] or 0) / x["sliv"][0])
    lines.append("\n💸 ТОП-3 ПО СЛИВУ +3.0:")
    for r in sliv_sorted[:3]:
        pct = (r["sliv"][1] or 0) / r["sliv"][0] * 100
        lines.append(f"   {r['eco']}: {pct:.0f}% слито ({r['sliv'][1]}/{r['sliv'][0]})")

    growing = []
    falling = []
    for r in results:
        weekly = r.get("weekly", [])
        if len(weekly) >= 3:
            first_wr = weekly[0][2] / weekly[0][1] * 100 if weekly[0][1] else 0
            last_wr = weekly[-1][2] / weekly[-1][1] * 100 if weekly[-1][1] else 0
            if last_wr - first_wr > 5:
                growing.append((r["eco"], first_wr, last_wr))
            elif last_wr - first_wr < -5:
                falling.append((r["eco"], first_wr, last_wr))

    lines.append("\n📈 РАСТУЩИЕ:")
    for eco, f, l in growing[:5]:
        lines.append(f"   {eco}: {f:.0f}% → {l:.0f}%")

    lines.append("\n📉 ПАДАЮЩИЕ:")
    for eco, f, l in falling[:5]:
        lines.append(f"   {eco}: {f:.0f}% → {l:.0f}%")

    lines.append("\n🎯 РЕКОМЕНДАЦИЯ:")
    if best:
        lines.append(f"   Играй: {', '.join(r['eco'] for r in best)}")
    if worst:
        lines.append(f"   Учи: {', '.join(r['eco'] for r in worst)}")

    lines.append("\n" + "=" * 60)
    return "\n".join(lines)