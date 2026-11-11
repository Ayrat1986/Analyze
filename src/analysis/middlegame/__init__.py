# ============================================================
# analysis/middlegame/__init__.py
# Публичное API пакета middlegame.
# ============================================================
from .phase_deep import report_phase_deep_dive
from .advantage_speed import report_advantage_speed
from .transition import report_transition_errors
from .tactics import report_tactical_motifs
from .win_loss_conversion import report_win_loss_conversion
from .positional_weaknesses import report_positional_weaknesses
from .plan_retention import report_plan_retention
from .piece_activity import report_piece_activity
from .position_types import report_position_types
from .long_vs_short import report_long_vs_short
from .summary import report_summary

__all__ = [
    "report_phase_deep_dive",
    "report_advantage_speed",
    "report_transition_errors",
    "report_tactical_motifs",
    "report_win_loss_conversion",
    "report_positional_weaknesses",
    "report_plan_retention",
    "report_piece_activity",
    "report_position_types",
    "report_long_vs_short",
    "report_summary",
]