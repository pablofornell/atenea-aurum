"""Position size calculator based on risk percentage and SL distance."""
import logging
from src.risk.config import RiskConfig

logger = logging.getLogger(__name__)

# For XAUUSD standard lot: 1 price point move = $10 per lot (100 oz × $0.10/oz/point)
XAUUSD_POINT_VALUE_PER_LOT = 10.0


def calculate_lots(
    balance: float,
    sl_pts: float,
    config: RiskConfig,
    point_value: float = XAUUSD_POINT_VALUE_PER_LOT,
) -> float:
    """Calculate position size based on fixed risk percentage.

    Args:
        balance: Account balance in USD
        sl_pts: Distance from entry to stop loss in price points
        config: Risk configuration
        point_value: USD value per lot per 1-point move (default XAUUSD = 10)

    Returns:
        Calculated lots, clamped to [min_lots, max_lots] and rounded to 2 decimal places.
    """
    if sl_pts <= 0 or balance <= 0:
        logger.warning(f"Invalid inputs for position sizer: balance={balance}, sl_pts={sl_pts}")
        return config.min_lots

    risk_amount = balance * config.risk_per_trade_pct / 100.0
    raw_lots = risk_amount / (sl_pts * point_value)
    clamped = max(config.min_lots, min(config.max_lots, raw_lots))
    result = round(clamped, 2)

    logger.info(
        f"Position sizer: balance={balance:.0f}, risk={config.risk_per_trade_pct}%, "
        f"sl={sl_pts:.1f}pts → raw={raw_lots:.4f}, clamped={result:.2f} lots"
    )
    return result
