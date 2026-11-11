# ============================================================
# analysis/psych_focus/blunder_anatomy.py (v19.1)
# ============================================================
from collections import Counter
from analysis.common import report_context
from .common import _conn

def report_blunder_anatomy():
    conn = _conn(); cur = conn.cursor()
    
    cur.execute("""
        SELECT b.move_num, b.loss_cp, b.time_spent, b.pattern_tag, g.eco, g.acpl
        FROM blunders b JOIN games g ON g.url=b.game_url
        WHERE g.is_lag=0 AND g.is_cheater=0 AND b.is_my_blunder=1 AND b.is_berserk=0 AND b.time_spent IS NOT NULL
    """)
    rows = cur.fetchall()

    with report_context("blunder_anatomy") as w:
        w.w_separator(title="BLUNDER ANATOMY: время на ход перед зевком")
        
        if not rows:
            w.w("⚠️ Нет данных для анализа времени на ход.")
            conn.close(); return

        cats = {
            "panic": {"label": "< 0.5 сек (паника)", "n": 0, "loss": 0, "phases": Counter()},
            "fast": {"label": "0.5 – 1 сек (спешка)", "n": 0, "loss": 0, "phases": Counter()},
            "normal": {"label": "1 – 3 сек (норма)", "n": 0, "loss": 0, "phases": Counter()},
            "thought": {"label": "3 – 10 сек (обдуманно)", "n": 0, "loss": 0, "phases": Counter()},
            "deep": {"label": "> 10 сек (глубоко)", "n": 0, "loss": 0, "phases": Counter()},
        }

        def phase_of(mn):
            if mn <= 10: return "opening"
            if mn <= 30: return "middlegame"
            return "endgame"

        total_n = total_loss = 0
        for move_num, loss, time_spent, pattern, eco, acpl in rows:
            if time_spent is None: continue
            if time_spent < 0.5: k = "panic"
            elif time_spent < 1.0: k = "fast"
            elif time_spent < 3.0: k = "normal"
            elif time_spent < 10.0: k = "thought"
            else: k = "deep"
            
            cats[k]["n"] += 1
            cats[k]["loss"] += loss or 0
            cats[k]["phases"][phase_of(move_num)] += 1
            total_n += 1
            total_loss += loss or 0

        w.w(f"Всего зевков (без берсерка): {total_n}")
        w.w(f"Средняя потеря: {total_loss / total_n:.0f} CP" if total_n else "")
        w.w()

        w.w(f"  {'Категория':<25} {'N':<6} {'%':<7} {'Ср. потеря':<12} {'Фаза (топ)'}")
        w.w("  " + "-" * 70)
        for k in ["panic", "fast", "normal", "thought", "deep"]:
            d = cats[k]
            if d["n"] == 0: continue
            pct = d["n"] / total_n * 100
            avg_loss = d["loss"] / d["n"]
            top_phase = d["phases"].most_common(1)[0] if d["phases"] else ("—", 0)
            w.w(f"  {d['label']:<25} {d['n']:<6} {pct:<7.1f} {avg_loss:<12.0f} {top_phase[0]}")
        w.w()

        w.w("🎯 ВЕРДИКТ:")
        panic_pct = cats["panic"]["n"] / total_n * 100 if total_n else 0
        normal_pct = cats["normal"]["n"] / total_n * 100 if total_n else 0
        thought_pct = (cats["thought"]["n"] + cats["deep"]["n"]) / total_n * 100 if total_n else 0

        if panic_pct > 20:
            w.w(f"  ⚠️ {panic_pct:.0f}% зевков — за < 0.5 сек. Это ПАНИКА.")
            w.w("  💡 Правило «Щит-Клик»: перед каждым ходом — пауза 0.5 сек.")
        if normal_pct > 50:
            w.w(f"  📊 {normal_pct:.0f}% зевков — в норме по времени (1-3 сек).")
            w.w("  💡 Дело не в скорости, а в глубине расчёта. Тренируй тактику.")
        if thought_pct > 50:
            w.w(f"  📊 {thought_pct:.0f}% зевков — после глубокого раздумья (>3 сек).")
            w.w("  💡 Это НЕ спешка, а позиционная слепота.")

    conn.close()

def run_blunder_anatomy():
    report_blunder_anatomy()