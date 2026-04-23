"""Circuit breaker that halts trading when loss thresholds are exceeded."""
import logging
from typing import Tuple, Optional

from src.risk.config import RiskConfig

logger = logging.getLogger(__name__)


class CircuitBreaker:
    def __init__(self, config: RiskConfig):
        self.config = config
        self._start_balance: Optional[float] = None
        self._consecutive_losses: int = 0
        self._total_trades: int = 0
        self._total_losses: int = 0
        self._tripped: bool = False
        self._trip_reason: str = ""

    def initialize(self, balance: float) -> None:
        """Call once at the start of each run with the opening balance."""
        self._start_balance = balance
        self._consecutive_losses = 0
        self._tripped = False
        self._trip_reason = ""
        logger.info(
            f"CircuitBreaker initialized: start_balance={balance:.2f}, "
            f"max_daily_loss={self.config.max_daily_loss_pct:.1f}%, "
            f"max_consecutive_losses={self.config.max_consecutive_losses}"
        )

    def record_trade(self, pnl: float) -> None:
        """Call after each confirmed trade close with its P&L."""
        self._total_trades += 1
        if pnl < 0:
            self._consecutive_losses += 1
            self._total_losses += 1
            logger.warning(
                f"Loss recorded: pnl={pnl:.2f}, "
                f"consecutive={self._consecutive_losses}/{self.config.max_consecutive_losses}"
            )
        else:
            self._consecutive_losses = 0
            logger.info(f"Win recorded: pnl={pnl:.2f}, consecutive losses reset")

    def check(self, equity: float) -> Tuple[bool, str]:
        """Check if it's safe to continue trading.
        Returns (can_trade, reason). If can_trade=False, reason explains why.
        """
        if self._tripped:
            return False, self._trip_reason

        # Consecutive loss check
        if self._consecutive_losses >= self.config.max_consecutive_losses:
            reason = (
                f"Circuit breaker: {self._consecutive_losses} consecutive losses "
                f"(max={self.config.max_consecutive_losses})"
            )
            self._trip(reason)
            return False, reason

        # Daily equity drawdown check
        if self._start_balance is not None:
            loss_pct = (self._start_balance - equity) / self._start_balance * 100
            if loss_pct >= self.config.max_daily_loss_pct:
                reason = (
                    f"Circuit breaker: equity drawdown {loss_pct:.2f}% "
                    f"exceeds max {self.config.max_daily_loss_pct:.1f}%"
                )
                self._trip(reason)
                return False, reason

        return True, "OK"

    def _trip(self, reason: str) -> None:
        self._tripped = True
        self._trip_reason = reason
        logger.critical(f"CIRCUIT BREAKER TRIPPED: {reason}")

    def reset(self) -> None:
        """Manual reset (e.g. start of new trading day)."""
        self._tripped = False
        self._trip_reason = ""
        self._consecutive_losses = 0
        logger.info("CircuitBreaker manually reset")

    def status(self) -> dict:
        return {
            "tripped": self._tripped,
            "trip_reason": self._trip_reason,
            "consecutive_losses": self._consecutive_losses,
            "total_trades": self._total_trades,
            "total_losses": self._total_losses,
            "start_balance": self._start_balance,
        }

    @property
    def is_tripped(self) -> bool:
        return self._tripped
