# ============================================================
# analysis/dashboard_helpers.py — v27.5 (Фасад)
# Модуляризовано:
#   • analysis/dashboard_db.py         — подключение БД, клинок, агрессия PGN
#   • analysis/dashboard_kpis.py       — key_numbers (CombR v2), слабости, действия
#   • analysis/dashboard_dynamics.py   — full_dynamics, снапшоты, сессии
#   • analysis/dashboard_aggression.py — разрезы агрессии
#   • analysis/dashboard_trends.py     — тренды и графики для Streamlit
# ============================================================
from analysis.common import (  # noqa: F401
    PLAYER,
    REPORTS_DIR,
    WINDOW_LABELS,
    WINDOWS,
    window_cutoff_ts,
    window_label,
)
from analysis.dashboard_aggression import (  # noqa: F401
    aggression_by_moves,
    aggression_by_opening,
    aggression_by_phase,
    aggression_by_rating,
)
from analysis.dashboard_db import (  # noqa: F401
    DASHBOARD_FILES,
    DB_FILE,
    HAS_TURSO,
    get_blade_state,
    get_conn as _get_conn,
    percentile as _percentile,
)
from analysis.dashboard_dynamics import (  # noqa: F401
    combined_vs_perf,
    full_dynamics,
    last_session_vs_windows,
    monitoring_snapshot,
    time_vs_rating,
)
from analysis.dashboard_kpis import (  # noqa: F401
    key_numbers,
    top3_weaknesses,
    top_actions,
)
from analysis.dashboard_trends import (  # noqa: F401
    get_blunder_map_data,
    get_cascade_trend,
    get_daily_metrics_trend,
    get_hourly_rhythm,
)