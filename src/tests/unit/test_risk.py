"""Unit tests for the risk management modules."""
import pytest
from src.risk.config import RiskConfig
from src.risk.validator import OrderValidator
from src.risk.circuit_breaker import CircuitBreaker
from src.risk.position_sizer import calculate_lots, XAUUSD_POINT_VALUE_PER_LOT
from src.agent.filters import EntryFilters


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def config():
    return RiskConfig(
        risk_per_trade_pct=1.0,
        max_lots=0.50,
        min_lots=0.01,
        min_sl_pts=10.0,
        min_rr_ratio=1.5,
        max_spread_pts=30.0,
        max_daily_loss_pct=3.0,
        max_consecutive_losses=3,
        breakeven_trigger_r=1.0,
        trailing_trigger_r=2.0,
        trailing_step_pts=10.0,
    )


@pytest.fixture
def validator(config):
    return OrderValidator(config)


@pytest.fixture
def cb(config):
    return CircuitBreaker(config)


@pytest.fixture
def filters():
    return EntryFilters(min_atr_pts=8.0)


def _market_context(bid=4700.0, ask=4700.50, spread=5.0,
                     balance=4500.0, equity=4500.0, free_margin=4000.0,
                     atr=18.0, positions=None):
    return {
        "price": {"bid": bid, "ask": ask, "spread": spread},
        "account": {"balance": balance, "equity": equity, "free_margin": free_margin},
        "atr": atr,
        "positions": positions or [],
        "server_time": "2026.04.23 14:00:00",
    }


# ─── OrderValidator ───────────────────────────────────────────────────────────

class TestOrderValidator:

    def test_valid_buy_passes(self, validator):
        # BUY at ask=4700.50, sl=4680 (dist=20.5), tp=4740 (dist=39.5) → R/R=1.93 → passes
        action = {"action": "BUY", "sl": 4680.0, "tp": 4740.0, "lots": 0.10}
        ctx = _market_context(bid=4700.0, ask=4700.50)
        ok, reason = validator.validate_order(action, ctx, balance=4500.0)
        assert ok, f"Expected OK but got: {reason}"

    def test_valid_sell_passes(self, validator):
        # SELL at bid=4700.0, sl=4730 (dist=30), tp=4655 (dist=45) → R/R=1.5 → passes (not < 1.5)
        action = {"action": "SELL", "sl": 4730.0, "tp": 4655.0, "lots": 0.10}
        ctx = _market_context(bid=4700.0, ask=4700.50)
        ok, reason = validator.validate_order(action, ctx, balance=4500.0)
        assert ok, f"Expected OK but got: {reason}"

    def test_sl_zero_rejected(self, validator):
        action = {"action": "BUY", "sl": 0, "tp": 4750.0, "lots": 0.10}
        ok, reason = validator.validate_order(action, _market_context(), balance=4500.0)
        assert not ok
        assert "SL" in reason

    def test_sl_none_rejected(self, validator):
        action = {"action": "BUY", "sl": None, "tp": 4750.0, "lots": 0.10}
        ok, reason = validator.validate_order(action, _market_context(), balance=4500.0)
        assert not ok

    def test_tp_zero_rejected(self, validator):
        action = {"action": "BUY", "sl": 4680.0, "tp": 0, "lots": 0.10}
        ok, reason = validator.validate_order(action, _market_context(), balance=4500.0)
        assert not ok
        assert "TP" in reason

    def test_lots_too_high_rejected(self, validator):
        action = {"action": "BUY", "sl": 4680.0, "tp": 4730.0, "lots": 2.0}
        ok, reason = validator.validate_order(action, _market_context(), balance=4500.0)
        assert not ok
        assert "0.5" in reason or "maximum" in reason.lower() or "exceeds" in reason.lower()

    def test_lots_too_low_rejected(self, validator):
        action = {"action": "BUY", "sl": 4680.0, "tp": 4730.0, "lots": 0.001}
        ok, reason = validator.validate_order(action, _market_context(), balance=4500.0)
        assert not ok

    def test_rr_too_low_rejected(self, validator):
        # BUY at ask=4700.50, sl=4685.50 (dist=15, passes min_sl=10), tp=4718 (dist=17.5) → R/R=1.17 → rejected
        action = {"action": "BUY", "sl": 4685.50, "tp": 4718.0, "lots": 0.10}
        ctx = _market_context(ask=4700.50)
        ok, reason = validator.validate_order(action, ctx, balance=4500.0)
        assert not ok
        assert "R/R" in reason or "ratio" in reason.lower()

    def test_sl_too_close_rejected(self, validator):
        # SL dist = 4700.5 - 4696 = 4.5 < min_sl_pts (10.0) → rejected
        action = {"action": "BUY", "sl": 4696.0, "tp": 4750.0, "lots": 0.10}
        ctx = _market_context(ask=4700.50)
        ok, reason = validator.validate_order(action, ctx, balance=4500.0)
        assert not ok
        assert "close" in reason.lower() or "minimum" in reason.lower()

    def test_spread_too_wide_rejected(self, validator):
        action = {"action": "BUY", "sl": 4680.0, "tp": 4730.0, "lots": 0.10}
        ctx = _market_context(spread=50.0)
        ok, reason = validator.validate_order(action, ctx, balance=4500.0)
        assert not ok
        assert "spread" in reason.lower()

    def test_validate_close_with_ticket(self, validator):
        ok, _ = validator.validate_close({"ticket": 12345})
        assert ok

    def test_validate_close_missing_ticket(self, validator):
        ok, reason = validator.validate_close({"ticket": None})
        assert not ok

    def test_validate_modify_with_sl(self, validator):
        ok, _ = validator.validate_modify({"ticket": 12345, "sl": 4690.0, "tp": None})
        assert ok

    def test_validate_modify_missing_ticket(self, validator):
        ok, reason = validator.validate_modify({"ticket": None, "sl": 4690.0, "tp": None})
        assert not ok

    def test_validate_modify_no_sl_no_tp(self, validator):
        ok, reason = validator.validate_modify({"ticket": 12345, "sl": None, "tp": None})
        assert not ok


