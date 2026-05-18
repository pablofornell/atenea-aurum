"""
Default state structure and bot_managed validation.
"""

SCHEMA_VERSION = 3

_VALID_BIASES = {"bullish", "bearish", "ranging", "unclear"}
_VALID_DECISIONS = {"BUY", "SELL", "WAIT", "HOLD", "CLOSE"}
_VALID_SETUP_TYPES = {
    "waiting_for_sweep", "waiting_for_choch", "waiting_for_fvg_fill",
    "waiting_for_retest", None,
}


def default_pending_setup() -> dict:
    return {
        "active": False,
        "type": None,
        "context": "",
        "target_poi_id": None,
        "target_liquidity_id": None,
        "expected_direction": None,
        "since": None,
        "invalidate_above": None,
        "invalidate_below": None,
        "invalidate_after": None,
    }


def default_bot_managed() -> dict:
    return {
        "h1_bias": "unclear",
        "h1_bias_since": None,
        "h1_bias_justification": "",
        "m15_bias": "unclear",
        "m15_bias_justification": "",
        "pending_setup": default_pending_setup(),
        "narrative": "",
    }


def default_state() -> dict:
    return {
        "last_updated": None,
        "schema_version": SCHEMA_VERSION,
        "code_managed": {
            "market_state": None,
            "open_position_metrics": {
                "ticket": None, "type": None, "entry_price": 0.0,
                "pnl_price": 0.0, "max_drawdown_price": 0.0,
                "max_profit_price": 0.0, "tp_completion_pct": 0.0,
                "opened_at": None, "minutes_open": 0,
            },
            "recent_decisions": [],
            "economic_events_today": [],
        },
        "bot_managed": default_bot_managed(),
    }


def validate_bot_managed(bm: dict) -> tuple[bool, str]:
    """Validate bot_managed dict from agent response. Returns (ok, error_msg)."""
    if not isinstance(bm, dict):
        return False, "bot_managed must be a dict"
    required = [
        "h1_bias", "h1_bias_since", "h1_bias_justification",
        "m15_bias", "m15_bias_justification", "pending_setup", "narrative",
    ]
    for key in required:
        if key not in bm:
            return False, f"missing key: {key}"
    if bm.get("h1_bias") not in _VALID_BIASES:
        return False, f"invalid h1_bias: {bm.get('h1_bias')!r}"
    if bm.get("m15_bias") not in _VALID_BIASES:
        return False, f"invalid m15_bias: {bm.get('m15_bias')!r}"
    ps = bm.get("pending_setup")
    if not isinstance(ps, dict):
        return False, "pending_setup must be a dict"
    if "active" not in ps or not isinstance(ps.get("active"), bool):
        return False, "pending_setup.active must be bool"
    return True, ""
