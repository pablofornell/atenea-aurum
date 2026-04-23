"""Automatic trade management: breakeven and trailing stop."""
import logging
from typing import Optional, TYPE_CHECKING

from src.risk.config import RiskConfig

if TYPE_CHECKING:
    from src.mt4.bridge import MT4Bridge
    from src.agent.feedback_logger import FeedbackLogger

logger = logging.getLogger(__name__)


class TradeManager:
    def __init__(self, config: RiskConfig):
        self.config = config
        # Track which tickets have already reached breakeven (avoid double-log)
        self._be_applied: set = set()

    def check_and_update(
        self,
        positions: list,
        market_context: dict,
        mt4_bridge: "MT4Bridge",
        flog: Optional["FeedbackLogger"] = None,
        session_id: Optional[str] = None,
    ) -> tuple:
        """Check open positions and apply breakeven/trailing if conditions met.

        Returns:
            (modified: bool, notes: str) — notes for injection into Claude's prompt.
        """
        if not positions:
            return False, ""

        price_data = market_context.get("price") or {}
        bid = price_data.get("bid")
        ask = price_data.get("ask")
        if bid is None or ask is None:
            return False, ""

        modified = False
        notes_parts = []

        for pos in positions:
            result, note = self._process_position(pos, bid, ask, mt4_bridge, flog, session_id)
            if result:
                modified = True
            if note:
                notes_parts.append(note)

        return modified, " | ".join(notes_parts)

    def _process_position(
        self,
        pos: dict,
        bid: float,
        ask: float,
        mt4_bridge: "MT4Bridge",
        flog: Optional["FeedbackLogger"],
        session_id: Optional[str],
    ) -> tuple:
        ticket = pos["ticket"]
        pos_type = pos["type"]   # "BUY" or "SELL"
        open_price = pos["open_price"]
        current_sl = pos["sl"]
        tp = pos["tp"]

        if pos_type == "BUY":
            current_price = bid
            sl_dist = open_price - current_sl  # distance from entry to SL
            profit_pts = current_price - open_price
        else:  # SELL
            current_price = ask
            sl_dist = current_sl - open_price
            profit_pts = open_price - current_price

        if sl_dist <= 0:
            logger.warning(f"TradeManager: invalid sl_dist {sl_dist:.2f} for ticket {ticket}")
            return False, ""

        r_ratio = profit_pts / sl_dist

        # — Trailing stop (higher priority than breakeven) —
        if r_ratio >= self.config.trailing_trigger_r:
            if pos_type == "BUY":
                new_sl = round(current_price - self.config.trailing_step_pts, 2)
                if new_sl > current_sl:
                    return self._modify(ticket, new_sl, tp, mt4_bridge, flog, session_id,
                                        f"Trailing stop → SL moved to {new_sl:.2f} ({r_ratio:.2f}R)")
            else:
                new_sl = round(current_price + self.config.trailing_step_pts, 2)
                if new_sl < current_sl:
                    return self._modify(ticket, new_sl, tp, mt4_bridge, flog, session_id,
                                        f"Trailing stop → SL moved to {new_sl:.2f} ({r_ratio:.2f}R)")

        # — Breakeven —
        elif r_ratio >= self.config.breakeven_trigger_r and ticket not in self._be_applied:
            buf = self.config.breakeven_buffer_pts
            if pos_type == "BUY":
                new_sl = round(open_price + buf, 2)
                if new_sl > current_sl:
                    self._be_applied.add(ticket)
                    return self._modify(ticket, new_sl, tp, mt4_bridge, flog, session_id,
                                        f"Breakeven applied → SL moved to {new_sl:.2f}")
            else:
                new_sl = round(open_price - buf, 2)
                if new_sl < current_sl:
                    self._be_applied.add(ticket)
                    return self._modify(ticket, new_sl, tp, mt4_bridge, flog, session_id,
                                        f"Breakeven applied → SL moved to {new_sl:.2f}")

        return False, ""

    def _modify(
        self, ticket, new_sl, tp, mt4_bridge, flog, session_id, note
    ) -> tuple:
        try:
            mt4_bridge.modify(ticket, new_sl, tp)
            logger.info(f"TradeManager [{ticket}]: {note}")
            if flog:
                flog.action_result(
                    session_id or "", 0, "AUTO_MODIFY", ok=True,
                    detail={"ticket": ticket, "new_sl": new_sl, "note": note}
                )
            return True, f"[AUTO] #{ticket}: {note}"
        except Exception as e:
            logger.warning(f"TradeManager [{ticket}]: modify failed: {e}")
            if flog:
                flog.action_result(
                    session_id or "", 0, "AUTO_MODIFY", ok=False,
                    detail={"ticket": ticket, "error": str(e)}
                )
            return False, ""