# ─── CircuitBreaker ───────────────────────────────────────────────────────────

class TestCircuitBreaker:

    def test_initial_state_allows_trading(self, cb):
        cb.initialize(4500.0)
        ok, reason = cb.check(4500.0)
        assert ok

    def test_drawdown_trips_breaker(self, cb):
        cb.initialize(4500.0)
        # 3% of 4500 = 135 → equity 4365 trips it
        ok, reason = cb.check(4364.0)
        assert not ok
        assert "drawdown" in reason.lower() or "circuit" in reason.lower()

    def test_drawdown_below_threshold_ok(self, cb):
        cb.initialize(4500.0)
        # 2% loss (90), should still be OK (threshold is 3%)
        ok, reason = cb.check(4410.0)
        assert ok

    def test_consecutive_losses_trip_breaker(self, cb):
        cb.initialize(4500.0)
        cb.record_trade(-50.0)
        cb.record_trade(-50.0)
        cb.record_trade(-50.0)  # 3rd consecutive loss = trip
        ok, reason = cb.check(4350.0)
        assert not ok
        assert "consecutive" in reason.lower() or "circuit" in reason.lower()

    def test_win_resets_consecutive_counter(self, cb):
        cb.initialize(4500.0)
        cb.record_trade(-50.0)
        cb.record_trade(-50.0)
        cb.record_trade(+30.0)  # win resets counter
        cb.record_trade(-50.0)
        ok, reason = cb.check(4380.0)
        assert ok  # only 1 consecutive loss after the win

    def test_tripped_breaker_stays_tripped(self, cb):
        cb.initialize(4500.0)
        cb.check(4300.0)  # trigger drawdown trip
        ok1, _ = cb.check(4500.0)  # even with recovered equity
        assert not ok1

    def test_reset_allows_trading_again(self, cb):
        cb.initialize(4500.0)
        cb.check(4300.0)  # trip
        assert cb.is_tripped
        cb.reset()
        ok, _ = cb.check(4500.0)
        assert ok
        assert not cb.is_tripped

    def test_status_returns_dict(self, cb):
        cb.initialize(4500.0)
        s = cb.status()
        assert isinstance(s, dict)
        assert "tripped" in s
        assert "consecutive_losses" in s


