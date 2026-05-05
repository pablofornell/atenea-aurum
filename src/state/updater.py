"""
Code-managed state updater. Runs before the agent each cycle.
All functions modify state in-place.
"""

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

_PIP = 0.10   # 1 pip = $0.10 for XAUUSD


# ── Time helpers ──────────────────────────────────────────────────────────────

def _now_str() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_time(t: str) -> datetime:
    for fmt in ("%Y.%m.%d %H:%M", "%Y-%m-%d %H:%M", "%Y.%m.%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(t, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    # Try ISO format (already has tz info)
    try:
        return datetime.fromisoformat(t)
    except ValueError:
        pass
    raise ValueError(f"Cannot parse time: {t!r}")


def _minutes_since(t_str: str) -> float:
    try:
        dt = _parse_time(t_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 60
    except Exception:
        return 9999.0


def _hours_since(t_str: str) -> float:
    return _minutes_since(t_str) / 60


def _days_since(t_str: str) -> float:
    return _hours_since(t_str) / 24


def _pips(price_diff: float) -> int:
    return round(price_diff / _PIP)


# ── ATR ───────────────────────────────────────────────────────────────────────

def _compute_atr(candles: list, period: int = 14) -> float:
    if len(candles) < period + 1:
        return 0.0
    trs = []
    for i in range(1, len(candles)):
        h = candles[i]["high"]
        l = candles[i]["low"]
        pc = candles[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if len(trs) < period:
        return 0.0
    return sum(trs[-period:]) / period


# ── Swing detection ───────────────────────────────────────────────────────────

def _find_swings(candles: list, n: int) -> tuple[list, list]:
    """
    Returns (swing_highs, swing_lows) as lists of {"time": str, "price": float}.
    A swing high at index i: candle[i].high is strictly greater than all N neighbors on each side.
    """
    highs, lows = [], []
    for i in range(n, len(candles) - n):
        h = candles[i]["high"]
        l = candles[i]["low"]
        t = candles[i]["time"]

        if all(h > candles[j]["high"] for j in range(i - n, i + n + 1) if j != i):
            highs.append({"time": t, "price": h})

        if all(l < candles[j]["low"] for j in range(i - n, i + n + 1) if j != i):
            lows.append({"time": t, "price": l})

    return highs, lows


# ── 1. Session context ────────────────────────────────────────────────────────

def _update_session_context(state: dict, context: dict, cfg) -> None:
    now = datetime.now(timezone.utc)
    h = now.hour
    today = now.date()

    if 0 <= h < 7:
        session = "asia"
    elif 7 <= h < 12:
        session = "london"
    elif 12 <= h < 16:
        session = "overlap"
    elif 16 <= h < 20:
        session = "ny"
    else:
        session = "off"

    killzones = getattr(cfg, "KILLZONES", [])
    killzone_active = bool(killzones and any(start <= h < end for start, end in killzones))

    # Asia range from H1 candles (00:00–07:00 GMT today)
    asia_high, asia_low = 0.0, float("inf")
    for c in context["candles"].get("H1", []):
        try:
            t = _parse_time(c["time"])
            if t.date() == today and 0 <= t.hour < 7:
                asia_high = max(asia_high, c["high"])
                asia_low = min(asia_low, c["low"])
        except Exception:
            pass

    ctx = state["code_managed"]["session_context"]
    ctx["current_session"] = session
    ctx["killzone_active"] = killzone_active
    ctx["asia_range"] = {
        "high": asia_high if asia_high > 0 else 0.0,
        "low": asia_low if asia_low != float("inf") else 0.0,
    }

    # London open price (07:00 candle) and NY open price (12:00 candle) today
    for c in context["candles"].get("H1", []):
        try:
            t = _parse_time(c["time"])
            if t.date() == today:
                if t.hour == 7:
                    ctx["london_open_price"] = c["open"]
                if t.hour == 12:
                    ctx["ny_open_price"] = c["open"]
        except Exception:
            pass


# ── 2. ATR ────────────────────────────────────────────────────────────────────

def _update_atr(state: dict, context: dict) -> None:
    atr = state["code_managed"]["atr"]
    atr["h4_pips"] = round(_compute_atr(context["candles"].get("H4", [])) / _PIP)
    atr["h1_pips"] = round(_compute_atr(context["candles"].get("H1", [])) / _PIP)
    atr["m15_pips"] = round(_compute_atr(context["candles"].get("M15", [])) / _PIP)


# ── 3. Liquidity pools ────────────────────────────────────────────────────────

def _price_in_list(price: float, lst: list, tol_pips: float = 2.0) -> bool:
    tol = tol_pips * _PIP
    return any(abs(item["price"] - price) <= tol for item in lst)


def _update_liquidity_pools(state: dict, context: dict) -> list:
    """
    Returns list of swept pool descriptions for logging.
    Modifies state["code_managed"]["untaken_liquidity"] and ["swept_liquidity_recent"].
    """
    cm = state["code_managed"]
    bsl = cm["untaken_liquidity"]["bsl"]
    ssl = cm["untaken_liquidity"]["ssl"]
    swept = cm["swept_liquidity_recent"]

    bid = context["price"]["bid"]
    d = context["day_ohlc"]
    w = context["week_hl"]
    asia = cm["session_context"]["asia_range"]
    now = _now_str()
    swept_log = []

    # ── Static named levels (refresh each cycle) ──────────────────────────────
    # Remove old named entries and re-insert with current prices
    named_sources = {"pdh", "pdl", "pwh", "pwl", "asia_high", "asia_low"}
    bsl[:] = [b for b in bsl if b.get("source") not in named_sources]
    ssl[:] = [s for s in ssl if s.get("source") not in named_sources]

    def _add_bsl(price, source, tf="D1"):
        if price > 0 and price > bid and not _price_in_list(price, bsl, 1.0):
            bsl.append({"price": price, "source": source, "created": now, "timeframe": tf})

    def _add_ssl(price, source, tf="D1"):
        if price > 0 and price < bid and not _price_in_list(price, ssl, 1.0):
            ssl.append({"price": price, "source": source, "created": now, "timeframe": tf})

    _add_bsl(d["prev_high"], "pdh")
    _add_ssl(d["prev_low"], "pdl")
    _add_bsl(w["prev_high"], "pwh", "W1")
    _add_ssl(w["prev_low"], "pwl", "W1")
    if asia["high"] > 0:
        _add_bsl(asia["high"], "asia_high", "H1")
    if asia["low"] > 0:
        _add_ssl(asia["low"], "asia_low", "H1")

    # ── Swing-based pools from candles ────────────────────────────────────────
    tf_configs = [
        ("H4", context["candles"].get("H4", []), 3),
        ("H1", context["candles"].get("H1", []), 3),
        ("M15", context["candles"].get("M15", []), 2),
    ]
    for tf, candles, n in tf_configs:
        highs, lows = _find_swings(candles, n)

        for sh in highs:
            p = sh["price"]
            if p > bid and not _price_in_list(p, bsl):
                bsl.append({"price": p, "source": "swing_high",
                             "created": sh["time"], "timeframe": tf})

        for sl_ in lows:
            p = sl_["price"]
            if p < bid and not _price_in_list(p, ssl):
                ssl.append({"price": p, "source": "swing_low",
                             "created": sl_["time"], "timeframe": tf})

    # ── Equal highs / lows (within 2.5 pips) ─────────────────────────────────
    def _mark_equal(pools, side):
        tol = 2.5 * _PIP
        for i, a in enumerate(pools):
            for j, b in enumerate(pools):
                if i < j and abs(a["price"] - b["price"]) <= tol:
                    avg = (a["price"] + b["price"]) / 2
                    src = f"equal_{'highs' if side == 'bsl' else 'lows'}"
                    if not _price_in_list(avg, pools, 1.0):
                        pools.append({"price": avg, "source": src,
                                      "created": _now_str(), "timeframe": "multi"})

    _mark_equal(bsl, "bsl")
    _mark_equal(ssl, "ssl")

    # ── Detect sweeps: candle wick penetrates the pool level ──────────────────
    all_recent_candles = []
    for tf, candles, _ in tf_configs:
        if candles:
            all_recent_candles.append(candles[-1])

    swept_bsl = []
    swept_ssl = []
    for rc in all_recent_candles:
        for pool in bsl:
            if rc["high"] >= pool["price"] and pool not in swept_bsl:
                swept_bsl.append(pool)
        for pool in ssl:
            if rc["low"] <= pool["price"] and pool not in swept_ssl:
                swept_ssl.append(pool)

    for pool in swept_bsl:
        bsl.remove(pool)
        entry = {**pool, "side": "BSL", "swept_at": now,
                 "minutes_ago": 0}
        swept.append(entry)
        swept_log.append(f"BSL swept at {pool['price']:.2f} ({pool['source']})")

    for pool in swept_ssl:
        ssl.remove(pool)
        entry = {**pool, "side": "SSL", "swept_at": now,
                 "minutes_ago": 0}
        swept.append(entry)
        swept_log.append(f"SSL swept at {pool['price']:.2f} ({pool['source']})")

    # Update minutes_ago for all swept entries
    for entry in swept:
        try:
            entry["minutes_ago"] = round(_minutes_since(entry["swept_at"]))
        except Exception:
            pass

    return swept_log


# ── 4. Structural events ──────────────────────────────────────────────────────

def _update_structural_events(state: dict, context: dict) -> list:
    """
    Detects new BOS/CHoCH events on H4 and H1.
    Returns list of event descriptions for logging.
    """
    cm = state["code_managed"]
    log = []

    for tf, candles, n, key in [
        ("H4", context["candles"].get("H4", []), 3, "h4_structural_events"),
        ("H1", context["candles"].get("H1", []), 3, "h1_structural_events"),
    ]:
        existing = cm[key]
        new_events = _detect_structure(candles, n, existing)
        for ev in new_events:
            existing.append(ev)
            log.append(f"{tf} {ev['type']} {ev['direction']} @ {ev['price']:.2f}")
        # Keep last 10
        cm[key] = existing[-10:]

    return log


def _detect_structure(candles: list, n: int, existing: list) -> list:
    """Detect new BOS/CHoCH events not already in existing list."""
    if len(candles) < 2 * n + 2:
        return []

    highs, lows = _find_swings(candles, n)
    if not highs and not lows:
        return []

    last_event = existing[-1] if existing else None
    current_bias = last_event["direction"] if last_event else None
    last_event_time = last_event["time"] if last_event else None

    # Full scan on init (no history); incremental scan (last 5) on updates.
    check_start = n if not existing else max(0, len(candles) - 5)

    new_events = []

    for i in range(check_start, len(candles)):
        c = candles[i]
        close = c["close"]
        t = c["time"]

        if last_event_time and t <= last_event_time:
            continue

        # Most recent confirmed swing high BEFORE this candle
        sh_candidates = [sh for sh in highs if sh["time"] < t]
        if sh_candidates:
            last_sh = sh_candidates[-1]
            if close > last_sh["price"]:
                ev_type = "BOS" if current_bias == "up" else "CHoCH"
                if not _event_already_tracked(last_sh["price"], "up", existing + new_events):
                    ev = {"type": ev_type, "direction": "up",
                          "price": last_sh["price"], "time": t}
                    new_events.append(ev)
                    current_bias = "up"
                    last_event_time = t

        # Most recent confirmed swing low BEFORE this candle
        sl_candidates = [sl for sl in lows if sl["time"] < t]
        if sl_candidates:
            last_sl = sl_candidates[-1]
            if close < last_sl["price"]:
                ev_type = "BOS" if current_bias == "down" else "CHoCH"
                if not _event_already_tracked(last_sl["price"], "down", existing + new_events):
                    ev = {"type": ev_type, "direction": "down",
                          "price": last_sl["price"], "time": t}
                    new_events.append(ev)
                    current_bias = "down"
                    last_event_time = t

    return new_events


def _event_already_tracked(price: float, direction: str, events: list, tol: float = 0.15) -> bool:
    return any(
        e["direction"] == direction and abs(e["price"] - price) < tol
        for e in events
    )


# ── 5. POIs (FVGs and Order Blocks) ──────────────────────────────────────────

def _update_pois(state: dict, context: dict) -> list:
    """
    Adds new POIs, updates fill%, marks mitigated ones.
    Returns list of mitigated POI descriptions for logging.
    """
    cm = state["code_managed"]
    active = cm["active_pois"]
    mitigated_recent = cm["mitigated_pois_recent"]
    bid = context["price"]["bid"]
    atr = cm["atr"]
    now = _now_str()
    mitigated_log = []

    tf_configs = [
        ("H4", context["candles"].get("H4", []), atr["h4_pips"]),
        ("H1", context["candles"].get("H1", []), atr["h1_pips"]),
        ("M15", context["candles"].get("M15", []), atr["m15_pips"]),
    ]

    for tf, candles, atr_pips in tf_configs:
        if len(candles) < 3:
            continue
        new_fvgs = _detect_fvgs(candles, tf, active, bid)
        new_obs = _detect_obs(candles, tf, active, bid, atr_pips)
        active.extend(new_fvgs)
        active.extend(new_obs)

    # Update fill% and detect mitigation for all active POIs
    still_active = []
    for poi in active:
        # Already mitigated in a prior cycle — keep for deduplication, skip re-check
        if poi.get("mitigated"):
            still_active.append(poi)
            continue

        poi_type = poi["type"]
        high = poi["high"]
        low = poi["low"]

        if "bullish" in poi_type:
            # Price enters from above, full mitigation = close below low
            if bid <= low:
                poi["mitigated"] = True
                poi["mitigated_at"] = now
                poi["filled_pct"] = 1.0
            elif bid < high:
                poi["filled_pct"] = round((high - bid) / (high - low), 2) if high > low else 0.0
            else:
                poi["filled_pct"] = 0.0
        else:  # bearish
            # Price enters from below, full mitigation = close above high
            if bid >= high:
                poi["mitigated"] = True
                poi["mitigated_at"] = now
                poi["filled_pct"] = 1.0
            elif bid > low:
                poi["filled_pct"] = round((bid - low) / (high - low), 2) if high > low else 0.0
            else:
                poi["filled_pct"] = 0.0

        if poi.get("mitigated"):
            mitigated_recent.append({"id": poi["id"], "type": poi_type,
                                      "mitigated_at": now})
            mitigated_log.append(f"{poi.get('timeframe', '?')} {poi_type} mitigated at {bid:.2f}")

        still_active.append(poi)

    cm["active_pois"] = still_active
    return mitigated_log


def _detect_fvgs(candles: list, tf: str, existing: list, bid: float) -> list:
    new_pois = []
    min_gap = 0.50  # minimum 5-pip gap (5 * 0.10)

    for i in range(1, len(candles) - 1):
        c0, c1, c2 = candles[i - 1], candles[i], candles[i + 1]

        # Bullish FVG: gap between c0.high and c2.low
        gap_low = c0["high"]
        gap_high = c2["low"]
        if gap_high > gap_low and (gap_high - gap_low) >= min_gap:
            if not _poi_exists(gap_low, gap_high, existing + new_pois):
                poi_id = str(uuid.uuid4())[:8]
                new_pois.append({
                    "id": poi_id,
                    "type": "bullish_fvg",
                    "high": gap_high,
                    "low": gap_low,
                    "timeframe": tf,
                    "created": c2["time"],
                    "filled_pct": 0.0,
                    "mitigated": False,
                })

        # Bearish FVG: gap between c2.high and c0.low
        gap_low2 = c2["high"]
        gap_high2 = c0["low"]
        if gap_high2 > gap_low2 and (gap_high2 - gap_low2) >= min_gap:
            if not _poi_exists(gap_low2, gap_high2, existing + new_pois):
                poi_id = str(uuid.uuid4())[:8]
                new_pois.append({
                    "id": poi_id,
                    "type": "bearish_fvg",
                    "high": gap_high2,
                    "low": gap_low2,
                    "timeframe": tf,
                    "created": c2["time"],
                    "filled_pct": 0.0,
                    "mitigated": False,
                })

    return new_pois


def _detect_obs(candles: list, tf: str, existing: list, bid: float, atr_pips: int) -> list:
    new_pois = []
    atr_price = max(atr_pips * _PIP, 1.0)  # minimum threshold

    for i in range(2, len(candles)):
        disp = candles[i]
        body = abs(disp["close"] - disp["open"])
        if body < atr_price:
            continue

        # Bullish displacement
        if disp["close"] > disp["open"]:
            ob = _last_bearish(candles, i - 1, lookback=5)
            if ob and disp["close"] > ob["high"]:
                if not _poi_exists(ob["low"], ob["high"], existing + new_pois):
                    new_pois.append({
                        "id": str(uuid.uuid4())[:8],
                        "type": "bullish_ob",
                        "high": ob["high"],
                        "low": ob["low"],
                        "timeframe": tf,
                        "created": disp["time"],
                        "filled_pct": 0.0,
                        "mitigated": False,
                    })

        # Bearish displacement
        elif disp["close"] < disp["open"]:
            ob = _last_bullish(candles, i - 1, lookback=5)
            if ob and disp["close"] < ob["low"]:
                if not _poi_exists(ob["low"], ob["high"], existing + new_pois):
                    new_pois.append({
                        "id": str(uuid.uuid4())[:8],
                        "type": "bearish_ob",
                        "high": ob["high"],
                        "low": ob["low"],
                        "timeframe": tf,
                        "created": disp["time"],
                        "filled_pct": 0.0,
                        "mitigated": False,
                    })

    return new_pois


def _last_bearish(candles: list, from_idx: int, lookback: int) -> dict | None:
    for i in range(from_idx, max(from_idx - lookback, -1), -1):
        if candles[i]["close"] < candles[i]["open"]:
            return candles[i]
    return None


def _last_bullish(candles: list, from_idx: int, lookback: int) -> dict | None:
    for i in range(from_idx, max(from_idx - lookback, -1), -1):
        if candles[i]["close"] > candles[i]["open"]:
            return candles[i]
    return None


def _poi_exists(low: float, high: float, pois: list, tol: float = 0.50) -> bool:
    return any(
        abs(p["low"] - low) < tol and abs(p["high"] - high) < tol
        for p in pois
    )


# ── 6. Distances ──────────────────────────────────────────────────────────────

def _update_distances(state: dict, context: dict) -> None:
    cm = state["code_managed"]
    bid = context["price"]["bid"]
    d = context["day_ohlc"]
    w = context["week_hl"]
    asia = cm["session_context"]["asia_range"]
    bsl = cm["untaken_liquidity"]["bsl"]
    ssl = cm["untaken_liquidity"]["ssl"]

    bsl_above = [b["price"] for b in bsl if b["price"] > bid]
    ssl_below = [s["price"] for s in ssl if s["price"] < bid]

    nearest_bsl = min(bsl_above) if bsl_above else bid
    nearest_ssl = max(ssl_below) if ssl_below else bid

    def p(price): return _pips(price - bid)

    cm["distances"] = {
        "to_pdh_pips": p(d["prev_high"]),
        "to_pdl_pips": p(d["prev_low"]),
        "to_pwh_pips": p(w["prev_high"]),
        "to_pwl_pips": p(w["prev_low"]),
        "to_asia_high_pips": p(asia["high"]) if asia["high"] > 0 else 0,
        "to_asia_low_pips": p(asia["low"]) if asia["low"] > 0 else 0,
        "to_nearest_untaken_bsl_pips": p(nearest_bsl) if nearest_bsl != bid else 0,
        "to_nearest_untaken_ssl_pips": p(nearest_ssl) if nearest_ssl != bid else 0,
    }


# ── 7. Open position metrics ──────────────────────────────────────────────────

def _update_position_metrics(state: dict, context: dict) -> None:
    cm = state["code_managed"]
    positions = context["positions"]
    bid = context["price"]["bid"]
    ask = context["price"]["ask"]

    if not positions:
        cm["open_position_metrics"] = {
            "ticket": None, "type": None, "entry_price": 0.0,
            "current_pnl_pips": 0, "max_drawdown_pips": 0,
            "max_profit_pips": 0, "tp_completion_pct": 0.0, "minutes_open": 0,
        }
        return

    pos = positions[0]
    ticket = pos["ticket"]
    pos_type = str(pos["type"]).upper()
    entry = pos["open"]
    tp = pos["tp"]

    is_buy = pos_type in ("BUY", "0")
    if is_buy:
        pnl_pips = _pips(bid - entry)
        tp_dist = tp - entry if tp > entry else 0
        pnl_price = bid - entry
    else:
        pnl_pips = _pips(entry - ask)
        tp_dist = entry - tp if tp < entry else 0
        pnl_price = entry - ask

    tp_pct = round(max(0.0, min(1.0, pnl_price / tp_dist)), 2) if tp_dist > 0 else 0.0

    prev = cm.get("open_position_metrics", {})
    if prev.get("ticket") == ticket:
        max_dd = min(prev.get("max_drawdown_pips", 0), pnl_pips)
        max_pr = max(prev.get("max_profit_pips", 0), pnl_pips)
        mins_open = prev.get("minutes_open", 0) + 15
    else:
        max_dd = min(0, pnl_pips)
        max_pr = max(0, pnl_pips)
        mins_open = 15

    cm["open_position_metrics"] = {
        "ticket": ticket,
        "type": pos_type,
        "entry_price": entry,
        "current_pnl_pips": pnl_pips,
        "max_drawdown_pips": max_dd,
        "max_profit_pips": max_pr,
        "tp_completion_pct": tp_pct,
        "minutes_open": mins_open,
    }


# ── 8. Recent decisions ───────────────────────────────────────────────────────

def _append_decision(state: dict, decision: dict) -> None:
    """Append the previous cycle's decision to recent_decisions, keep last 5."""
    if not decision:
        return
    cm = state["code_managed"]
    action = decision.get("decision", "WAIT")
    reasoning = decision.get("reasoning", "")[:80]
    confidence = decision.get("confidence", 0.0)

    cm["recent_decisions"].append({
        "cycle_time": _now_str(),
        "decision": action,
        "reason_summary": reasoning,
        "confidence": round(float(confidence), 2),
    })
    cm["recent_decisions"] = cm["recent_decisions"][-5:]


# ── 9. Economic events ────────────────────────────────────────────────────────

def _update_economic_events(state: dict, cfg) -> None:
    """Load manual economic calendar and filter today's events with minutes_until."""
    events_path = Path(getattr(cfg, "STATE_DIR", "./state")) / "economic_events.json"
    cm = state["code_managed"]

    if not events_path.exists():
        cm["economic_events_today"] = []
        return

    try:
        with open(events_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        cm["economic_events_today"] = []
        return

    now = datetime.now(timezone.utc)
    today_str = now.date().isoformat()
    result = []

    for ev in data.get("events", []):
        if ev.get("date") != today_str:
            continue
        try:
            ev_dt = datetime.strptime(
                f"{ev['date']} {ev['time']}", "%Y-%m-%d %H:%M"
            ).replace(tzinfo=timezone.utc)
            mins = round((ev_dt - now).total_seconds() / 60)
            result.append({
                "time": ev_dt.isoformat(),
                "event": ev.get("event", ""),
                "impact": ev.get("impact", "medium"),
                "minutes_until": mins,
            })
        except Exception:
            pass

    cm["economic_events_today"] = result


# ── 10. Cleanup stale items ───────────────────────────────────────────────────

def _cleanup_stale(state: dict) -> None:
    cm = state["code_managed"]

    # Swept liquidity: keep only last 3 hours
    cm["swept_liquidity_recent"] = [
        s for s in cm["swept_liquidity_recent"]
        if _hours_since(s.get("swept_at", "")) < 3
    ]

    # Mitigated POIs: keep only last 3 hours
    cm["mitigated_pois_recent"] = [
        m for m in cm["mitigated_pois_recent"]
        if _hours_since(m.get("mitigated_at", "")) < 3
    ]

    # Untaken liquidity older than 7 days: archive (drop)
    for side in ("bsl", "ssl"):
        cm["untaken_liquidity"][side] = [
            p for p in cm["untaken_liquidity"][side]
            if _days_since(p.get("created", "")) < 7
        ]

    # Active POIs: mitigated ones expire after 3h (dedup window), non-mitigated after 48h
    cm["active_pois"] = [
        p for p in cm["active_pois"]
        if (p.get("mitigated") and _hours_since(p.get("mitigated_at", "")) < 3)
        or (not p.get("mitigated") and _hours_since(p.get("created", "")) < 48)
    ]


# ── Sanity check ──────────────────────────────────────────────────────────────

def check_h4_bias_sanity(state: dict, new_bot_managed: dict) -> str | None:
    """
    Returns a warning string if H4 bias changed without a corresponding H4 CHoCH
    within the last 4 hours. Returns None if everything looks fine.
    """
    prev_bias = state["bot_managed"].get("h4_bias")
    new_bias = new_bot_managed.get("h4_bias")

    if prev_bias == new_bias:
        return None

    events = state["code_managed"].get("h4_structural_events", [])
    recent_choch = [
        e for e in events
        if e.get("type") == "CHoCH" and _hours_since(e.get("time", "")) < 4
    ]
    if not recent_choch:
        return (
            f"H4 bias changed {prev_bias!r} → {new_bias!r} but no H4 CHoCH "
            f"in last 4h found in code_managed events"
        )
    return None


# ── Main entry point ──────────────────────────────────────────────────────────

def update_code_managed_state(
    state: dict,
    context: dict,
    previous_decision: dict | None,
    cfg,
) -> dict:
    """
    Update all code-managed fields in state.
    Returns dict of changes for structured logging.
    Modifies state in-place; caller is responsible for save.
    """
    state["last_updated"] = _now_str()

    _update_session_context(state, context, cfg)
    _update_atr(state, context)

    pool_changes = _update_liquidity_pools(state, context)
    _update_distances(state, context)

    poi_changes = _update_pois(state, context)
    struct_changes = _update_structural_events(state, context)

    _update_position_metrics(state, context)
    _append_decision(state, previous_decision)
    # _update_economic_events disabled — no calendar source configured yet
    _cleanup_stale(state)

    return {
        "new_structural_events": struct_changes,
        "pools_swept":           pool_changes,
        "pois_mitigated":        poi_changes,
    }
