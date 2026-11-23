# ============================================================
# core/time_control.py (v19.5)
# Неизвестный контроль больше не считается 1+0.
# parse_time_control_strict() возвращает (base, inc, is_known).
# ============================================================
PRIMARY_TIME_CONTROL = "1+0"
PRIMARY_BASE_SEC = 60
PRIMARY_INCREMENT_SEC = 0


def parse_time_control_strict(tc: str) -> tuple[int | None, int | None, bool]:
    if not tc or not isinstance(tc, str):
        return None, None, False
    tc = tc.strip().lower()
    if tc in ("unknown", "?", ""):
        return None, None, False
    try:
        if "+" in tc:
            base_str, inc_str = tc.split("+", 1)
            return int(base_str), int(inc_str), True
        return int(tc), 0, True
    except (ValueError, TypeError):
        return None, None, False


def parse_time_control(tc: str) -> tuple[int | None, int | None]:
    base, inc, _ = parse_time_control_strict(tc)
    return base, inc


def is_primary(tc: str) -> bool:
    base, inc = parse_time_control(tc)
    return base == PRIMARY_BASE_SEC and inc == PRIMARY_INCREMENT_SEC


def format_time_control(tc: str) -> str:
    base, inc = parse_time_control(tc)
    if base is None:
        return "unknown"
    base_min = base // 60 if base >= 60 else base
    return f"{base_min}+{inc}"


def is_supported_for_analysis(tc: str) -> bool:
    base, inc = parse_time_control(tc)
    if base == 60 and inc == 0:
        return True
    if base == 180 and inc == 2:
        return True
    return False