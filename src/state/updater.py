"""
Code-managed state updater. Runs before the agent each cycle.
All functions modify state in-place.
"""

import json
from datetime import datetime, timezone
from pathlib import Path


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


def _update_atr(state: dict, context: dict) -> None:
    atr = state["code_managed"]["atr"]
    atr["h1_atr"] = round(_compute_atr(context["candles"].get("H1", [])), 2)
    atr["m15_atr"] = round(_compute_atr(context["candles"].get("M15", [])), 2)


# ── Open position metrics ─────────────────────────────────────────────────────

def _update_position_metrics(state: dict, context: dict) -> None:
    cm = state["code_managed"]
    positions = context["positions"]
    bid = context["price"]["bid"]
    ask = context["price"]["ask"]

    if not positions:
        cm["open_position_metrics"] = {
            "ticket": None, "type": None, "entry_price": 0.0,
            "pnl_price": 0.0, "max_drawdown_price": 0.0,
            "max_profit_price": 0.0, "tp_completion_pct": 0.0,
            "opened_at": None, "minutes_open": 0,
        }
        return

    pos = positions[0]
    ticket = pos["ticket"]
    pos_type = str(pos["type"]).upper()
    entry = pos["open"]
    tp = pos["tp"]

    is_buy = pos_type in ("BUY", "0")
    if is_buy:
        pnl = round(bid - entry, 2)
        tp_dist = tp - entry if tp > entry else 0
        pnl_for_tp = bid - entry
    else:
        pnl = round(entry - ask, 2)
        tp_dist = entry - tp if tp < entry else 0
        pnl_for_tp = entry - ask

    tp_pct = round(max(0.0, min(1.0, pnl_for_tp / tp_dist)), 2) if tp_dist > 0 else 0.0

    prev = cm.get("open_position_metrics", {})
    now = _now_str()

    if prev.get("ticket") == ticket:
        opened_at = prev.get("opened_at") or now
        max_dd = min(prev.get("max_drawdown_price", 0.0), pnl)
        max_pr = max(prev.get("max_profit_price", 0.0), pnl)
    else:
        opened_at = now
        max_dd = min(0.0, pnl)
        max_pr = max(0.0, pnl)

    minutes_open = round(_minutes_since(opened_at)) if opened_at else 0

    cm["open_position_metrics"] = {
        "ticket": ticket,
        "type": pos_type,
        "entry_price": entry,
        "pnl_price": pnl,
        "max_drawdown_price": max_dd,
        "max_profit_price": max_pr,
        "tp_completion_pct": tp_pct,
        "opened_at": opened_at,
        "minutes_open": minutes_open,
    }


# ── Recent decisions ──────────────────────────────────────────────────────────

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


# ── Economic events ───────────────────────────────────────────────────────────

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

    _update_atr(state, context)
    _update_position_metrics(state, context)
    _append_decision(state, previous_decision)
    # _update_economic_events disabled — no calendar source configured yet

    return {}
