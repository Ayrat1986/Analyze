# ============================================================
# 07_endgame.py — ЭНДШПИЛЬ + БЕРСЕРК
# ============================================================
import sqlite3
import os
import io
import json
from collections import defaultdict
from datetime import datetime

import _common

try:
    import chess
    import chess.pgn
    HAVE_CHESS = True
except ImportError:
    HAVE_CHESS = False
    print("⚠️ python-chess не установлен — часть отчётов будет пропущена.")

DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")
REPORTS_DIR = str(_common.REPORTS_DIR)
TRAINING_DIR = os.path.join(REPORTS_DIR, "training")
PLAYER = _common.CONFIG.get("player", "")

os.makedirs(REPORTS_DIR, exist_ok=True)
os.makedirs(TRAINING_DIR, exist_ok=True)


def _conn():
    return sqlite3.connect(DB_FILE)


def _is_player_white(white: str) -> bool:
    return (white or "").lower() == PLAYER.lower()


def _load_clocks_evals(url, clocks_raw, evals_raw):
    try:
        clocks = json.loads(clocks_raw) if clocks_raw else []
        evals = json.loads(evals_raw) if evals_raw else []
        return clocks, evals
    except Exception:
        return [], []


# ============================================================
# 1. ENDGAME SKILLS — техника эндшпиля
# ============================================================
def report_endgame_skills():
    conn = _conn(); cur = conn.cursor()
    path = os.path.join(REPORTS_DIR, "endgame_skills.txt")
    with open(path, "w", encoding="utf-8") as f:
        def w(line=""):
            print(line); f.write(line + "\n")
        w("=" * 60); w(" ЭНДШПИЛЬНАЯ ТЕХНИКА"); w("=" * 60); w()

        # --- Секция 1: общая точность в эндшпиле ---
        cur.execute("""
            SELECT
                COUNT(*),
                SUM(CASE WHEN won=1 THEN 1 ELSE 0 END),
                SUM(CASE WHEN won=0 THEN 1 ELSE 0 END),
                ROUND(AVG(acpl_endgame), 1),
                ROUND(AVG(CASE WHEN won=1 THEN acpl_endgame END), 1),
                ROUND(AVG(CASE WHEN won=0 THEN acpl_endgame END), 1)
            FROM games
            WHERE is_lag=0 AND is_cheater=0 AND game_length >= 60 AND acpl_endgame > 0
        """)
        total, wins, losses, avg_all, avg_win, avg_loss = cur.fetchone()
        total = total or 0; wins = wins or 0; losses = losses or 0
        avg_all = avg_all or 0; avg_win = avg_win or 0; avg_loss = avg_loss or 0
        w(f"Партий с длиной ≥ 60 ходов: {total}")
        w(f"  Побед: {wins} | Поражений: {losses}")
        w(f"  ACPL эндшпиля (все):       {avg_all:.0f} CP")
        w(f"  ACPL эндшпиля (победы):    {avg_win:.0f} CP")
        w(f"  ACPL эндшпиля (поражения): {avg_loss:.0f} CP")
        if avg_win > 0:
            w(f"  ⚠️ Разница win/loss:       {avg_loss - avg_win:+.0f} CP")
        w()

        # --- Секция 2: слив в эндшпиле ---
        cur.execute("""
            SELECT COUNT(*) FROM games
            WHERE is_lag=0 AND is_cheater=0
              AND game_length >= 60 AND eval_final > 0 AND won=0
        """)
        sliv = cur.fetchone()[0] or 0
        cur.execute("""
            SELECT COUNT(*) FROM games
            WHERE is_lag=0 AND is_cheater=0
              AND game_length >= 60 AND eval_final > 0
        """)
        total_finish = cur.fetchone()[0] or 0
        if total_finish > 0:
            w("📊 СЛИТЫЕ В ЭНДШПИЛЕ:")
            w(f"  Всего с eval_final > 0: {total_finish}")
            w(f"  Из них проиграно:      {sliv} ({sliv/total_finish*100:.1f}%)")
            w()

        # --- Секция 3: паттерны зевков в эндшпиле ---
        cur.execute("""
            SELECT b.pattern_tag, COUNT(*), ROUND(AVG(b.loss_cp))
            FROM blunders b JOIN games g ON g.url=b.game_url
            WHERE g.is_lag=0 AND g.is_cheater=0
              AND b.is_berserk=0 AND b.is_instant=0 AND b.is_my_blunder=1
              AND b.move_num > 30
            GROUP BY b.pattern_tag ORDER BY COUNT(*) DESC
        """)
        pats = cur.fetchall()
        if pats:
            w("📊 ПАТТЕРНЫ ЗЕВКОВ В ЭНДШПИЛЕ:")
            tot = sum(p[1] for p in pats)
            for tag, cnt, avg_loss in pats[:10]:
                w(f"  {tag:<25} {cnt:>4} ({cnt/tot*100:.1f}%) ср. {avg_loss:.0f} CP")
            w()

        # --- Секция 4: время на зевок в эндшпиле ---
        cur.execute("""
            SELECT
                ROUND(AVG(CASE WHEN won=1 AND time_spent > 0 THEN time_spent END), 2),
                ROUND(AVG(CASE WHEN won=0 AND time_spent > 0 THEN time_spent END), 2)
            FROM blunders b JOIN games g ON g.url=b.game_url
            WHERE b.move_num > 30 AND b.is_my_blunder=1
              AND g.is_lag=0 AND g.is_cheater=0
        """)
        tw, tl = cur.fetchone()
        tw = tw or 0; tl = tl or 0
        if tw or tl:
            w("📊 ВРЕМЯ НА ЗЕВОК В ЭНДШПИЛЕ:")
            w(f"  В победах (когда зевнул):    {tw:.2f} сек")
            w(f"  В поражениях (когда зевнул): {tl:.2f} сек")
            w()

        # --- Секция 5: топ-5 худших эндшпилей ---
        w("📊 ТОП-5 ХУДШИХ ПАРТИЙ ПО ЭНДШПИЛЮ:")
        cur.execute("""
            SELECT white, black, won, acpl_endgame, url
            FROM games
            WHERE is_lag=0 AND is_cheater=0 AND game_length >= 60 AND acpl_endgame > 0
            ORDER BY acpl_endgame DESC LIMIT 5
        """)
        for wh, bl, won, acpl_e, url in cur.fetchall():
            res = "победа" if won else "поражение"
            w(f"  {wh[:15]:<17} vs {bl[:15]:<17} | ACPL {acpl_e:.0f} | {res}")
        w()

        # --- НОВЫЙ БЛОК: разбивка по reason ---
        w("\n📊 ACPL ЭНДШПИЛЯ В ПОБЕДАХ (разбивка по окончанию):")
        cur.execute("""
            SELECT reason, COUNT(*) as n, AVG(acpl_endgame) as avg_acpl
            FROM games
            WHERE is_lag=0 AND is_cheater=0 AND won=1 AND acpl_endgame IS NOT NULL
            GROUP BY reason
            ORDER BY n DESC
        """)
        rows = cur.fetchall()

        if rows:
            total_acpl_sum = 0
            total_n = 0
            flag_acpl = None
            flag_n = 0

            for reason, n, avg_acpl in rows:
                if avg_acpl is None: continue
                total_acpl_sum += avg_acpl * n
                total_n += n

                if 'просроч' in str(reason).lower() or 'time' in str(reason).lower():
                    flag_acpl = avg_acpl
                    flag_n = n
                    w(f"  • 🚩 {reason:<15} : {n:>4} партий, ACPL {avg_acpl:.1f}  ← стратегия флага")
                else:
                    w(f"  •    {reason:<15} : {n:>4} партий, ACPL {avg_acpl:.1f}")

            if total_n > 0:
                w(f"  ➡️ Средний ACPL в победах (все): {total_acpl_sum / total_n:.1f}")

            if flag_acpl and total_n > 0 and (total_n - flag_n) > 0:
                # ИСПРАВЛЕНО: правильная формула вычисления среднего без учета флагов
                non_flag_sum = total_acpl_sum - (flag_acpl * flag_n)
                non_flag_n = total_n - flag_n
                real_acpl = non_flag_sum / non_flag_n
                
                w(f"\n🎯 ВЕРДИКТ:")
                w(f"  ⚠️ {flag_n} побед по флагу имеют ACPL эндшпиля {flag_acpl:.1f}.")
                w(f"  ✅ Это НЕ ошибка техники. В победах по мату/сдаче ACPL значительно ниже.")
                w(f"  ✅ Твой реальный ACPL эндшпиля в победах без флага — {real_acpl:.1f}.")
                w(f"  🎯 Рекомендация: не тренируй мат ладьёй на флаговых победах — ты их и так выиграл.")
        w()

        # --- Вердикт (твой старый) ---
        w("🎯 ВЕРДИКТ:")
        if avg_all > 70:
            w(f"  ⚠️ ACPL эндшпиля {avg_all:.0f} — плохо. Тренируй технику.")
        elif avg_all > 60:
            w(f"  ➡️ ACPL эндшпиля {avg_all:.0f} — средне. Есть куда расти.")
        else:
            w(f"  ✅ ACPL эндшпиля {avg_all:.0f} — хорошо.")
        if total_finish and sliv / total_finish > 0.3:
            w(f"  ⚠️ Сливаешь {sliv/total_finish*100:.0f}% выигранных эндшпилей — правило Бухгалтера.")

    conn.close(); print(f"\n✅ {path}")


