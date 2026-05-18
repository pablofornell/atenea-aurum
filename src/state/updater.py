"""
Code-managed state updater. Runs before the agent each cycle.
All functions modify state in-place.
"""
from datetime import datetime, timezone
from pathlib import Path
import json

from analysis.market_structure import build_market_state


def _now_str() -> str:
    return datetime.now(timezone.utc).isoformat()


def _minutes_since(t_str: str) -> float:
    for fmt in ("%Y.%m.%d %H:%M", "%Y-%m-%d %H:%M", "%Y.%m.%d %H:%M:%S"):
        try:
            dt = datetime.strptime(t_str, fmt).replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - dt).total_seconds() / 60
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(t_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 60
    except ValueError:
        return 9999.0


def _update_market_state(state: dict, context: dict) -> None:
    """Run Layer 1: build structured_market_state and store in code_managed."""
    prev = state["code_managed"].get("market_state")
    ms = build_market_state(
        candles=context["candles"],
        price=context["price"],
        session=context["session"],
        symbol=context["symbol"],
        timestamp=context["timestamp"],
        day_ohlc=context["day_ohlc"],
        week_hl=context["week_hl"],
        prev_market_state=prev,
    )
    state["code_managed"]["market_state"] = ms


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
        tp_dist = (tp - entry) if tp > entry else 0
        pnl_for_tp = bid - entry
    else:
        pnl = round(entry - ask, 2)
        tp_dist = (entry - tp) if tp < entry else 0
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

    cm["open_position_metrics"] = {
        "ticket": ticket, "type": pos_type, "entry_price": entry,
        "pnl_price": pnl, "max_drawdown_price": max_dd,
        "max_profit_price": max_pr, "tp_completion_pct": tp_pct,
        "opened_at": opened_at,
        "minutes_open": round(_minutes_since(opened_at)) if opened_at else 0,
    }


def _append_decision(state: dict, decision: dict | None) -> None:
    if not decision:
        return
    cm = state["code_managed"]
    cm["recent_decisions"].append({
        "cycle_time": _now_str(),
        "decision": decision.get("decision", "WAIT"),
        "reason_summary": decision.get("reasoning", "")[:80],
        "confidence": round(float(decision.get("confidence", 0.0)), 2),
    })
    cm["recent_decisions"] = cm["recent_decisions"][-5:]


def update_code_managed_state(
    state: dict,
    context: dict,
    previous_decision: dict | None,
    cfg,
) -> dict:
    """
    Update all code-managed fields. Modifies state in-place.
    Returns dict of changes for structured logging.
    """
    state["last_updated"] = _now_str()
    _update_market_state(state, context)
    _update_position_metrics(state, context)
    _append_decision(state, previous_decision)
    return {}
