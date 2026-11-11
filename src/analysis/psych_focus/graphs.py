# ============================================================
# analysis/psych_focus/graphs.py
# ============================================================
import os
import json
from .common import _conn, REPORTS_DIR

GRAPHS_DIR = os.path.join(REPORTS_DIR, "graphs")
os.makedirs(GRAPHS_DIR, exist_ok=True)

def _eval_graph(url, out_path=None):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("❌ matplotlib не установлен. pip install matplotlib")
        return False

    conn = _conn(); cur = conn.cursor()
    cur.execute("SELECT white, black, won, reason, my_rating, opp_rating, eval_history FROM games WHERE url=?", (url,))
    row = cur.fetchone()
    conn.close()
    if not row: return False
    
    white, black, won, reason, mr, orat, raw = row
    try:
        hist = json.loads(raw)
        pts = [(int(a), float(b)) for a, b in hist if a is not None and b is not None]
    except Exception:
        pts = []
    if not pts: return False

    moves = [p[0] for p in pts]
    evals = [p[1] / 100.0 for p in pts]

    if out_path is None:
        slug = (white + "_vs_" + black).replace(" ", "_").replace("/", "_")[:40]
        out_path = os.path.join(GRAPHS_DIR, f"eval_{slug}.png")

    plt.figure(figsize=(14, 6))
    plt.plot(moves, evals, color="steelblue", linewidth=2)
    plt.axhline(0, color="gray", linestyle="--", linewidth=1)
    plt.fill_between(moves, evals, 0, where=[e > 0 for e in evals], color="green", alpha=0.15)
    plt.fill_between(moves, evals, 0, where=[e < 0 for e in evals], color="red", alpha=0.15)
    res = "ПОБЕДА" if won else (reason if reason != "ничья" else "НИЧЬЯ")
    plt.title(f"{white} vs {black} — {res} | {mr} vs {orat}", fontsize=11)
    plt.xlabel("Номер моего хода")
    plt.ylabel("Eval (+ = лучше)")
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_path, dpi=100)
    plt.close()
    print(f"✅ {out_path}")
    return True

def report_auto_graphs():
    try:
        import matplotlib  # noqa: F401
    except ImportError:
        print("❌ matplotlib не установлен — графики пропущены.")
        return

    conn = _conn(); cur = conn.cursor()
    print("=" * 60); print(" AUTO GRAPHS"); print("=" * 60)

    # 1. Слитые партии (+3.0)
    cur.execute("""
        SELECT url FROM games WHERE is_lag=0 AND is_cheater=0 AND max_eval_advantage >= 300 AND won=0
        ORDER BY max_eval_advantage DESC LIMIT 3
    """)
    for i, (url,) in enumerate(cur.fetchall(), 1):
        _eval_graph(url, out_path=os.path.join(GRAPHS_DIR, f"lost_won_{i}.png"))

    # 2. Худший миттельшпиль
    cur.execute("""
        SELECT url FROM games WHERE is_lag=0 AND is_cheater=0 AND acpl_middlegame > 0
        ORDER BY acpl_middlegame DESC LIMIT 3
    """)
    for i, (url,) in enumerate(cur.fetchall(), 1):
        _eval_graph(url, out_path=os.path.join(GRAPHS_DIR, f"worst_mid_{i}.png"))

    conn.close()
    print(f"\n✅ Графики в {GRAPHS_DIR}/")

def run_auto_graphs():
    report_auto_graphs()