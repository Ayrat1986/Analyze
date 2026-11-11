# ============================================================
# analysis/middlegame/win_loss_conversion.py (v19.5)
# ============================================================
import io
import chess
import chess.pgn
from analysis.common import report_context
from .common import _conn, get_base_filter

def _open_game(pgn):
    if not pgn: return None
    try:
        return chess.pgn.read_game(io.StringIO(pgn))
    except Exception:
        return None


def report_win_loss_conversion():
    conn = _conn()
    cur = conn.cursor()
    base = get_base_filter()

    with report_context("win_loss_conversion") as w:
        w.w_separator(title="РЕАЛИЗАЦИЯ ПЕРЕВЕСА")
        w.w()

        # 1. Потери из +3.0
        w.w("📊 1. ПОТЕРИ ИЗ +3.0 (max_eval_advantage >= 300)")
        cur.execute(f"""
            SELECT COUNT(*), SUM(CASE WHEN won=1 THEN 1 ELSE 0 END),
                   SUM(CASE WHEN won=0 AND draw=0 THEN 1 ELSE 0 END),
                   SUM(CASE WHEN draw=1 THEN 1 ELSE 0 END), ROUND(AVG(moves_in_winning_position), 1)
            FROM games WHERE {base} AND max_eval_advantage >= 300
        """)
        total, wins, losses, draws, avg_moves = cur.fetchone()
        total = total or 0; wins = wins or 0; losses = losses or 0; draws = draws or 0; avg_moves = avg_moves or 0

        w.w(f"  Партий с перевесом ≥ +3.0: {total}")
        if total:
            w.w(f"    Реализовано (победа): {wins} ({wins/total*100:.1f}%)")
            w.w(f"    Слито (поражение):    {losses} ({losses/total*100:.1f}%)")
            w.w(f"    Недобрано (ничья):    {draws} ({draws/total*100:.1f}%)")
        w.w(f"  Ср. ходов удержания перевеса: {avg_moves:.1f}")
        w.w()

        # 2. Распределение сливов по ходам
        w.w("📊 2. РАСПРЕДЕЛЕНИЕ СЛИВОВ ПО ХОДАМ (где теряешь перевес):")
        cur.execute(f"""
            SELECT 
                CASE 
                    WHEN game_length <= 30 THEN 'до 30 ходов'
                    WHEN game_length <= 40 THEN '31-40 ходов'
                    WHEN game_length <= 50 THEN '41-50 ходов'
                    WHEN game_length <= 60 THEN '51-60 ходов'
                    ELSE '60+ ходов'
                END AS bucket,
                COUNT(*),
                SUM(CASE WHEN won=0 AND draw=0 THEN 1 ELSE 0 END) AS lost
            FROM games
            WHERE {base} AND max_eval_advantage >= 300
            GROUP BY bucket
        """)
        hour_rows = cur.fetchall()
        order = ['до 30 ходов', '31-40 ходов', '41-50 ходов', '51-60 ходов', '60+ ходов']
        by_bucket = {r[0]: (r[1], r[2]) for r in hour_rows}
        w.w(f"  {'Длина партии':<20} {'Всего':<8} {'Слито':<8} {'% слито'}")
        w.w("  " + "-" * 48)
        for b in order:
            if b in by_bucket:
                n, lost = by_bucket[b]
                pct = lost / n * 100 if n else 0
                w.w(f"  {b:<20} {n:<8} {lost:<8} {pct:.1f}%")
        w.w()
        w.w("  💡 Если сливы концентрируются в '51-60' или '60+', значит проблема в цейтноте.")
        w.w()

        # 3. Правило Бухгалтера (НЕ УНИВЕРСАЛЬНО)
        w.w("📊 3. ПРАВИЛО БУХГАЛТЕРА (размен ферзей после +3.0)")
        cur.execute(f"SELECT url FROM games WHERE {base} AND max_eval_advantage >= 300 AND pgn IS NOT NULL ORDER BY end_time DESC LIMIT 300")
        qt = {"traded": 0, "won_t": 0, "not_traded": 0, "won_nt": 0}
        analyzed = 0

        for (url,) in cur.fetchall():
            cur.execute("SELECT pgn, won FROM games WHERE url=?", (url,))
            row = cur.fetchone()
            if not row: continue
            pgn, won = row
            game = _open_game(pgn)
            if not game: continue

            board = game.board()
            q_on = (len(board.pieces(chess.QUEEN, chess.WHITE)) + len(board.pieces(chess.QUEEN, chess.BLACK)))
            traded = False
            for node in game.mainline():
                board.push(node.move)
                new_q = (len(board.pieces(chess.QUEEN, chess.WHITE)) + len(board.pieces(chess.QUEEN, chess.BLACK)))
                if new_q < q_on:
                    traded = True; break

            if traded:
                qt["traded"] += 1
                if won: qt["won_t"] += 1
            else:
                qt["not_traded"] += 1
                if won: qt["won_nt"] += 1
            analyzed += 1

        if analyzed > 0:
            wr_t = qt["won_t"] / qt["traded"] * 100 if qt["traded"] else 0
            wr_nt = qt["won_nt"] / qt["not_traded"] * 100 if qt["not_traded"] else 0
            w.w(f"  Разменял ферзей: {qt['traded']} партий → win {wr_t:.0f}%")
            w.w(f"  НЕ разменял:     {qt['not_traded']} партий → win {wr_nt:.0f}%")
            w.w(f"  Δ win rate:      {wr_t - wr_nt:+.0f}%")
            w.w()
            w.w("  ⚠️ ВАЖНО: Правило Бухгалтера НЕ УНИВЕРСАЛЬНО.")
            w.w(f"     Размен ферзей {'снижает' if wr_t < wr_nt else 'повышает'} твой винрейт на {abs(wr_t - wr_nt):.0f}%.")
            w.w("     Это значит: не меняй ферзя по шаблону.")
            w.w("     • Если ферзь помогает атаковать — НЕ меняй.")
            w.w("     • Если соперник играет на контригру — меняй фигуры.")
            w.w("     • Если у тебя цейтнот — упрощай (меняй ферзей).")
            w.w("     Правило решает КОНКРЕТНАЯ ПОЗИЦИЯ, а не шаблон.")
        else:
            w.w("  ⚠️ Не удалось проанализировать PGN.")
        w.w()

        # 4. Спасения из -3.0
        w.w("📊 4. СПАСЕНИЯ ИЗ -3.0 (min_eval_advantage <= -300)")
        cur.execute(f"""
            SELECT COUNT(*), SUM(CASE WHEN won=1 THEN 1 ELSE 0 END), SUM(CASE WHEN draw=1 THEN 1 ELSE 0 END)
            FROM games WHERE {base} AND min_eval_advantage <= -300
        """)
        total_cb, wins_cb, draws_cb = cur.fetchone()
        total_cb = total_cb or 0; wins_cb = wins_cb or 0; draws_cb = draws_cb or 0

        w.w(f"  Всего партий: {total_cb}")
        w.w(f"  Побед: {wins_cb} | Ничьих: {draws_cb}")
        save_rate = 0
        if total_cb > 0:
            save_rate = (wins_cb + draws_cb) / total_cb * 100
            w.w(f"  Спасено: {wins_cb + draws_cb} ({save_rate:.1f}%)")
        w.w()

        # 5. Индекс бойца
        w.w("🏅 5. ИНДЕКС БОЙЦА")
        lose_rate = losses / total * 100 if total else 0
        if total_cb > 0 and total > 0:
            fighter_index = save_rate - lose_rate
            w.w(f"  Спасения: {save_rate:.1f}% − Потери: {lose_rate:.1f}% = {fighter_index:+.1f}")
            if fighter_index > 10: w.w("  🔥 Отлично. Ты борешься до конца и редко сливаешь.")
            elif fighter_index < -20: w.w("  ❄️ Плохо. Ты сливаешь больше, чем спасаешь.")
            else: w.w("  ➡️ Средне. Есть куда расти.")
        else:
            w.w("  Недостаточно данных.")
        w.w()

        # 6. Топ-3 спасения
        w.w("📊 6. ТОП-3 ЛУЧШИХ СПАСЕНИЯ (из -5.0 и ниже)")
        cur.execute(f"""
            SELECT white, black, min_eval_advantage, won, draw, url
            FROM games WHERE {base} AND min_eval_advantage <= -500 AND (won=1 OR draw=1)
            ORDER BY min_eval_advantage ASC LIMIT 3
        """)
        top_saves = cur.fetchall()
        for wh, bl, min_ev, won, draw, url in top_saves:
            res = "Победа" if won else "Ничья"
            w.w(f"  {wh[:15]} vs {bl[:15]}: из {min_ev/100:.1f} → {res}")
            w.w(f"    {url}")
        if not top_saves:
            w.w("  Нет данных.")

    conn.close()