# ============================================================
# analysis/psych_rating/bullet_stats.py
# ============================================================
import os
import statistics
from datetime import datetime, timezone, timedelta
from importlib import import_module
from analysis.common import REPORTS_DIR, PLAYER
from core.метрики import perf_rating, anchor

fetch_api = import_module("01_fetch_chess_api")

def get_peak_for_interval(games, player, days_ago_min, days_ago_max):
    now_utc = datetime.now(timezone.utc)
    cutoff_newest = int((now_utc - timedelta(days=days_ago_min)).timestamp())
    cutoff_oldest = int((now_utc - timedelta(days=days_ago_max)).timestamp())
    interval = [g for g in games if cutoff_oldest < g.get("end_time", 0) <= cutoff_newest]
    if not interval: return 0, 0
    max_rating = 0; opp_ratings = []
    for g in interval:
        white, black = g.get("white", {}), g.get("black", {})
        is_white = white.get("username", "").lower() == player.lower()
        my_rating = white.get("rating", 0) if is_white else black.get("rating", 0)
        opp_rating = black.get("rating", 0) if is_white else white.get("rating", 0)
        if my_rating > max_rating: max_rating = my_rating
        if opp_rating > 0: opp_ratings.append(opp_rating)
    avg_opp = sum(opp_ratings) / len(opp_ratings) if opp_ratings else 0
    return max_rating, avg_opp

def calculate_stats(games, player, peak_for_anchor, avg_opp_for_anchor=None):
    total = len(games)
    if total == 0: return None
    wins, losses, draws = 0, 0, 0
    ratings, win_ratings, loss_ratings, my_ratings_with_time = [], [], [], []
    for g in games:
        white, black = g.get("white", {}), g.get("black", {})
        is_white = white.get("username", "").lower() == player.lower()
        my_rating = white.get("rating", 0) if is_white else black.get("rating", 0)
        if my_rating > 0: my_ratings_with_time.append((g.get("end_time", 0), my_rating))
        opp_rating = black.get("rating", 0) if is_white else white.get("rating", 0)
        if opp_rating > 0: ratings.append(opp_rating)
        my_result = white.get("result") if is_white else black.get("result")
        if my_result == "win":
            wins += 1
            if opp_rating > 0: win_ratings.append(opp_rating)
        elif my_result in ["checkmated", "timeout", "resigned", "abandoned", "lose"]:
            losses += 1
            if opp_rating > 0: loss_ratings.append(opp_rating)
        else: draws += 1
    actual_avg_opp = sum(ratings) / len(ratings) if ratings else 0
    my_sorted = sorted(my_ratings_with_time, key=lambda x: x[0])
    my_vals = [r for _, r in my_sorted]
    avg_my = sum(my_vals) / len(my_vals) if my_vals else 0
    first_my = my_sorted[0][1] if my_sorted else 0
    last_my = my_sorted[-1][1] if my_sorted else 0
    gap = avg_my - actual_avg_opp if (avg_my and actual_avg_opp) else 0
    min_window = min(my_vals) if my_vals else 0
    perf = perf_rating(actual_avg_opp, wins, draws, total)
    anchor_final = anchor(min_window, peak_for_anchor, actual_avg_opp)
    return {
        "total": total, "wins": wins, "losses": losses, "draws": draws, "win_rate": (wins / total) * 100,
        "loss_rate": (losses / total) * 100, "draw_rate": (draws / total) * 100, "avg_opp": actual_avg_opp,
        "avg_win": sum(win_ratings) / len(win_ratings) if win_ratings else 0, "avg_loss": sum(loss_ratings) / len(loss_ratings) if loss_ratings else 0,
        "max_rating": max(my_vals) if my_vals else 0, "perf_rating": perf, "avg_my_rating": avg_my,
        "first_my_rating": first_my, "last_my_rating": last_my, "gap": gap, "anchor_min": min_window,
        "anchor_peak": peak_for_anchor - 150, "anchor_formula": actual_avg_opp * 0.98 if actual_avg_opp > 0 else 0,
        "anchor_final": anchor_final, "peak_in_window": peak_for_anchor,
    }

