# ============================================================
# analysis/psych_focus/blunder_anatomy.py (v25.1)
# NEW: Кластеризация ошибок A/B/C (Мисклик / Тактика / Каскад).
# ============================================================
from collections import Counter
from analysis.common import report_context
from .common import _conn

def report_blunder_anatomy():
    conn = _conn(); cur = conn.cursor()
    
    # Достаем зевки вместе с предыдущим ходом (для поиска каскадов)
    cur.execute("""
        WITH ranked_blunders AS (
            SELECT b.game_url, b.move_num, b.loss_cp, b.time_spent, b.pattern_tag,
                   g.eco, g.acpl,
                   LAG(b.move_num) OVER (PARTITION BY b.game_url ORDER BY b.move_num) as prev_move,
                   LAG(b.loss_cp) OVER (PARTITION BY b.game_url ORDER BY b.move_num) as prev_loss
            FROM blunders b 
            JOIN games g ON g.url=b.game_url
            WHERE g.is_lag=0 AND g.is_cheater=0 
              AND b.is_my_blunder=1 AND b.is_berserk=0 
              AND b.time_spent IS NOT NULL
        )
        SELECT game_url, move_num, loss_cp, time_spent, pattern_tag, eco, acpl, prev_move, prev_loss
        FROM ranked_blunders
    """)
    rows = cur.fetchall()

    with report_context("blunder_anatomy") as w:
        w.w_separator(title="BLUNDER ANATOMY: время на ход и кластеризация ошибок")
        
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
        
        # НОВЫЕ КАТЕГОРИИ (A/B/C)
        clusters = {
            "A_misclick": {"label": "A: Мисклик/Премув (<0.3с, потеря >300)", "n": 0, "loss": 0},
            "B_tactic": {"label": "B: Тактическая слепота (1-5с, не каскад)", "n": 0, "loss": 0},
            "C_cascade": {"label": "C: Психологический обвал (Паника после зевка)", "n": 0, "loss": 0},
            "D_other": {"label": "D: Прочее (позиционный провал и т.д.)", "n": 0, "loss": 0},
        }

        def phase_of(mn):
            if mn <= 10: return "opening"
            if mn <= 30: return "middlegame"
            return "endgame"

        total_n = total_loss = 0
        for url, move_num, loss, time_spent, pattern, eco, acpl, prev_move, prev_loss in rows:
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

            # --- КЛАСТЕРИЗАЦИЯ A/B/C ---
            is_cascade = (prev_move is not None and (move_num - prev_move) <= 5 and prev_loss and prev_loss > 150)
            
            if time_spent < 0.3 and loss > 300:
                clusters["A_misclick"]["n"] += 1
                clusters["A_misclick"]["loss"] += loss
            elif is_cascade and time_spent < 1.0:
                clusters["C_cascade"]["n"] += 1
                clusters["C_cascade"]["loss"] += loss
            elif 1.0 <= time_spent <= 5.0 and not is_cascade:
                clusters["B_tactic"]["n"] += 1
                clusters["B_tactic"]["loss"] += loss
            else:
                clusters["D_other"]["n"] += 1
                clusters["D_other"]["loss"] += loss

        w.w(f"Всего зевков (без берсерка): {total_n}")
        w.w(f"Средняя потеря: {total_loss / total_n:.0f} CP" if total_n else "")
        w.w()

        w.w(f"  {'Категория времени':<25} {'N':<6} {'%':<7} {'Ср. потеря':<12} {'Фаза (топ)'}")
        w.w("  " + "-" * 70)
        for k in ["panic", "fast", "normal", "thought", "deep"]:
            d = cats[k]
            if d["n"] == 0: continue
            pct = d["n"] / total_n * 100
            avg_loss = d["loss"] / d["n"]
            top_phase = d["phases"].most_common(1)[0] if d["phases"] else ("—", 0)
            w.w(f"  {d['label']:<25} {d['n']:<6} {pct:<7.1f} {avg_loss:<12.0f} {top_phase[0]}")
        w.w()

        w.w("🎯 КЛАСТЕРИЗАЦИЯ ОШИБОК (A/B/C):")
        w.w(f"  {'Тип ошибки':<50} {'N':<6} {'%':<7} {'Ср.потеря'}")
        w.w("  " + "-" * 70)
        for k, d in clusters.items():
            if d["n"] == 0: continue
            pct = d["n"] / total_n * 100
            avg_loss = d["loss"] / d["n"]
            w.w(f"  {d['label']:<50} {d['n']:<6} {pct:<7.1f} {avg_loss:<.0f}")
        w.w()

        w.w("🎯 ВЕРДИКТ:")
        if total_n == 0:
            w.w("  ⚠️ Нет данных.")
            conn.close(); return

        # Анализ самого частого паттерна
        top_cluster = max(clusters.items(), key=lambda x: x[1]["n"])
        top_name = top_cluster[0]
        top_pct = top_cluster[1]["n"] / total_n * 100

        if top_name == "C_cascade":
            w.w(f"  ⚠️ Твой главный враг — КАСКАДНЫЙ ТИЛЬТ ({top_pct:.0f}% зевков).")
            w.w("  💡 Правило «3 секунды»: после зевка замри, выдохни и посмотри на часы.")
        elif top_name == "B_tactic":
            w.w(f"  ⚠️ Твой главный враг — ТАКТИЧЕСКАЯ СЛЕПОТА ({top_pct:.0f}% зевков).")
            w.w("  💡 Дело не в скорости, а в глубине. Тренируй вилки (fork_heavy) в 11_Trainer.")
        elif top_name == "A_misclick":
            w.w(f"  ⚠️ Твой главный враг — МИСКЛИКИ ({top_pct:.0f}% зевков).")
            w.w("  💡 Замедлись на 0.1 сек. Это не потеря времени, это спасение фигуры.")
        else:
            w.w(f"  ⚠️ Преобладают прочие ошибки ({top_pct:.0f}%).")
            w.w("  💡 Скорее всего, это позиционные провалы. Играй проще.")

        # Если есть паника, но нет каскада (просто разогнался)
        if cats["panic"]["n"] / total_n > 0.2:
            w.w(f"  ⚠️ {cats['panic']['n']/total_n*100:.0f}% зевков — за < 0.5 сек. Это ПАНИКА.")
            w.w("  💡 Правило «Щит-Клик»: перед каждым ходом — пауза 0.5 сек.")
            
        if cats["normal"]["n"] / total_n > 0.5:
            w.w(f"  📊 {cats['normal']['n']/total_n*100:.0f}% зевков — в норме по времени (1-3 сек).")
            w.w("  💡 Это тактическая слепота. Тренируй вилки.")

    conn.close()

def run_blunder_anatomy():
    report_blunder_anatomy()