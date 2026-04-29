from bridge.mt4_client import MT4Client


# XAUUSD pip values
_PIP_SIZE      = 0.10   # 1 pip = $0.10 per 0.01 lot
_LOTS_MIN      = 0.01
_LOTS_MAX      = 5.00
_MIN_CONFIDENCE = 0.60
_DD_GUARD       = 0.95  # equity / balance threshold


def execute(decision: dict, context: dict, mt4: MT4Client, cfg) -> str:
    action = decision.get("decision", "WAIT").upper()
    acc    = context["account"]
    pos    = context["positions"]
    symbol = cfg.SYMBOL

    # Confidence gate
    confidence = float(decision.get("confidence", 0.0))
    if confidence < _MIN_CONFIDENCE and action not in ("CLOSE", "HOLD", "WAIT"):
        return f"WAIT: confidence {confidence:.2f} < {_MIN_CONFIDENCE}"

    if action == "WAIT" or action == "HOLD":
        return f"{action}: no action"

    if action == "CLOSE":
        ticket = decision.get("ticket_to_close")
        if ticket:
            ok = mt4.close(int(ticket))
            return f"CLOSE ticket={ticket} ok={ok}"
        # Close all positions with our magic number
        closed = []
        for p in pos:
            if mt4.close(p["ticket"]):
                closed.append(str(p["ticket"]))
        return f"CLOSE all: {', '.join(closed) or 'none'}"

    if action not in ("BUY", "SELL"):
        return f"WAIT: unknown action '{action}'"

    # Drawdown guard
    balance = acc["balance"]
    equity  = acc["equity"]
    if balance > 0 and equity < balance * _DD_GUARD:
        return f"WAIT: drawdown guard equity={equity:.2f} balance={balance:.2f}"

    # Max open trades
    if len(pos) >= cfg.MAX_OPEN_TRADES:
        return f"WAIT: max open trades ({cfg.MAX_OPEN_TRADES}) reached"

    # SL validation
    sl = decision.get("sl", 0.0)
    tp = decision.get("tp", 0.0)
    if not sl or sl <= 0:
        return "WAIT: no valid SL provided"

    ask = context["price"]["ask"]
    bid = context["price"]["bid"]
    entry = ask if action == "BUY" else bid

    sl_pips = abs(entry - sl) / _PIP_SIZE
    if sl_pips < cfg.MIN_SL_PIPS:
        return f"WAIT: SL too tight ({sl_pips:.1f} pips < {cfg.MIN_SL_PIPS})"
    if sl_pips > cfg.MAX_SL_PIPS:
        return f"WAIT: SL too wide ({sl_pips:.1f} pips > {cfg.MAX_SL_PIPS})"

    # Broker stop level
    try:
        stop_level = mt4.get_stoplevel(symbol)
        stop_pips  = stop_level / _PIP_SIZE
        if sl_pips < stop_pips:
            return f"WAIT: SL {sl_pips:.1f} pips < broker stop level {stop_pips:.1f} pips"
    except Exception:
        pass  # non-fatal; proceed without broker-level check

    # Lot sizing
    risk_amount = balance * (cfg.MAX_RISK_PCT / 100.0)
    lots = risk_amount / (sl_pips * _PIP_SIZE * 100)
    lots = max(_LOTS_MIN, min(_LOTS_MAX, round(lots, 2)))

    # Execute
    try:
        if action == "BUY":
            ticket = mt4.buy(symbol, lots, sl, tp)
        else:
            ticket = mt4.sell(symbol, lots, sl, tp)
    except Exception as e:
        return f"ERROR: order rejected by MT4: {e}"

    return f"{action} executed ticket={ticket} lots={lots} sl={sl:.2f} tp={tp:.2f}"