def _print_block(title, stats, f):
    f.write("=" * 50 + "\n"); f.write(f" ОКНО: {title}\n"); f.write("=" * 50 + "\n")
    if not stats: f.write(" Нет данных.\n\n"); return
    f.write(f" Партий: {stats['total']}\n")
    f.write(f" Победы: {stats['wins']} ({stats['win_rate']:.1f}%)\n")
    f.write(f" Поражения: {stats['losses']} ({stats['loss_rate']:.1f}%)\n")
    f.write(f" Ничьи: {stats['draws']} ({stats['draw_rate']:.1f}%)\n")
    f.write("-" * 50 + "\n")
    f.write(f" Исторический пик до окна: {stats['peak_in_window']}\n")
    f.write(f" Мой рейтинг на начало: {stats['first_my_rating']}\n")
    f.write(f" Мой средний рейтинг: {stats['avg_my_rating']:.0f}\n")
    f.write(f" Мой последний рейтинг: {stats['last_my_rating']}\n")
    f.write(f" Средний рейтинг соперников: {stats['avg_opp']:.0f}\n")
    f.write(f"  - В победах: {stats['avg_win']:.0f}\n")
    f.write(f"  - В поражениях: {stats['avg_loss']:.0f}\n")
    f.write(f" Разрыв: {stats['gap']:+.0f}\n")
    f.write("-" * 50 + "\n")
    f.write(f" 🔥 PERFORMANCE: {stats['perf_rating']:.0f}\n")
    f.write("-" * 50 + "\n")
    f.write(f" ⚓ ЯКОРЬ:\n")
    f.write(f"  1) Минимум: {stats['anchor_min']}\n")
    f.write(f"  2) Пик − 150: {stats['anchor_peak']}\n")
    f.write(f"  3) Ср. рейтинг ×0.98: {stats['anchor_formula']:.0f}\n")
    f.write(f"  ⚓ ИТОГОВЫЙ: {stats['anchor_final']:.0f}\n\n")

def report_bullet_stats():
    all_games = fetch_api.get_games_from_cache(player=fetch_api.PLAYER, days=fetch_api.DAYS_TO_FETCH, time_class=fetch_api.TIME_CLASS, max_base=fetch_api.MAX_BULLET_BASE_TIME, require_pgn=False)
    if not all_games: print("⚠️ bullet_stats пропущен: нет партий в кэше."); return
    
    peaks = {1: get_peak_for_interval(all_games, PLAYER, 0, 90), 2: get_peak_for_interval(all_games, PLAYER, 1, 90), 7: get_peak_for_interval(all_games, PLAYER, 2, 90), 30: get_peak_for_interval(all_games, PLAYER, 7, 90), 90: get_peak_for_interval(all_games, PLAYER, 30, 90)}
    now = datetime.now(timezone.utc)
    path = os.path.join(REPORTS_DIR, "bullet_stats_report.txt")
    
    with open(path, "w", encoding="utf-8") as f:
        f.write("=" * 50 + "\n СТАТИСТИКА BULLET CHESS.COM\n" + "=" * 50 + "\n\n")
        for d in [1, 2, 7, 30, 90]:
            title = f"{d} ДЕНЬ" if d == 1 else (f"{d} ДНЯ" if d == 2 else f"{d} ДНЕЙ")
            cutoff_utc = int((now - timedelta(days=d)).timestamp())
            games_in_window = [g for g in all_games if g.get("end_time", 0) >= cutoff_utc]
            peak_for_anchor, avg_opp_for_anchor = peaks[d]
            stats = calculate_stats(games_in_window, PLAYER, peak_for_anchor, avg_opp_for_anchor)
            _print_block(title, stats, f)
        f.write("✅ Готово.\n")
    print(f"\n✅ {path}")