"""Validates Claude's trading decisions before MT4 execution."""
import logging
from typing import Tuple, Optional, Dict, Any

from src.risk.config import RiskConfig

logger = logging.getLogger(__name__)


class OrderValidator:
    def __init__(self, config: RiskConfig):
        self.config = config

    def validate_order(
        self,
        action: Dict[str, Any],
        market_context: Dict[str, Any],
        balance: float
    ) -> Tuple[bool, str]:
        """Validate a BUY/SELL action before execution.
        Returns (ok, reason). If ok=False, reason explains the rejection.
        """
        side = action.get("action")  # "BUY" or "SELL"
        sl = action.get("sl")
        tp = action.get("tp")
        lots = action.get("lots")
        price_data = market_context.get("price") or {}
        account = market_context.get("account") or {}

        # SL presence
        if sl is None or sl == 0:
            return False, "SL is zero or missing — order rejected for safety"

        # TP presence
        if tp is None or tp == 0:
            return False, "TP is zero or missing — order rejected for safety"

        # Lots bounds
        if lots is None or lots <= 0:
            return False, f"Invalid lots: {lots}"
        if lots > self.config.max_lots:
            return False, f"Lots {lots} exceeds maximum {self.config.max_lots}"
        if lots < self.config.min_lots:
            return False, f"Lots {lots} below minimum {self.config.min_lots}"

        # Spread check (if price data available)
        spread = price_data.get("spread")
        if spread is not None and spread > self.config.max_spread_pts:
            return False, f"Spread {spread:.1f} pts exceeds max {self.config.max_spread_pts:.0f} pts"

        # SL/TP distance and R/R
        bid = price_data.get("bid")
        ask = price_data.get("ask")
        if bid is not None and ask is not None:
            if side == "BUY":
                entry = ask
                sl_dist = entry - sl
                tp_dist = tp - entry
            else:  # SELL
                entry = bid
                sl_dist = sl - entry
                tp_dist = entry - tp

            if sl_dist < self.config.min_sl_pts:
                return False, (
                    f"SL too close: {sl_dist:.2f} pts < minimum {self.config.min_sl_pts:.1f} pts"
                )
            if tp_dist <= 0:
                return False, f"TP is on the wrong side of entry (tp_dist={tp_dist:.2f})"
            rr = tp_dist / sl_dist
            if rr < self.config.min_rr_ratio:
                return False, (
                    f"R/R {rr:.2f} is below minimum {self.config.min_rr_ratio:.1f}"
                )

        # Margin check (conservative estimate)
        free_margin = account.get("free_margin")
        if free_margin is not None:
            estimated_margin = lots * 500  # ~$500 per lot conservative for XAUUSD at 1:100
            if free_margin < estimated_margin:
                return False, (
                    f"Insufficient margin: {free_margin:.0f} < {estimated_margin:.0f} estimated"
                )

        return True, "OK"

    def validate_close(self, action: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate a CLOSE action."""
        ticket = action.get("ticket")
        if not ticket:
            return False, "CLOSE action missing ticket number"
        return True, "OK"

    def validate_modify(self, action: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate a MODIFY action."""
        ticket = action.get("ticket")
        if not ticket:
            return False, "MODIFY action missing ticket number"
        sl = action.get("sl")
        tp = action.get("tp")
        if sl is None and tp is None:
            return False, "MODIFY must include at least one of sl or tp"
        return True, "OK"
