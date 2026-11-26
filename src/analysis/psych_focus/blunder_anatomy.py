# ============================================================
# analysis/psych_focus/blunder_anatomy.py (v26.3)
# FIX: Полная очистка, корректный контекст, поддержка новых матов.
# ============================================================
import os
import sqlite3
from collections import Counter
from datetime import datetime
import _common
from analysis.common import report_context

DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")
REPORTS_DIR = str(_common.REPORTS_DIR)


def report_blunder_anatomy():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    with report_context("blunder_anatomy") as w:
        w.w_separator(title="BLUNDER ANATOMY: время на ход и кластеризация ошибок")
        
        # 1. Загружаем данные
        cur.execute("""
            WITH ranked_blunders AS (
                SELECT b.game_url, b.move_num, b.loss_cp, b.time_spent, b.pattern_tag,
                       LAG(b.move_num) OVER (PARTITION BY b.game_url ORDER BY b.move_num) as prev_move,
                       LAG(b.loss_cp) OVER (PARTITION BY b.game_url ORDER BY b.move_num) as prev_loss
                FROM blunders b 
                JOIN games g ON g.url=b.game_url
                WHERE g.is_lag=0 AND g.is_cheater=0 
                  AND b.is_my_blunder=1 AND b.is_berserk=0 
                  AND b.time_spent IS NOT NULL
            )
            SELECT game_url, move_num, loss_cp, time_spent, pattern_tag, prev_move, prev_loss
            FROM ranked_blunders
        """)
        rows = cur.fetchall()

        if not rows:
            w.w("⚠️ Нет данных для анализа времени на ход.")
            conn.close()
            return

        cats = {
            "panic": {"label": "< 0.5 сек (паника)", "n": 0, "loss": 0, "phases": Counter()},
            "fast": {"label": "0.5 – 1 сек (спешка)", "n": 0, "loss": 0, "phases": Counter()},
            "normal": {"label": "1 – 3 сек (норма)", "n": 0, "loss": 0, "phases": Counter()},
            "thought": {"label": "3 – 10 сек (обдуманно)", "n": 0, "loss": 0, "phases": Counter()},
            "deep": {"label": "> 10 сек (глубоко)", "n": 0, "loss": 0, "phases": Counter()},
        }
        
        clusters = {
            "A":  {"label": "A: Мисклик / Срыв премува (<0.35с)", "n": 0, "loss": 0},
            "C":  {"label": "C: Каскадный тильт (паника после ошибки)", "n": 0, "loss": 0},
            "D1": {"label": "D1: Импульсивный ход (интуитивная слепота, 0.35-1с)", "n": 0, "loss": 0},
            "B":  {"label": "B: Тактический расчёт (сбой чеклиста, 1-4с)", "n": 0, "loss": 0},
            "D2": {"label": "D2: Зависание / Перегруз тайм-банка (>4с)", "n": 0, "loss": 0},
            "E":  {"label": "E: Прочее", "n": 0, "loss": 0},
        }

        def phase_of(mn):
            if mn <= 10: return "opening"
            if mn <= 30: return "middlegame"
            return "endgame"

        total_n = total_loss = 0
        for url, move_num, loss, time_spent, pattern, prev_move, prev_loss in rows:
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

            is_after_blunder = (prev_move is not None and (move_num - prev_move) <= 5 and prev_loss and prev_loss > 150)
            
            if time_spent < 0.35 and loss >= 300:
                cat = "A"
            elif is_after_blunder and time_spent < 1.0:
                cat = "C"
            elif 0.35 <= time_spent < 1.0:
                cat = "D1"
            elif 1.0 <= time_spent <= 4.0:
                cat = "B"
            elif time_spent > 4.0:
                cat = "D2"
            else:
                cat = "E"
                
            clusters[cat]["n"] += 1
            clusters[cat]["loss"] += loss or 0

        w.w(f"Всего зевков (без берсерка): {total_n}")
        if total_n > 0:
            w.w(f"Средняя потеря: {total_loss / total_n:.0f} CP")
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

        w.w("🎯 КЛАСТЕРИЗАЦИЯ ОШИБОК (A/B/C/D1/D2):")
        w.w(f"  {'Тип ошибки':<50} {'N':<6} {'%':<7} {'Ср.потеря'}")
        w.w("  " + "-" * 70)
        for k in ["A", "C", "D1", "B", "D2", "E"]:
            d = clusters[k]
            if d["n"] == 0: continue
            pct = d["n"] / total_n * 100
            avg_loss = d["loss"] / d["n"]
            w.w(f"  {d['label']:<50} {d['n']:<6} {pct:<7.1f} {avg_loss:<.0f}")
        w.w()

        w.w("🎯 ВЕРДИКТ:")
        if total_n == 0:
            w.w("  ⚠️ Нет данных.")
        else:
            sorted_clusters = sorted([(k, v) for k, v in clusters.items() if v["n"] > 0], key=lambda x: x[1]["n"], reverse=True)
            top_key, top_data = sorted_clusters[0]
            top_pct = top_data["n"] / total_n * 100

            if top_key == "D1":
                w.w(f"  ⚠️ Главный враг — ИМПУЛЬСИВНЫЙ ХОД ({top_pct:.0f}%).")
                w.w("  💡 Ты делаешь визуально логичный ход без чеклиста. Делай микропаузу 0.2 сек: 'Есть ли шах?'")
            elif top_key == "B":
                w.w(f"  ⚠️ Главный враг — СБОЙ ЧЕКЛИСТА ({top_pct:.0f}%).")
                w.w("  💡 Ты думаешь 1-4 сек, но не проверяешь вилки. Сканируй поля для коневых вилок.")
            elif top_key == "C":
                w.w(f"  ⚠️ Главный враг — КАСКАДНЫЙ ТИЛЬТ ({top_pct:.0f}%).")
                w.w("  💡 После первого зевка — стоп 3 секунды. Ошибся — забудь.")
            elif top_key == "D2":
                w.w(f"  ⚠️ Главный враг — ЗАВИСАНИЕ ({top_pct:.0f}%).")
                w.w("  💡 Ты думаешь >4 сек и все равно ошибаешься. Играй достаточно сильный ход за 0.5 сек.")
            elif top_key == "A":
                w.w(f"  ⚠️ Главный враг — СРЫВ ПРЕМУВА ({top_pct:.0f}%).")
                w.w("  💡 Контролируй палец. Премувы только на 1-4 горизонталях.")
        w.w()

        # 2. Общая статистика по паттернам (включая маты)
        cur.execute("""
            SELECT COUNT(*), ROUND(AVG(loss_cp), 1)
            FROM blunders b JOIN games g ON g.url = b.game_url
            WHERE g.is_lag=0 AND g.is_cheater=0 
              AND b.is_my_blunder=1 AND b.is_berserk=0
        """)
        total_glob, avg_loss_glob = cur.fetchone()
        total_glob = total_glob or 0
        avg_loss_glob = avg_loss_glob or 0
        
        w.w_separator(title="РАСПРЕДЕЛЕНИЕ ПО ПАТТЕРНАМ (Глобально)")
        w.w(f" Всего зевков: {total_glob}")
        w.w(f" Средняя потеря: {avg_loss_glob:.0f} CP")
        w.w()

        cur.execute("""
            SELECT pattern_tag, COUNT(*), ROUND(AVG(loss_cp), 1)
            FROM blunders b JOIN games g ON g.url = b.game_url
            WHERE g.is_lag=0 AND g.is_cheater=0 
              AND b.is_my_blunder=1 AND b.is_berserk=0
            GROUP BY pattern_tag
            ORDER BY COUNT(*) DESC
        """)
        for tag, cnt, avg in cur.fetchall():
            tag_name = tag or "unknown"
            if tag_name == "missed_own_mate": tag_name = "Упущен свой мат"
            elif tag_name == "allowed_opponent_mate": tag_name = "Допущен мат соперника"
            elif tag_name == "lost_piece": tag_name = "Потеря фигуры"
            elif tag_name == "lost_queen": tag_name = "Потеря ферзя"
            elif tag_name == "positional": tag_name = "Позиционная ошибка"
            elif tag_name == "blunder": tag_name = "Общий зевок"

            pct = (cnt / total_glob * 100) if total_glob else 0
            w.w(f"  {tag_name:<25} {cnt:>5} ({pct:>4.1f}%)  Средний урон: {avg:.0f} CP")
        w.w()

    conn.close()


def run_blunder_anatomy():
    report_blunder_anatomy()
