"""Pre-entry market filters — applied before calling Claude when no position is open.

All filters are deterministic (no LLM involved). They prevent unnecessary Claude calls
during unfavorable market conditions (low liquidity, extreme spread, flat ATR).
CLOSE and MODIFY actions on existing positions bypass these filters entirely.
"""
import logging
from typing import Tuple, List, Dict, Any

from src.risk.config import RiskConfig

logger = logging.getLogger(__name__)

# Sessions where new position entries are not attempted
BLOCKED_ENTRY_SESSIONS = ("Asia", "Late NY")


class EntryFilters:
    """Deterministic gates for new position entries.

    Only call all_pass() when there is NO open position. Existing positions
    are managed by TradeManager and Claude regardless of filter state.
    """

    def __init__(self, min_atr_pts: float = 8.0):
        """
        Args:
            min_atr_pts: Minimum ATR(14) in price points to allow entries.
                         Below this, the market is considered too flat for directional trades.
        """
        self.min_atr_pts = min_atr_pts

    def check_session(self, session_name: str) -> Tuple[bool, str]:
        """Block new entries during low-liquidity sessions.

        Blocked: Asia (00:00-07:00 UTC), Late NY (22:00-00:00 UTC).
        Allowed: London Open, London, London/NY Overlap, New York.
        """
        for blocked in BLOCKED_ENTRY_SESSIONS:
            if blocked in session_name:
                return False, (
                    f"Session '{session_name}' — new entries blocked (low liquidity). "
                    "Wait for London Open or NY Open Kill Zone."
                )
        return True, "OK"

    def check_atr(self, atr: float) -> Tuple[bool, str]:
        """Block entries when ATR(14) signals an extremely flat market."""
        if atr < self.min_atr_pts:
            return False, (
                f"ATR(14)={atr:.2f} pts < minimum {self.min_atr_pts:.1f} pts — "
                "market too flat for directional entries (risk of false breakouts)"
            )
        return True, "OK"

    def check_spread(self, spread: float, config: RiskConfig) -> Tuple[bool, str]:
        """Block entries when spread is too wide (e.g. news events, thin market)."""
        if spread > config.max_spread_pts:
            return False, (
                f"Spread {spread:.1f} pts > max {config.max_spread_pts:.0f} pts — "
                "likely high-volatility event or thin market. Skip this cycle."
            )
        return True, "OK"

    def all_pass(
        self,
        market_context: Dict[str, Any],
        session_name: str,
        config: RiskConfig,
    ) -> Tuple[bool, List[str]]:
        """Run all filters and return a combined verdict.

        Args:
            market_context: Dict with keys 'price', 'atr', 'account', 'positions', etc.
            session_name: Current session name (from AurumAgent._trading_session())
            config: Risk configuration with max_spread_pts

        Returns:
            (all_passed: bool, failures: list[str])
            If all_passed is False, failures contains one or more human-readable reasons.
        """
        failures: List[str] = []

        # Session filter
        ok, reason = self.check_session(session_name)
        if not ok:
            failures.append(reason)
            # Session is the most decisive filter — no need to check others
            logger.info(f"EntryFilters blocked: {reason}")
            return False, failures

        # ATR filter
        atr = market_context.get("atr")
        if atr is not None:
            ok, reason = self.check_atr(atr)
            if not ok:
                failures.append(reason)

        # Spread filter (early exit before Claude call)
        price_data = market_context.get("price") or {}
        spread = price_data.get("spread")
        if spread is not None:
            ok, reason = self.check_spread(spread, config)
            if not ok:
                failures.append(reason)

        if failures:
            for f in failures:
                logger.info(f"EntryFilters blocked: {f}")

        return len(failures) == 0, failures
