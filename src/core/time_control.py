# ============================================================
# core/time_control.py (v19.4)
# Единый парсер time_control из chess.com.
# Формат: "60" (1+0), "180+2" (3+2), "300+3" (5+3), etc.
# ============================================================


# Проект настроен на 1+0 (bullet).
# 3+2 — турнирный контроль, рассматривается отдельно.
PRIMARY_TIME_CONTROL = "1+0"
PRIMARY_BASE_SEC = 60
PRIMARY_INCREMENT_SEC = 0


def parse_time_control(tc: str) -> tuple[int, int]:
    """
    Возвращает (base_sec, increment_sec).
    
    Примеры:
      "60"      → (60, 0)      # 1+0
      "180+2"   → (180, 2)     # 3+2
      "300+3"   → (300, 3)     # 5+3
      ""        → (60, 0)      # fallback
      "unknown" → (60, 0)      # fallback
    """
    if not tc or not isinstance(tc, str):
        return PRIMARY_BASE_SEC, PRIMARY_INCREMENT_SEC
    
    tc = tc.strip().lower()
    if tc in ("unknown", "?", ""):
        return PRIMARY_BASE_SEC, PRIMARY_INCREMENT_SEC
    
    try:
        if "+" in tc:
            base_str, inc_str = tc.split("+", 1)
            return int(base_str), int(inc_str)
        else:
            return int(tc), 0
    except (ValueError, TypeError):
        return PRIMARY_BASE_SEC, PRIMARY_INCREMENT_SEC


def is_primary(tc: str) -> bool:
    """True, если это 1+0 (основной контроль)."""
    base, inc = parse_time_control(tc)
    return base == PRIMARY_BASE_SEC and inc == PRIMARY_INCREMENT_SEC


def format_time_control(tc: str) -> str:
    """Человекочитаемый формат: '1+0', '3+2'."""
    base, inc = parse_time_control(tc)
    base_min = base // 60 if base >= 60 else base
    return f"{base_min}+{inc}"


def is_supported_for_analysis(tc: str) -> bool:
    """
    True, если time_control поддерживается текущими скриптами.
    Сейчас: 1+0 (основной) и 3+2 (турнирный, ограниченно).
    """
    base, inc = parse_time_control(tc)
    if base == 60 and inc == 0:      # 1+0
        return True
    if base == 180 and inc == 2:     # 3+2
        return True
    return False