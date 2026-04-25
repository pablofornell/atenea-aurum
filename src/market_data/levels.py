"""Pure functions for SMC/ICT technical level calculation on OHLC data."""
from typing import Optional


def find_swing_highs(candles: list, lookback: int = 3) -> list:
    if len(candles) < 2 * lookback + 1:
        return []
    result = []
    for i in range(lookback, len(candles) - lookback):
        pivot_high = candles[i]["high"]
        if all(pivot_high > candles[i - j]["high"] for j in range(1, lookback + 1)) and \
           all(pivot_high > candles[i + j]["high"] for j in range(1, lookback + 1)):
            result.append({
                "index": i,
                "price": pivot_high,
                "timestamp": candles[i]["timestamp"],
            })
    result.sort(key=lambda x: x["index"], reverse=True)
    return result


def find_swing_lows(candles: list, lookback: int = 3) -> list:
    if len(candles) < 2 * lookback + 1:
        return []
    result = []
    for i in range(lookback, len(candles) - lookback):
        pivot_low = candles[i]["low"]
        if all(pivot_low < candles[i - j]["low"] for j in range(1, lookback + 1)) and \
           all(pivot_low < candles[i + j]["low"] for j in range(1, lookback + 1)):
            result.append({
                "index": i,
                "price": pivot_low,
                "timestamp": candles[i]["timestamp"],
            })
    result.sort(key=lambda x: x["index"], reverse=True)
    return result


def detect_structure(candles: list) -> dict:
    default = {
        "bias": "RANGING",
        "last_hh": None,
        "last_ll": None,
        "last_lh": None,
        "last_hl": None,
        "choch_detected": False,
        "choch_level": None,
        "description": "RANGING",
    }
    if not candles:
        return default

    swing_highs = find_swing_highs(candles, lookback=3)
    swing_lows = find_swing_lows(candles, lookback=3)

    recent_highs = sorted(swing_highs[:6], key=lambda x: x["index"])
    recent_lows = sorted(swing_lows[:6], key=lambda x: x["index"])

    hh_count = 0
    lh_count = 0
    for i in range(1, len(recent_highs)):
        if recent_highs[i]["price"] > recent_highs[i - 1]["price"]:
            hh_count += 1
        else:
            lh_count += 1

    hl_count = 0
    ll_count = 0
    for i in range(1, len(recent_lows)):
        if recent_lows[i]["price"] > recent_lows[i - 1]["price"]:
            hl_count += 1
        else:
            ll_count += 1

    last_hh: Optional[float] = None
    last_lh: Optional[float] = None
    last_hl: Optional[float] = None
    last_ll: Optional[float] = None

    for i in range(len(recent_highs) - 1, 0, -1):
        if recent_highs[i]["price"] > recent_highs[i - 1]["price"]:
            if last_hh is None:
                last_hh = recent_highs[i]["price"]
        else:
            if last_lh is None:
                last_lh = recent_highs[i]["price"]
        if last_hh is not None and last_lh is not None:
            break

    for i in range(len(recent_lows) - 1, 0, -1):
        if recent_lows[i]["price"] > recent_lows[i - 1]["price"]:
            if last_hl is None:
                last_hl = recent_lows[i]["price"]
        else:
            if last_ll is None:
                last_ll = recent_lows[i]["price"]
        if last_hl is not None and last_ll is not None:
            break

    bullish_signals = hh_count + hl_count
    bearish_signals = lh_count + ll_count
    total_signals = bullish_signals + bearish_signals

    if total_signals == 0:
        bias = "RANGING"
    elif bullish_signals > bearish_signals and bullish_signals / total_signals >= 0.6:
        bias = "BULLISH"
    elif bearish_signals > bullish_signals and bearish_signals / total_signals >= 0.6:
        bias = "BEARISH"
    else:
        bias = "RANGING"

    choch_detected = False
    choch_level: Optional[float] = None
    current_close = candles[-1]["close"] if candles else None

    if current_close is not None:
        if bias == "BEARISH" and swing_highs:
            last_swing_high = swing_highs[0]["price"]
            if current_close > last_swing_high:
                choch_detected = True
                choch_level = last_swing_high
        elif bias == "BULLISH" and swing_lows:
            last_swing_low = swing_lows[0]["price"]
            if current_close < last_swing_low:
                choch_detected = True
                choch_level = last_swing_low

    if bias == "BULLISH":
        high_prices = "→".join(f"{h['price']:.0f}" for h in sorted(swing_highs[:3], key=lambda x: x["index"]))
        description = f"BULLISH(HH:{high_prices})"
    elif bias == "BEARISH":
        high_prices = "→".join(f"{h['price']:.0f}" for h in sorted(swing_highs[:3], key=lambda x: x["index"]))
        description = f"BEARISH(LH:{high_prices})"
    else:
        description = "RANGING"

    return {
        "bias": bias,
        "last_hh": last_hh,
        "last_ll": last_ll,
        "last_lh": last_lh,
        "last_hl": last_hl,
        "choch_detected": choch_detected,
        "choch_level": choch_level,
        "description": description,
    }


def calc_atr(candles: list, period: int = 14) -> float:
    if len(candles) < period + 1:
        return 0.0

    trs = []
    for i in range(1, len(candles)):
        high = candles[i]["high"]
        low = candles[i]["low"]
        prev_close = candles[i - 1]["close"]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)

    atr = sum(trs[:period]) / period
    alpha = 1.0 / period
    for tr in trs[period:]:
        atr = alpha * tr + (1 - alpha) * atr

    return atr


def find_ssl_bsl(candles_h1: list, candles_d1: list, candles_w1: list) -> dict:
    result = {
        "weekly_ssl": None,
        "weekly_ssl_timestamp": None,
        "weekly_bsl": None,
        "weekly_bsl_timestamp": None,
        "daily_ssl": None,
        "daily_bsl": None,
        "weekly_open": None,
        "daily_open": None,
    }

    if len(candles_w1) >= 2:
        prev_week = candles_w1[-2]
        result["weekly_ssl"] = prev_week["low"]
        result["weekly_ssl_timestamp"] = prev_week["timestamp"]
        result["weekly_bsl"] = prev_week["high"]
        result["weekly_bsl_timestamp"] = prev_week["timestamp"]

    if candles_w1:
        result["weekly_open"] = candles_w1[-1]["open"]

    if len(candles_d1) >= 2:
        prev_day = candles_d1[-2]
        result["daily_ssl"] = prev_day["low"]
        result["daily_bsl"] = prev_day["high"]

    if candles_d1:
        result["daily_open"] = candles_d1[-1]["open"]

    return result


def check_ssl_swept(candles_h1: list, ssl_level: float, lookback_candles: int = 48) -> dict:
    default = {
        "swept": False,
        "swept_at": None,
        "swept_low": None,
        "pts_below": None,
        "candles_ago": None,
    }

    if not candles_h1 or ssl_level is None:
        return default

    window = candles_h1[-(lookback_candles + 1):-1]
    if not window:
        return default

    for i, candle in enumerate(reversed(window)):
        if candle["low"] < ssl_level and candle["close"] > ssl_level:
            return {
                "swept": True,
                "swept_at": candle["timestamp"],
                "swept_low": candle["low"],
                "pts_below": ssl_level - candle["low"],
                "candles_ago": i + 1,
            }

    return default
