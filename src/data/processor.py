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
    atr_h1   = mt4.get_atr(config.SYMBOL, 14, 60)
    day_ohlc = mt4.get_day_ohlc(config.SYMBOL)
    week_hl  = mt4.get_week_hl(config.SYMBOL)
    positions = mt4.get_positions()

    candles = {
        "H4":  mt4.get_candles(config.SYMBOL, 240, config.CANDLES_H4),
        "H1":  mt4.get_candles(config.SYMBOL, 60,  config.CANDLES_H1),
        "M15": mt4.get_candles(config.SYMBOL, 15,  config.CANDLES_M15),
        "M5":  mt4.get_candles(config.SYMBOL, 5,   config.CANDLES_M5),
    }

    return {
        "timestamp": now.strftime("%Y-%m-%d %H:%M UTC"),
        "session":   session,
        "symbol":    config.SYMBOL,
        "price":     price,
        "atr_h1":    atr_h1,
        "day_ohlc":  day_ohlc,
        "week_hl":   week_hl,
        "candles":   candles,
        "positions": positions,
        "account":   account,
    }


def serialize_for_prompt(ctx: dict) -> str:
    p       = ctx["price"]
    d       = ctx["day_ohlc"]
    w       = ctx["week_hl"]
    acc     = ctx["account"]
    pos     = ctx["positions"]

    lines = [
        f"=== AURUM MARKET CONTEXT — {ctx['timestamp']} ({ctx['session']} session) ===",
        "",
        f"PRICE: Bid {p['bid']:.2f} | Ask {p['ask']:.2f} | Spread {p['spread']:.2f} | ATR(H1,14): {ctx['atr_h1']:.2f}",
        "",
        f"PREV DAY: O {d['prev_open']:.2f} H {d['prev_high']:.2f} L {d['prev_low']:.2f} C {d['prev_close']:.2f}",
        f"TODAY O: {d['today_open']:.2f}",
        f"PREV WEEK: H {w['prev_high']:.2f} L {w['prev_low']:.2f} | CURR WEEK: H {w['curr_high']:.2f} L {w['curr_low']:.2f}",
        "",
    ]

    for tf, label, count in [
        ("H4",  "H4 CANDLES",  config.CANDLES_H4),
        ("H1",  "H1 CANDLES",  config.CANDLES_H1),
        ("M15", "M15 CANDLES", config.CANDLES_M15),
        ("M5",  "M5 CANDLES",  config.CANDLES_M5),
    ]:
        candles = ctx["candles"].get(tf, [])
        lines.append(f"{label} (last {count}, oldest→newest):")
        for c in candles:
            lines.append(f"{c['time']} | O:{c['open']:.2f} H:{c['high']:.2f} L:{c['low']:.2f} C:{c['close']:.2f}")
        lines.append("")

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

    lines.append(
        f"ACCOUNT: Balance {acc['balance']:.2f} {acc['currency']}"
        f" | Equity {acc['equity']:.2f}"
        f" | Free margin {acc['free_margin']:.2f}"
    )

    return "\n".join(lines)
