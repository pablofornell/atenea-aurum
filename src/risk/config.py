"""Risk management configuration for AURUM."""
from dataclasses import dataclass, field


@dataclass
class RiskConfig:
    # Position sizing
    risk_per_trade_pct: float = 1.0      # % of balance risked per trade
    max_lots: float = 0.50               # hard ceiling on position size
    min_lots: float = 0.01
    # Order validation
    min_sl_pts: float = 10.0             # minimum SL distance in price points
    min_rr_ratio: float = 1.2            # minimum risk/reward ratio
    max_spread_pts: float = 30.0         # maximum spread to accept entry
    # Circuit breaker
    max_daily_loss_pct: float = 3.0      # max equity drawdown from session start (%)
    max_consecutive_losses: int = 3      # consecutive losses before halting
    # Trade management
    breakeven_trigger_r: float = 1.0     # move SL to BE when profit >= 1R
    trailing_trigger_r: float = 2.0      # start trailing when profit >= 2R
    trailing_step_pts: float = 10.0      # trailing stop step in price points
    breakeven_buffer_pts: float = 2.0    # buffer above entry when moving to BE
    # Broker timezone
    broker_gmt_offset: int = 0           # broker server GMT offset (0=UTC, 2=EET winter, 3=EEST summer)
