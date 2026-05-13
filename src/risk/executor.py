import math
import time

from bridge.mt4_client import MT4Client, MT4Error


_PIP_SIZE = 0.10   # 1 pip = $0.10 per 0.01 lot
_LOTS_MIN = 0.01
_LOTS_MAX = 5.00
_DD_GUARD = 0.95   # equity / balance threshold


def _parse_mt4_error(exc_msg: str) -> tuple[int, str]:
    """Parse 'ordersend_failed|4109|autotrading_disabled' → (4109, 'autotrading_disabled').
    Also handles legacy format 'ordersend_failed|4109' without name."""
    parts = exc_msg.split("|")
    try:
        code = int(parts[1])
        name = parts[2] if len(parts) > 2 else f"err_{code}"
    except (ValueError, IndexError):
        return 0, exc_msg
    return code, name


def _snap_lots(lots: float, min_lot: float, max_lot: float, lot_step: float) -> float:
    stepped = round(round(lots / lot_step) * lot_step, 2)
    return max(min_lot, min(max_lot, stepped))


def _attempt_order(
    action: str, mt4: MT4Client, symbol: str,
    lots: float, sl: float, tp: float,
    min_lot: float, max_lot: float, lot_step: float,
    fixed_lots: bool = False,
) -> tuple[int | None, float, str | None]:
    """Send BUY/SELL with retry logic for recoverable errors.
    Returns (ticket, final_lots, None) on success or (None, lots, error_msg) on failure."""

    lots = _snap_lots(lots, min_lot, max_lot, lot_step)

    for attempt in range(3):
        try:
            if action == "BUY":
                ticket = mt4.buy(symbol, lots, sl, tp)
            else:
                ticket = mt4.sell(symbol, lots, sl, tp)
            return ticket, lots, None

        except MT4Error as e:
            code, name = _parse_mt4_error(str(e))

            # ── Transient: trade context busy → wait 1.5 s and retry ─────────
            if code == 146:
                if attempt < 2:
                    time.sleep(1.5)
                    continue
                return None, lots, "ERROR: trade context busy after retries (146)"

            # ── Transient: requote / price changed → retry immediately ────────
            if code in (135, 138):
                if attempt < 2:
                    continue
                return None, lots, f"ERROR: persistent requote ({code}) — market moving too fast"

            # ── Correctable: not enough margin → halve lots and retry ─────────
            # When fixed_lots is active, FIXED_LOTS has total authority — no auto-reduction.
            if code == 134:
                if fixed_lots:
                    return None, lots, (
                        f"ERROR: insufficient margin (134) for FIXED_LOTS={lots:.2f} — "
                        f"reduce FIXED_LOTS in config or add funds"
                    )
                reduced = _snap_lots(lots / 2, min_lot, max_lot, lot_step)
                if reduced >= min_lot and reduced != lots:
                    lots = reduced
                    continue
                return None, lots, (
                    f"ERROR: insufficient margin (134) — "
                    f"retried with {lots:.2f} lots, still rejected"
                )

            # ── Correctable: invalid volume → re-snap to broker step and retry ─
            if code == 131 and attempt == 0:
                lots = _snap_lots(lots, min_lot, max_lot, lot_step)
                continue

            # ── Non-recoverable: descriptive messages for agent ───────────────
            if code == 4109:
                return None, lots, (
                    "ERROR: AutoTrading disabled in MT4 terminal (4109) — "
                    "enable it manually; no trades possible until resolved"
                )
            if code == 130:
                return None, lots, (
                    "ERROR: SL/TP rejected by broker — too close to market price (130) — "
                    "widen SL distance on next decision"
                )
            if code == 132:
                return None, lots, "ERROR: market is closed (132) — wait for market open"
            if code == 133:
                return None, lots, "ERROR: trading disabled for this symbol by broker (133)"
            if code == 136:
                return None, lots, "ERROR: no quotes available (136) — market may be illiquid"
            if code == 140:
                return None, lots, "ERROR: only long positions allowed on this account (140)"
            if code == 148:
                return None, lots, "ERROR: too many open orders on account (148)"

            return None, lots, f"ERROR: {name} ({code})"

    return None, lots, "ERROR: max retries exceeded"


def execute(
    decision: dict, context: dict, mt4: MT4Client, cfg,
    agent_closed_tickets: set[int] | None = None,
) -> str:
    action = decision.get("decision", "WAIT").upper()
    acc    = context["account"]
    pos    = context["positions"]
    symbol = cfg.SYMBOL

    if action in ("WAIT", "HOLD"):
        return f"{action}: no action"

    if action == "CLOSE":
        ticket = decision.get("ticket_to_close")
        if ticket:
            ticket_int = int(ticket)
            ok = mt4.close(ticket_int)
            if ok and agent_closed_tickets is not None:
                agent_closed_tickets.add(ticket_int)
            return f"CLOSE ticket={ticket} ok={ok}"
        closed = []
        for p in pos:
            if mt4.close(p["ticket"]):
                closed.append(str(p["ticket"]))
                if agent_closed_tickets is not None:
                    agent_closed_tickets.add(p["ticket"])
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

    ask   = context["price"]["ask"]
    bid   = context["price"]["bid"]
    entry = ask if action == "BUY" else bid
    sl_pips = abs(entry - sl) / _PIP_SIZE

    # TP validation and R:R check
    if not tp or tp <= 0:
        return "WAIT: no valid TP provided"
    tp_pips = abs(tp - entry) / _PIP_SIZE
    if sl_pips > 0:
        rr = tp_pips / sl_pips
        if rr < 1.3:
            return f"WAIT: R:R {rr:.2f}:1 below minimum 1.3:1 — widen TP or tighten SL"

    # Broker stop level check
    try:
        stop_pips = mt4.get_stoplevel(symbol) / _PIP_SIZE
        if sl_pips < stop_pips:
            return (
                f"ERROR: SL/TP rejected by broker — too close to market price (130) — "
                f"widen SL distance on next decision"
            )
    except Exception:
        pass

    # Symbol lot constraints from broker
    try:
        info     = mt4.get_symbol_info(symbol)
        min_lot  = info["min_lot"]
        max_lot  = info["max_lot"]
        lot_step = info["lot_step"]
    except Exception:
        min_lot, max_lot, lot_step = _LOTS_MIN, _LOTS_MAX, 0.01

    # Lot sizing
    using_fixed_lots = getattr(cfg, "FIXED_LOTS", 0.0) > 0
    if using_fixed_lots:
        lots = cfg.FIXED_LOTS
    else:
        # Capital-tier rule: 0.01 lots per 100€ of balance.
        lots = math.floor(balance / 100) * 0.01
        if lots <= 0:
            return (
                f"WAIT: insufficient capital ({balance:.2f}€) — "
                f"need at least 100€ to size a trade"
            )

    ticket, final_lots, error = _attempt_order(
        action, mt4, symbol, lots, sl, tp, min_lot, max_lot, lot_step,
        fixed_lots=using_fixed_lots,
    )
    if error:
        return error
    return f"{action} executed ticket={ticket} lots={final_lots:.2f} sl={sl:.2f} tp={tp:.2f}"
