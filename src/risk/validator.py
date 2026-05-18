"""
Hard validation checks applied to every LLM order before execution.
If any check fails, the order is rejected and the cycle is logged as WAIT.
"""
from __future__ import annotations


def validate_order(
    decision: dict,
    market_state: dict,
    positions: list[dict],
    ask: float,
    bid: float,
    min_rr: float = 1.3,
    tp_tolerance: float = 0.5,
) -> dict:
    """
    Run all hard checks on a BUY or SELL decision.
    Returns {"passed": bool, "checks": dict, "rejection_reason": str | None}.
    WAIT/HOLD/CLOSE decisions pass immediately with empty checks.
    """
    action = decision.get("decision", "WAIT").upper()
    if action not in ("BUY", "SELL"):
        return {"passed": True, "checks": {}, "rejection_reason": None}

    sl = float(decision.get("sl") or 0)
    tp = float(decision.get("tp") or 0)
    entry = ask if action == "BUY" else bid
    checks: dict = {}
    reasons: list[str] = []

    # R:R >= 1.3
    sl_dist = abs(entry - sl)
    tp_dist = abs(tp - entry)
    rr = round(tp_dist / sl_dist, 2) if sl_dist > 0 else 0.0
    rr_ok = rr >= min_rr
    checks["rr"] = {"ok": rr_ok, "value": rr}
    if not rr_ok:
        reasons.append(f"R:R {rr:.2f} < {min_rr}")

    # Max 1 simultaneous position
    max_pos_ok = len(positions) == 0
    checks["max_positions"] = {"ok": max_pos_ok}
    if not max_pos_ok:
        reasons.append("position already open")

    # Direction consistent with H1 bias (allow entry if CHoCH H1 confirmed)
    bm = decision.get("bot_managed_state") or {}
    h1_bias = bm.get("h1_bias", "unclear")
    h1_struct = market_state.get("structure", {}).get("H1", {})
    choch = h1_struct.get("last_choch")
    if action == "BUY":
        bias_ok = h1_bias == "bullish" or bool(choch and choch.get("direction") == "bullish")
    else:
        bias_ok = h1_bias == "bearish" or bool(choch and choch.get("direction") == "bearish")
    checks["direction_vs_bias"] = {"ok": bias_ok}
    if not bias_ok:
        reasons.append(f"{action} conflicts with h1_bias={h1_bias!r}")

    # SL beyond the most recent confirmed sweep wick
    confirmed_sweeps = [s for s in market_state.get("sweeps", []) if s.get("confirmed")]
    sl_ok = True
    if confirmed_sweeps:
        if action == "BUY":
            ssl_sweeps = [s for s in confirmed_sweeps if s.get("pool_type") == "SSL"]
            if ssl_sweeps:
                latest = max(ssl_sweeps, key=lambda s: s["sweep_time"])
                sl_ok = sl < latest["wick_extreme"]
        else:
            bsl_sweeps = [s for s in confirmed_sweeps if s.get("pool_type") == "BSL"]
            if bsl_sweeps:
                latest = max(bsl_sweeps, key=lambda s: s["sweep_time"])
                sl_ok = sl > latest["wick_extreme"]
    checks["sl_beyond_sweep"] = {"ok": sl_ok}
    if not sl_ok:
        reasons.append("SL not beyond swept extreme")

    # TP within tolerance of an intact liquidity pool
    liq = market_state.get("liquidity", {})
    all_pools = liq.get("bsl", []) + liq.get("ssl", [])
    intact = [p for p in all_pools if p.get("status") == "intact"]
    tp_ok = any(abs(p["price"] - tp) <= tp_tolerance for p in intact)
    checks["tp_at_intact_liquidity"] = {"ok": tp_ok}
    if not tp_ok:
        reasons.append(f"TP {tp:.2f} not within {tp_tolerance} of any intact pool")

    passed = all(v["ok"] for v in checks.values())
    return {
        "passed": passed,
        "checks": checks,
        "rejection_reason": "; ".join(reasons) if reasons else None,
    }
