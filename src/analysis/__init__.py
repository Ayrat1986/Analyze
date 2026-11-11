# ============================================================
# analysis/__init__.py
# ============================================================
from .constants import DEPTH

__all__ = ["DEPTH", "build_all"]


def build_all(*args, **kwargs):
    """
    Ленивый импорт сборщика дашбордов.
    Нужен для 13_dashboard_final.py. Не грузится при импорте analysis.constants.
    """
    from .dashboard import build_all as _build_all
    return _build_all(*args, **kwargs)