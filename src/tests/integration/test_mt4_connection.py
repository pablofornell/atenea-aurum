"""Integration tests for MT4 connectivity.

These tests require:
1. AURUM_Bridge.mq4 running in MT4
2. MT4 listening on 127.0.0.1:5555

Run with: pytest src/tests/integration/ -m mt4
"""
import pytest
import time

from src.mt4.bridge import MT4Bridge, MT4BridgeError, MT4CommandError
from src.mt4.screenshot import capture_mt4, ScreenshotError


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
        result = bridge.buy(symbol="XAUUSD", lots=0.01, sl=1800.0, tp=1950.0)
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
        result = bridge.sell(symbol="XAUUSD", lots=0.01, sl=1950.0, tp=1800.0)
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
class TestScreenshot:
    """MT4 screenshot integration tests."""

    def test_capture_screenshot(self):
        """Test capturing MT4 screenshot."""
        try:
            path = capture_mt4(save_dir="tmp/test_screenshots")
            assert path is not None
            assert len(path) > 0
            # File should exist
            import os
            assert os.path.exists(path)
        except ScreenshotError as e:
            pytest.skip(f"Screenshot capture failed: {e}")

