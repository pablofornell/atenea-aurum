"""Integration tests for MT4 connectivity.

These tests require:
1. AURUM_Bridge.mq4 running in MT4
2. MT4 listening on 127.0.0.1:5555

Run with: pytest src/tests/integration/ -m mt4
"""
import pytest
import time

from src.mt4.bridge import MT4Bridge, MT4BridgeError, MT4CommandError


@pytest.mark.mt4
class TestMT4Bridge:
    """MT4 TCP bridge integration tests."""

    @pytest.fixture
    def bridge(self):
        """Create and connect MT4 bridge."""
        b = MT4Bridge(host="127.0.0.1", port=5555, timeout=5.0)
        b.connect()
        yield b
        b.close_connection()

    def test_connection(self):
        """Test TCP connection to MT4."""
        bridge = MT4Bridge(host="127.0.0.1", port=5555, timeout=5.0)
        assert bridge.connect() is not None
        bridge.close_connection()

    def test_ping(self, bridge):
        """Test PING command."""
        result = bridge.ping()
        assert result is True

    def test_status(self, bridge):
        """Test STATUS command (count open orders)."""
        result = bridge.status()
        assert result.get("ok") is True
        assert isinstance(result.get("orders_count"), int)

    def test_buy_order(self, bridge):
        """Test BUY order execution."""
        # Close any existing positions first
        try:
            status = bridge.status()
            orders = status.get("orders_count", 0)
            if orders > 0:
                pytest.skip("Existing positions found, skipping order test")
        except Exception:
            pass

        # Place BUY order
        result = bridge.buy(symbol="XAUUSD", lots=0.01, sl=0, tp=0)
        assert result.get("ok") is True
        ticket = result.get("ticket")
        assert isinstance(ticket, int) and ticket > 0

        # Close the order
        try:
            bridge.close(ticket)
        except Exception:
            pass

    def test_sell_order(self, bridge):
        """Test SELL order execution."""
        # Close any existing positions first
        try:
            status = bridge.status()
            orders = status.get("orders_count", 0)
            if orders > 0:
                pytest.skip("Existing positions found, skipping order test")
        except Exception:
            pass

        # Place SELL order
        result = bridge.sell(symbol="XAUUSD", lots=0.01, sl=0, tp=0)
        assert result.get("ok") is True
        ticket = result.get("ticket")
        assert isinstance(ticket, int) and ticket > 0

        # Close the order
        try:
            bridge.close(ticket)
        except Exception:
            pass

    def test_timeframe_change(self, bridge):
        """Test timeframe change command."""
        result = bridge.set_timeframe(symbol="XAUUSD", period="H1")
        assert result.get("ok") is True


@pytest.mark.mt4
class TestMT4MarketData:
    """Tests for the new market data commands (GET_POSITIONS, GET_ACCOUNT, GET_PRICE, GET_TIME)."""

    @pytest.fixture
    def bridge(self):
        b = MT4Bridge(host="127.0.0.1", port=5555, timeout=5.0)
        b.connect()
        yield b
        b.close_connection()

    def test_get_positions_returns_list(self, bridge):
        """GET_POSITIONS returns a list (empty or with positions)."""
        positions = bridge.get_positions()
        assert isinstance(positions, list)

    def test_get_positions_structure(self, bridge):
        """Each position has the required fields with correct types."""
        positions = bridge.get_positions()
        for p in positions:
            assert isinstance(p["ticket"], int)
            assert p["type"] in ("BUY", "SELL")
            assert isinstance(p["symbol"], str) and len(p["symbol"]) > 0
            assert isinstance(p["lots"], float) and p["lots"] > 0
            assert isinstance(p["open_price"], float) and p["open_price"] > 0
            assert isinstance(p["sl"], float)
            assert isinstance(p["tp"], float)
            assert isinstance(p["profit"], float)

    def test_get_account_fields(self, bridge):
        """GET_ACCOUNT returns balance, equity, free_margin and currency."""
        account = bridge.get_account()
        assert isinstance(account["balance"], float) and account["balance"] >= 0
        assert isinstance(account["equity"], float) and account["equity"] >= 0
        assert isinstance(account["free_margin"], float) and account["free_margin"] >= 0
        assert isinstance(account["currency"], str) and len(account["currency"]) > 0

    def test_get_account_equity_relation(self, bridge):
        """Equity must be within a reasonable range of balance (no extreme drawdown)."""
        account = bridge.get_account()
        if account["balance"] > 0:
            ratio = account["equity"] / account["balance"]
            assert 0.1 <= ratio <= 10.0, f"Equity/balance ratio out of range: {ratio}"

    def test_get_price_fields(self, bridge):
        """GET_PRICE returns bid, ask, spread for XAUUSD."""
        price = bridge.get_price("XAUUSD")
        assert isinstance(price["bid"], float) and price["bid"] > 0
        assert isinstance(price["ask"], float) and price["ask"] > 0
        assert isinstance(price["spread"], float) and price["spread"] >= 0

    def test_get_price_bid_less_than_ask(self, bridge):
        """Bid must always be less than ask."""
        price = bridge.get_price("XAUUSD")
        assert price["bid"] < price["ask"], (
            f"bid ({price['bid']}) >= ask ({price['ask']})"
        )

    def test_get_price_spread_matches_bid_ask(self, bridge):
        """Spread should equal ask - bid."""
        price = bridge.get_price("XAUUSD")
        calculated_spread = price["ask"] - price["bid"]
        assert abs(calculated_spread - price["spread"]) < 0.0001, (
            f"Spread mismatch: reported={price['spread']}, calculated={calculated_spread}"
        )

    def test_get_server_time_returns_string(self, bridge):
        """GET_TIME returns a non-empty string."""
        server_time = bridge.get_server_time()
        assert isinstance(server_time, str) and len(server_time) > 0

    def test_get_server_time_format(self, bridge):
        """Server time follows MT4 format YYYY.MM.DD HH:MM:SS."""
        import re
        server_time = bridge.get_server_time()
        pattern = r"^\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2}$"
        assert re.match(pattern, server_time), (
            f"Unexpected time format: '{server_time}'"
        )



