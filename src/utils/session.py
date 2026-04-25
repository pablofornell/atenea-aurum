"""Single source of truth for trading session classification."""


def trading_session(server_time: str, broker_gmt_offset: int = 0) -> str:
    """Derive trading session name from MT4 server time string.

    broker_gmt_offset: hours ahead of UTC (0=UTC, 2=EET winter, 3=EEST summer).
    Labels match exactly what strategy/CLAUDE.md and the EA indicator use.
    """
    try:
        hour = int(server_time[11:13])
        minute = int(server_time[14:16])
    except (TypeError, IndexError, ValueError):
        return "Unknown"
    gmt_mins = (hour * 60 + minute - broker_gmt_offset * 60) % (24 * 60)
    h = gmt_mins // 60
    m = gmt_mins % 60

    # Kill Zones — exact institutional windows (match EA indicator defaults)
    if h == 7 or (h == 8 and m < 30):                           # 07:00–08:30 UTC
        return "London Kill Zone"
    if (h == 13 and m >= 30) or h == 14:                        # 13:30–15:00 UTC
        return "NY Kill Zone"
    # Active sessions — Trend Follow eligible
    if (h == 8 and m >= 30) or (9 <= h <= 12) or (h == 13 and m < 30):  # 08:30–13:30
        return "London Active"
    if 15 <= h <= 21:                                            # 15:00–22:00
        return "NY Active"
    # Low volatility — no new entries
    if h < 7:
        return "Asia"
    return "Late NY"
