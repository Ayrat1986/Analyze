# ============================================================
# core/time_control.py (v25.3)
# Единый парсер time_control из chess.com.
# FIX v25.3:
#   - parse_time_control_strict() гарантирует корректный кортеж (base, inc, is_known).
#   - parse_time_control() оставлен для 100% обратной совместимости.
#   - Защита от отрицательных и невалидных значений.
# ============================================================

PRIMARY_TIME_CONTROL = "1+0"
PRIMARY_BASE_SEC = 60
PRIMARY_INCREMENT_SEC = 0


def parse_time_control_strict(tc: str) -> tuple[int | None, int | None, bool]:
    """
    Возвращает (base_sec, increment_sec, is_known).
    is_known = False, если контроль не распознан.
    Примеры:
      "60"      → (60, 0, True)
      "180+2"   → (180, 2, True)
      "300+3"   → (300, 3, True)
      ""        → (None, None, False)
      "unknown" → (None, None, False)
    """
    if not tc or not isinstance(tc, str):
        return None, None, False
    tc = tc.strip().lower()
    if tc in ("unknown", "?", "", "none"):
        return None, None, False
    try:
        if "+" in tc:
            base_str, inc_str = tc.split("+", 1)
            b = int(base_str)
            inc = int(inc_str)
            if b < 0 or inc < 0:
                return None, None, False
            return b, inc, True
        else:
            b = int(tc)
            if b < 0:
                return None, None, False
            return b, 0, True
    except (ValueError, TypeError):
        return None, None, False


def parse_time_control(tc: str) -> tuple[int | None, int | None]:
    """
    Обратная совместимость.
    Для неизвестных возвращает (None, None), а НЕ дефолтные (60, 0).
    """
    base, inc, _ = parse_time_control_strict(tc)
    return base, inc


def is_primary(tc: str) -> bool:
    """True, если это 1+0 (основной контроль пули)."""
    base, inc = parse_time_control(tc)
    return base == PRIMARY_BASE_SEC and inc == PRIMARY_INCREMENT_SEC


def format_time_control(tc: str) -> str:
    """Человекочитаемый формат: '1+0', '3+2'."""
    base, inc = parse_time_control(tc)
    if base is None:
        return "unknown"
    base_min = base // 60 if base >= 60 else base
    return f"{base_min}+{inc}"


def is_supported_for_analysis(tc: str) -> bool:
    """1+0 (основной) и 3+2 (турнирный, ограниченно)."""
    base, inc = parse_time_control(tc)
    if base == 60 and inc == 0:
        return True
    if base == 180 and inc == 2:
        return True
    return False