# ============================================================
# 2. ENDGAME TRAINER — FEN-позиции для тренировки
# ============================================================
def report_endgame_trainer():
    if not HAVE_CHESS:
        print("⚠️ endgame_trainer пропущен: нет python-chess")
        return
    conn = _conn(); cur = conn.cursor()

    cur.execute("""
        SELECT url, white, black, won, eval_final, pgn, acpl_endgame
        FROM games
        WHERE is_lag=0 AND is_cheater=0
          AND game_length >= 30
          AND acpl_endgame > 50
          AND pgn IS NOT NULL AND pgn != ''
          AND (reason NOT LIKE '%просроч%' AND reason NOT LIKE '%time%')
        ORDER BY acpl_endgame DESC
        LIMIT 50
    """)
    rows = cur.fetchall()

    positions = []
    for url, white, black, won, eval_final, pgn, acpl_endgame in rows:
        try:
            game = chess.pgn.read_game(io.StringIO(pgn))
            if not game:
                continue
        except Exception:
            continue

        board = game.board()
        move_num = 0
        for node in game.mainline():
            board.push(node.move)
            move_num += 1
            if move_num == 60:
                positions.append({
                    "url": url,
                    "move_num": move_num,
                    "fen": board.fen(),
                    "white": white,
                    "black": black,
                    "won": won,
                    "acpl_endgame": acpl_endgame,
                })
                break

    # CSV с позициями
    csv_path = os.path.join(TRAINING_DIR, "endgame_positions.csv")
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("url,fen,acpl_endgame\n")
        for p in positions:
            f.write(f"{p['url']},{p['fen']},{p['acpl_endgame']}\n")
    print(f"✅ {csv_path}")

    # TXT с описанием
    txt_path = os.path.join(REPORTS_DIR, "endgame_trainer.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        def w(line=""):
            print(line); f.write(line + "\n")
        w("=" * 60); w(" 🛡️ ТРЕНАЖЕР ЭНДШПИЛЯ"); w("=" * 60); w()
        w(f"Найдено позиций: {len(positions)}")
        w("Загрузи FEN в Lichess Analysis и тренируй технику.")
        w()
        for i, p in enumerate(positions[:20], 1):
            w(f"#{i}. {p['white']} vs {p['black']} (ACPL эндшпиля: {p['acpl_endgame']:.0f})")
            w(f"    FEN: {p['fen']}")
            w()

    # Готовые ссылки на Lichess
    links_path = os.path.join(TRAINING_DIR, "endgame_lichess_links.txt")
    with open(links_path, "w", encoding="utf-8") as f:
        for p in positions[:20]:
            fen_encoded = p["fen"].replace(" ", "_")
            f.write(f"https://lichess.org/analysis/standard/{fen_encoded}\n")
    print(f"✅ {links_path}")
    conn.close(); print(f"\n✅ {txt_path}")


# ============================================================
# 3. BERSERK ZONE — матрица время × рейтинг
# ============================================================
def report_berserk_zone():
    conn = _conn(); cur = conn.cursor()
    path = os.path.join(REPORTS_DIR, "berserk_zone.txt")

    cur.execute("""
        SELECT url, white, black, won, draw, reason, clocks, end_berserk, opp_rating
        FROM games
        WHERE is_cheater=0 AND is_lag=0
          AND clocks IS NOT NULL AND clocks != '[]'
    """)
    games = cur.fetchall()

    rating_labels = ["< 2500", "2500-2599", "2600-2699", "2700+"]

    # Порог 10 секунд
    time_labels_10 = ["rich_10", "poor_10", "both_low_10"]
    time_names_10 = {
        "rich_10": "У меня >10, у сопер. <10",
        "poor_10": "У меня <10, у сопер. >10",
        "both_low_10": "У обоих <10",
    }
    matrix_10 = {t: {r: {"n": 0, "w": 0} for r in rating_labels} for t in time_labels_10}
    stats_by_time_10 = {t: {"n": 0, "w": 0} for t in time_labels_10}
    stats_by_rating_10 = {r: {"n": 0, "w": 0} for r in rating_labels}
    total_zone_10 = 0

    # Порог 5 секунд
    time_labels_5 = ["rich_5", "poor_5", "both_low_5"]
    time_names_5 = {
        "rich_5": "У меня >5, у сопер. <5",
        "poor_5": "У меня <5, у сопер. >5",
        "both_low_5": "У обоих <5",
    }
    matrix_5 = {t: {r: {"n": 0, "w": 0} for r in rating_labels} for t in time_labels_5}
    stats_by_time_5 = {t: {"n": 0, "w": 0} for t in time_labels_5}
    stats_by_rating_5 = {r: {"n": 0, "w": 0} for r in rating_labels}
    total_zone_5 = 0

    for row in games:
        url, white, black, won, draw, reason, clocks_raw, end_berserk, opp_rating = row
        try:
            clocks = json.loads(clocks_raw)
        except Exception:
            continue
        if not clocks:
            continue
        player_is_white = _is_player_white(white)
        r = opp_rating or 0
        if r < 2500:
            r_cat = "< 2500"
        elif r < 2600:
            r_cat = "2500-2599"
        elif r < 2700:
            r_cat = "2600-2699"
        else:
            r_cat = "2700+"

        # Порог 10 сек
        for i in range(1, len(clocks)):
            if i % 2 == 0:
                w_time = clocks[i]; b_time = clocks[i-1] if i > 0 else 60.0
            else:
                w_time = clocks[i-1] if i > 0 else 60.0; b_time = clocks[i]
            if w_time < 10.0 or b_time < 10.0:
                my_t = w_time if player_is_white else b_time
                opp_t = b_time if player_is_white else w_time
                if my_t > 10.0 and opp_t < 10.0:
                    t_cat = "rich_10"
                elif my_t < 10.0 and opp_t > 10.0:
                    t_cat = "poor_10"
                else:
                    t_cat = "both_low_10"
                matrix_10[t_cat][r_cat]["n"] += 1
                if won: matrix_10[t_cat][r_cat]["w"] += 1
                stats_by_time_10[t_cat]["n"] += 1
                stats_by_rating_10[r_cat]["n"] += 1
                if won:
                    stats_by_time_10[t_cat]["w"] += 1
                    stats_by_rating_10[r_cat]["w"] += 1
                total_zone_10 += 1
                break

        # Порог 5 сек
        for i in range(1, len(clocks)):
            if i % 2 == 0:
                w_time = clocks[i]; b_time = clocks[i-1] if i > 0 else 60.0
            else:
                w_time = clocks[i-1] if i > 0 else 60.0; b_time = clocks[i]
            if w_time < 5.0 or b_time < 5.0:
                my_t = w_time if player_is_white else b_time
                opp_t = b_time if player_is_white else w_time
                if my_t > 5.0 and opp_t < 5.0:
                    t_cat = "rich_5"
                elif my_t < 5.0 and opp_t > 5.0:
                    t_cat = "poor_5"
                else:
                    t_cat = "both_low_5"
                matrix_5[t_cat][r_cat]["n"] += 1
                if won: matrix_5[t_cat][r_cat]["w"] += 1
                stats_by_time_5[t_cat]["n"] += 1
                stats_by_rating_5[r_cat]["n"] += 1
                if won:
                    stats_by_time_5[t_cat]["w"] += 1
                    stats_by_rating_5[r_cat]["w"] += 1
                total_zone_5 += 1
                break

    with open(path, "w", encoding="utf-8") as f:
        f.write("=" * 60 + "\n ЗОНА БЕРСЕРКА\n" + "=" * 60 + "\n\n")
        f.write(f"📊 [ПОРОГ 10 СЕКУНД] Всего партий: {total_zone_10}\n")
        if total_zone_10 > 0:
            for t in time_labels_10:
                d = stats_by_time_10[t]
                if d["n"] > 0:
                    f.write(f"  {time_names_10[t]}: {d['n']} партий, винрейт {d['w']/d['n']*100:.1f}%\n")
            f.write("\nПО РЕЙТИНГУ:\n")
            for r in rating_labels:
                d = stats_by_rating_10[r]
                if d["n"] > 0:
                    f.write(f"  {r}: {d['n']} партий, винрейт {d['w']/d['n']*100:.1f}%\n")
            f.write("\nКРОСС-ТАБЛИЦА:\n")
            f.write(f"  {'Время':<25} " + " ".join([f"{r:<12}" for r in rating_labels]) + "\n")
            f.write(f"  {'-'*25} " + " ".join([f"{'-'*12}" for _ in rating_labels]) + "\n")
            for t in time_labels_10:
                line = f"  {time_names_10[t]:<25} "
                for r in rating_labels:
                    d = matrix_10[t][r]
                    line += (f"{d['w']/d['n']*100:>5.1f}% ({d['n']:>3}) "
                             if d["n"] > 0 else f"{'—':>12} ")
                f.write(line + "\n")
        f.write("\n\n")

        f.write(f"📊 [ПОРОГ 5 СЕКУНД] Всего партий: {total_zone_5}\n")
        if total_zone_5 > 0:
            for t in time_labels_5:
                d = stats_by_time_5[t]
                if d["n"] > 0:
                    f.write(f"  {time_names_5[t]}: {d['n']} партий, винрейт {d['w']/d['n']*100:.1f}%\n")
            f.write("\nПО РЕЙТИНГУ:\n")
            for r in rating_labels:
                d = stats_by_rating_5[r]
                if d["n"] > 0:
                    f.write(f"  {r}: {d['n']} партий, винрейт {d['w']/d['n']*100:.1f}%\n")
            f.write("\nКРОСС-ТАБЛИЦА:\n")
            f.write(f"  {'Время':<25} " + " ".join([f"{r:<12}" for r in rating_labels]) + "\n")
            f.write(f"  {'-'*25} " + " ".join([f"{'-'*12}" for _ in rating_labels]) + "\n")
            for t in time_labels_5:
                line = f"  {time_names_5[t]:<25} "
                for r in rating_labels:
                    d = matrix_5[t][r]
                    line += (f"{d['w']/d['n']*100:>5.1f}% ({d['n']:>3}) "
                             if d["n"] > 0 else f"{'—':>12} ")
                f.write(line + "\n")

    conn.close(); print(f"\n✅ {path}")


# ============================================================
# 4. MISSED BERSERK — где можно было включить, но не включил
# ============================================================
def report_missed_berserk():
    conn = _conn(); cur = conn.cursor()
    path = os.path.join(REPORTS_DIR, "missed_berserk.txt")

    cur.execute("""
        SELECT url, white, black, won, draw, reason, clocks, eval_history, end_berserk, my_rating
        FROM games
        WHERE is_cheater=0 AND is_lag=0 AND won=0 AND end_berserk=0
    """)
    games = cur.fetchall()

    missed = []
    for row in games:
        url, white, black, won, draw, reason, clocks_raw, evals_raw, end_berserk, my_rating = row
        if reason not in ("просрочка", "отключение"):
            continue
        clocks, hist = _load_clocks_evals(url, clocks_raw, evals_raw)
        if not clocks or not hist:
            continue
        player_is_white = _is_player_white(white)
        trigger_move = None
        trigger_my_time = 0
        trigger_opp_time = 0
        for move, ev in hist:
            clock_idx = ((move - 1) * 2
                         if player_is_white else (move - 1) * 2 + 1)
            if clock_idx >= len(clocks):
                continue
            my_t = clocks[clock_idx]
            opp_t = clocks[clock_idx - 1] if clock_idx > 0 else clocks[0]
            if my_t < 10.0 and ev >= 0 and opp_t > 2.0:
                trigger_move = move
                trigger_my_time = my_t
                trigger_opp_time = opp_t
                break
        if trigger_move:
            missed.append({
                "url": url, "white": white, "black": black,
                "trigger_move": trigger_move,
                "my_t": trigger_my_time, "opp_t": trigger_opp_time,
            })

    with open(path, "w", encoding="utf-8") as f:
        f.write("=" * 60 + "\n УПУЩЕННЫЙ БЕРСЕРК\n" + "=" * 60 + "\n\n")
        f.write(f"Всего поражений по времени без берсерка: {len(games)}\n")
        pct = len(missed) / len(games) * 100 if games else 0
        f.write(f"Из них с упущенным берсерком: {len(missed)} ({pct:.1f}%)\n\n")
        f.write(f"  {'Соперник':<20} {'Ход':<6} {'Мое время':<10} {'Время соп.':<10}\n")
        for g in missed[:15]:
            opp = g["black"] if _is_player_white(g["white"]) else g["white"]
            f.write(f"  {opp[:18]:<20} {g['trigger_move']:<6} "
                    f"{g['my_t']:<10.1f} {g['opp_t']:<10.1f}\n")

    conn.close(); print(f"\n✅ {path}")


# ============================================================
# 5. TIME GAP ANALYSIS — флаг-цугцванг при сливе перевеса
# ============================================================
def report_time_gap_analysis():
    conn = _conn(); cur = conn.cursor()
    path = os.path.join(REPORTS_DIR, "time_gap_analysis.txt")

    cur.execute("""
        SELECT url, white, black, won, draw, reason, max_eval_advantage,
               clocks, eval_history, opening, end_time
        FROM games
        WHERE is_cheater=0 AND is_lag=0 AND max_eval_advantage >= 300 AND won=0
    """)
    games = cur.fetchall()

    deficit_games = []
    for row in games:
        url, white, black, won, draw, reason, max_adv, clocks_raw, evals_raw, opening, end_time = row
        clocks, hist = _load_clocks_evals(url, clocks_raw, evals_raw)
        if not clocks or not hist:
            continue
        player_is_white = _is_player_white(white)

        peak_idx = None
        drop_idx = None
        for i, (move, ev) in enumerate(hist):
            if ev >= 300 and peak_idx is None:
                peak_idx = i
            if peak_idx is not None and ev < 100 and drop_idx is None:
                drop_idx = i
        if peak_idx is None:
            continue
        if drop_idx is None:
            drop_idx = len(hist) - 1
        move_drop = hist[drop_idx][0]
        clock_idx = (move_drop - 1) * 2 if player_is_white else (move_drop - 1) * 2 + 1
        if clock_idx >= len(clocks):
            continue
        my_time = clocks[clock_idx]
        opp_time = clocks[clock_idx - 1] if clock_idx > 0 else clocks[0]
        time_diff = my_time - opp_time
        if time_diff <= -3.0:
            deficit_games.append({
                "url": url, "white": white, "black": black,
                "won": won, "draw": draw, "reason": reason,
                "max_adv": max_adv, "my_time": my_time,
                "opp_time": opp_time, "time_diff": time_diff,
            })

    with open(path, "w", encoding="utf-8") as f:
        f.write("=" * 60 + "\n АНАЛИЗ ДЕФИЦИТА ВРЕМЕНИ (ФЛАГ-ЦУГЦВАНГ)\n" + "=" * 60 + "\n\n")
        f.write(f"Всего партий со слитым перевесом: {len(games)}\n")
        pct = len(deficit_games) / len(games) * 100 if games else 0
        f.write(f"Партий, где у соперника было на 3+ сек больше при сливе: "
                f"{len(deficit_games)} ({pct:.1f}%)\n\n")
        f.write(f"  {'Соперник':<20} {'Рез.':<10} {'Перевес':<10} "
                f"{'Мое время':<10} {'Время соп.':<10} {'Дефицит'}\n")
        deficit_games.sort(key=lambda x: x["time_diff"])
        for g in deficit_games[:15]:
            res = "Ничья" if g["draw"] else "Пораж"
            opp = g["black"] if _is_player_white(g["white"]) else g["white"]
            f.write(f"  {opp[:18]:<20} {res:<10} +{g['max_adv']/100:.1f} "
                    f"{g['my_time']:<10.1f} {g['opp_time']:<10.1f} "
                    f"{g['time_diff']:<+.1f} сек\n")

    conn.close(); print(f"\n✅ {path}")

# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 60)
    print(" 07_endgame.py — ЭНДШПИЛЬ + БЕРСЕРК")
    print("=" * 60)

    if not os.path.exists(DB_FILE):
        print(f"❌ Не найдена {DB_FILE}. Запусти 03_migrate_sqlite.py.")
        return
    if not PLAYER:
        print("⚠️ В config.json нет 'player' — часть отчётов будет некорректной.")

    print("\n── 1/5. Endgame skills ──")
    report_endgame_skills()

    print("\n── 2/5. Endgame trainer ──")
    report_endgame_trainer()

    print("\n── 3/5. Berserk zone ──")
    report_berserk_zone()

    print("\n── 4/5. Missed berserk ──")
    report_missed_berserk()

    print("\n── 5/5. Time gap analysis (флаг-цугцванг) ──")
    report_time_gap_analysis()

    print(f"\n✅ Все 5 отчётов в: {REPORTS_DIR}")


if __name__ == "__main__":
    main()