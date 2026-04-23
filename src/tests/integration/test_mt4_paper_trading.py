"""Integration tests for paper trading on real MT4 account.

These tests require:
1. AURUM_Bridge.mq4 running in MT4
2. MT4 listening on 127.0.0.1:5555
3. Paper trading account with no open positions
4. Enough balance for trades

Run with: pytest src/tests/integration/test_mt4_paper_trading.py -v -s
"""
import pytest
import time
from src.mt4.bridge import MT4Bridge, MT4ConnectionError, MT4CommandError


@pytest.mark.mt4
class TestMT4PaperTrading:
    """Real MT4 paper trading integration tests."""

    @pytest.fixture
    def bridge(self):
        """Create and connect MT4 bridge."""
        b = MT4Bridge(host="127.0.0.1", port=5555, timeout=5.0)
        b.connect()

        # Ensure clean state: close any existing positions
        status = b.status()
        orders = status.get("orders_count", 0)

        if orders > 0:
            pytest.skip("Found {} existing orders, please close them first".format(orders))

        yield b
        b.close_connection()

    def test_simple_buy_no_sl_tp(self, bridge):
        """Test BUY order without SL/TP (should succeed)."""
        result = bridge.buy(symbol="XAUUSD", lots=0.01, sl=0, tp=0)

        assert result["ok"] is True
        ticket = result["ticket"]
        assert isinstance(ticket, int)
        assert ticket > 0

        # Verify order opened
        status = bridge.status()
        assert status["orders_count"] == 1

        # Clean up
        bridge.close(ticket)

    def test_simple_sell_no_sl_tp(self, bridge):
        """Test SELL order without SL/TP."""
        result = bridge.sell(symbol="XAUUSD", lots=0.01, sl=0, tp=0)

        assert result["ok"] is True
        ticket = result["ticket"]
        assert isinstance(ticket, int)
        assert ticket > 0

        status = bridge.status()
        assert status["orders_count"] == 1

        bridge.close(ticket)

    def test_buy_with_none_sl_tp(self, bridge):
        """Test BUY with None SL/TP (should convert to 0)."""
        result = bridge.buy(symbol="XAUUSD", lots=0.01, sl=None, tp=None)

        assert result["ok"] is True
        ticket = result["ticket"]

        bridge.close(ticket)

    def test_buy_modify_close_cycle(self, bridge):
        """Test complete cycle: BUY -> CLOSE."""
        # Open position
        buy_result = bridge.buy(symbol="XAUUSD", lots=0.01, sl=0, tp=0)
        assert buy_result["ok"] is True
        ticket = buy_result["ticket"]

        # Verify opened
        status = bridge.status()
        assert status["orders_count"] == 1

        # Close
        close_result = bridge.close(ticket=ticket)
        assert close_result["ok"] is True

        # Verify closed
        status = bridge.status()
        assert status["orders_count"] == 0

    def test_sell_close_cycle(self, bridge):
        """Test SELL -> CLOSE cycle."""
        sell_result = bridge.sell(symbol="XAUUSD", lots=0.01, sl=0, tp=0)
        assert sell_result["ok"] is True
        ticket = sell_result["ticket"]

        status = bridge.status()
        assert status["orders_count"] == 1

        close_result = bridge.close(ticket=ticket)
        assert close_result["ok"] is True

        status = bridge.status()
        assert status["orders_count"] == 0

    def test_multiple_concurrent_positions(self, bridge):
        """Test multiple concurrent positions."""
        positions = []

        # Open 2 BUY positions
        for i in range(2):
            result = bridge.buy(symbol="XAUUSD", lots=0.01, sl=0, tp=0)
            assert result["ok"] is True
            positions.append(result["ticket"])
            time.sleep(0.5)

        # Verify both open
        status = bridge.status()
        assert status["orders_count"] == 2

        # Close all
        for ticket in positions:
            bridge.close(ticket=ticket)
            time.sleep(0.5)

        status = bridge.status()
        assert status["orders_count"] == 0

    def test_different_lot_sizes(self, bridge):
        """Test different lot sizes."""
        lot_sizes = [0.01, 0.1, 1.0]

        for lot in lot_sizes:
            result = bridge.buy(symbol="XAUUSD", lots=lot, sl=0, tp=0)
            assert result["ok"] is True
            ticket = result["ticket"]

            # Verify
            status = bridge.status()
            assert status["orders_count"] == 1

            # Close
            bridge.close(ticket=ticket)

            status = bridge.status()
            assert status["orders_count"] == 0

            time.sleep(0.5)

    def test_timeframe_switching(self, bridge):
        """Test switching between timeframes."""
        timeframes = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]

        for tf in timeframes:
            result = bridge.set_timeframe(symbol="XAUUSD", period=tf)
            assert result["ok"] is True

    def test_connection_persistence(self, bridge):
        """Test that connection persists across multiple commands."""
        # Send many commands without reconnecting
        for i in range(10):
            result = bridge.ping()
            assert result is True

    def test_order_lifecycle_with_balance_check(self, bridge):
        """Test order lifecycle while checking status."""
        # Check initial balance/status
        status1 = bridge.status()
        initial_orders = status1["orders_count"]

        # Place order
        buy_result = bridge.buy(symbol="XAUUSD", lots=0.01, sl=0, tp=0)
        assert buy_result["ok"] is True
        ticket = buy_result["ticket"]

        # Check status
        status2 = bridge.status()
        assert status2["orders_count"] == initial_orders + 1

        # Close order
        bridge.close(ticket=ticket)

        # Check final status
        status3 = bridge.status()
        assert status3["orders_count"] == initial_orders

    @pytest.mark.slow
    def test_rapid_order_placement(self, bridge):
        """Test rapid order placement and closure."""
        for i in range(5):
            result = bridge.buy(symbol="XAUUSD", lots=0.01, sl=0, tp=0)
            if result["ok"]:
                bridge.close(ticket=result["ticket"])
                time.sleep(0.1)

        # Ensure clean
        status = bridge.status()
        assert status["orders_count"] == 0
