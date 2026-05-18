import json
from datetime import datetime, timezone

import config
from bridge.mt4_client import MT4Client


def _current_session(utc_hour: int) -> str:
    if 22 <= utc_hour or utc_hour < 7:
        return "Asia"
    if 7 <= utc_hour < 12:
        return "London"
    if 12 <= utc_hour < 17:
        return "NY"
    if 17 <= utc_hour < 22:
        return "Off"
    return "Off"


def build_context(mt4: MT4Client) -> dict:
    now = datetime.now(timezone.utc)
    session = _current_session(now.hour)

    price    = mt4.get_price(config.SYMBOL)
    account  = mt4.get_account()
    day_ohlc = mt4.get_day_ohlc(config.SYMBOL)
    week_hl  = mt4.get_week_hl(config.SYMBOL)
    positions = mt4.get_positions()

    candles = {
        "H1":  mt4.get_candles(config.SYMBOL, 60,  config.CANDLES_H1),
        "M15": mt4.get_candles(config.SYMBOL, 15,  config.CANDLES_M15),
        "M5":  mt4.get_candles(config.SYMBOL, 5,   config.CANDLES_M5),
    }

    return {
        "timestamp": now.strftime("%Y-%m-%d %H:%M UTC"),
        "session":   session,
        "symbol":    config.SYMBOL,
        "price":     price,
        "day_ohlc":  day_ohlc,
        "week_hl":   week_hl,
        "candles":   candles,
        "positions": positions,
        "account":   account,
    }


def serialize_for_prompt(
    ctx: dict,
    market_state: dict | None = None,
    last_result: str | None = None,
    bot_managed: dict | None = None,
) -> str:
    """Build the text prompt for the LLM agent."""
    p   = ctx["price"]
    acc = ctx["account"]
    pos = ctx["positions"]

    lines = [
        f"=== AURUM MARKET CONTEXT — {ctx['timestamp']} ({ctx['session']} session) ===",
        "",
        f"PRICE: Bid {p['bid']:.2f} | Ask {p['ask']:.2f} | Spread {p['spread']:.2f}",
        f"ACCOUNT: Balance {acc['balance']:.2f} {acc['currency']}"
        f" | Equity {acc['equity']:.2f} | Free margin {acc['free_margin']:.2f}",
        "",
    ]

    if pos:
        lines.append("OPEN POSITIONS:")
        for p_ in pos:
            lines.append(
                f"  ticket={p_['ticket']} {p_['type']} {p_['lots']} lots"
                f" open={p_['open']:.2f} sl={p_['sl']:.2f} tp={p_['tp']:.2f}"
                f" profit={p_['profit']:.2f}"
            )
    else:
        lines.append("OPEN POSITIONS: none")

    if last_result:
        lines.append("")
        lines.append(f"LAST CYCLE RESULT: {last_result}")

    if market_state:
        lines.append("")
        lines.append("STRUCTURAL_MARKET_STATE:")
        lines.append(json.dumps(market_state, indent=2))

    if bot_managed:
        lines.append("")
        lines.append("BOT_MEMORY:")
        lines.append(json.dumps(bot_managed, indent=2))

    return "\n".join(lines)