# ─── PositionSizer ────────────────────────────────────────────────────────────

class TestPositionSizer:

    def test_basic_sizing(self, config):
        # balance=4500, risk=1%, sl=20pts → risk_amount=45, lots=45/(20*10)=0.225 → 0.23
        result = calculate_lots(balance=4500.0, sl_pts=20.0, config=config)
        assert result == 0.23

    def test_clamp_to_max(self, config):
        # Very tight SL would give many lots → clamped to max_lots (0.50)
        result = calculate_lots(balance=100000.0, sl_pts=5.0, config=config)
        assert result == config.max_lots

    def test_clamp_to_min(self, config):
        # Very small balance → clamped to min_lots
        result = calculate_lots(balance=10.0, sl_pts=100.0, config=config)
        assert result == config.min_lots

    def test_invalid_sl_returns_min(self, config):
        result = calculate_lots(balance=4500.0, sl_pts=0.0, config=config)
        assert result == config.min_lots

    def test_invalid_balance_returns_min(self, config):
        result = calculate_lots(balance=0.0, sl_pts=20.0, config=config)
        assert result == config.min_lots

    def test_result_has_two_decimal_places(self, config):
        result = calculate_lots(balance=4500.0, sl_pts=18.0, config=config)
        assert result == round(result, 2)

    def test_point_value_constant(self):
        assert XAUUSD_POINT_VALUE_PER_LOT == 10.0


# ─── EntryFilters ─────────────────────────────────────────────────────────────

class TestEntryFilters:

    def test_london_session_passes(self, filters, config):
        ctx = _market_context(spread=10.0, atr=15.0)
        ok, failures = filters.all_pass(ctx, "London Open", config)
        assert ok, f"Expected pass but got failures: {failures}"

    def test_ny_session_passes(self, filters, config):
        ctx = _market_context(spread=10.0, atr=15.0)
        ok, failures = filters.all_pass(ctx, "New York", config)
        assert ok

    def test_asia_session_blocked(self, filters, config):
        ctx = _market_context(spread=10.0, atr=15.0)
        ok, failures = filters.all_pass(ctx, "Asia", config)
        assert not ok
        assert any("Asia" in f or "liquidity" in f.lower() for f in failures)

    def test_late_ny_session_blocked(self, filters, config):
        ctx = _market_context(spread=10.0, atr=15.0)
        ok, failures = filters.all_pass(ctx, "Late NY", config)
        assert not ok

    def test_low_atr_blocked(self, filters, config):
        ctx = _market_context(atr=5.0, spread=10.0)
        ok, failures = filters.all_pass(ctx, "London", config)
        assert not ok
        assert any("ATR" in f or "flat" in f.lower() for f in failures)

    def test_high_spread_blocked(self, filters, config):
        ctx = _market_context(spread=50.0, atr=15.0)
        ok, failures = filters.all_pass(ctx, "London", config)
        assert not ok
        assert any("spread" in f.lower() for f in failures)

    def test_missing_atr_skips_atr_check(self, filters, config):
        ctx = _market_context(atr=None, spread=10.0)
        ctx["atr"] = None
        ok, failures = filters.all_pass(ctx, "London", config)
        assert ok  # ATR check skipped when no data

    def test_check_session_direct(self, filters):
        ok, _ = filters.check_session("London/NY Overlap")
        assert ok
        ok2, _ = filters.check_session("Asia")
        assert not ok2
