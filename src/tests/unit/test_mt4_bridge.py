"""Unit tests for MT4 bridge with mocked socket connections."""
import pytest
from unittest.mock import Mock, patch, MagicMock
import socket

from src.mt4.bridge import (
    MT4Bridge,
    MT4BridgeError,
    MT4ConnectionError,
    MT4CommandError,
)


class TestMT4BridgeConnection:
    """Test MT4 connection handling."""

    @patch("src.mt4.bridge.socket.socket")
    def test_connect_success(self, mock_socket_class):
        """Test successful connection to MT4."""
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock

        bridge = MT4Bridge(host="127.0.0.1", port=5555, timeout=5.0)
        result = bridge.connect()

        assert result is True
        mock_socket_class.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM)
        mock_sock.settimeout.assert_called_once_with(5.0)
        mock_sock.connect.assert_called_once_with(("127.0.0.1", 5555))

    @patch("src.mt4.bridge.socket.socket")
    def test_connect_failure(self, mock_socket_class):
        """Test connection failure."""
        mock_socket_class.return_value.connect.side_effect = socket.error("Connection refused")

        bridge = MT4Bridge(host="127.0.0.1", port=5555)
        with pytest.raises(MT4ConnectionError):
            bridge.connect()

    @patch("src.mt4.bridge.socket.socket")
    def test_ping_success(self, mock_socket_class):
        """Test PING command."""
        mock_sock = MagicMock()
        mock_file = MagicMock()
        mock_file.readline.return_value = "PONG\n"
        mock_sock.makefile.return_value = mock_file
        mock_socket_class.return_value = mock_sock

        bridge = MT4Bridge()
        bridge.connect()
        result = bridge.ping()

        assert result is True
        mock_sock.sendall.assert_called_with(b"PING\n")

    @patch("src.mt4.bridge.socket.socket")
    def test_ping_timeout(self, mock_socket_class):
        """Test PING timeout."""
        mock_sock = MagicMock()
        mock_file = MagicMock()
        mock_sock.sendall.side_effect = socket.timeout()
        mock_sock.makefile.return_value = mock_file
        mock_socket_class.return_value = mock_sock

        bridge = MT4Bridge()
        bridge.connect()
        result = bridge.ping()

        assert result is False

    @patch("src.mt4.bridge.socket.socket")
    def test_not_connected_error(self, mock_socket_class):
        """Test sending command when not connected."""
        bridge = MT4Bridge()
        result = bridge.ping()
        assert result is False


class TestMT4BridgeOrders:
    """Test order operations."""

    @patch("src.mt4.bridge.socket.socket")
    def test_buy_order_success(self, mock_socket_class):
        """Test successful BUY order."""
        mock_sock = MagicMock()
        mock_file = MagicMock()
        mock_file.readline.return_value = "OK|123456\n"
        mock_sock.makefile.return_value = mock_file
        mock_socket_class.return_value = mock_sock

        bridge = MT4Bridge()
        bridge.connect()
        result = bridge.buy(symbol="XAUUSD", lots=0.01, sl=1800.0, tp=1950.0)

        assert result["ok"] is True
        assert result["ticket"] == 123456
        mock_sock.sendall.assert_called_with(b"BUY|XAUUSD|0.01|1800.0|1950.0\n")

    @patch("src.mt4.bridge.socket.socket")
    def test_buy_order_error(self, mock_socket_class):
        """Test BUY order failure."""
        mock_sock = MagicMock()
        mock_file = MagicMock()
        mock_file.readline.return_value = "ERROR|130|Insufficient funds\n"
        mock_sock.makefile.return_value = mock_file
        mock_socket_class.return_value = mock_sock

        bridge = MT4Bridge()
        bridge.connect()
        with pytest.raises(MT4CommandError):
            bridge.buy(symbol="XAUUSD", lots=0.01, sl=1800.0, tp=1950.0)

    @patch("src.mt4.bridge.socket.socket")
    def test_sell_order_success(self, mock_socket_class):
        """Test successful SELL order."""
        mock_sock = MagicMock()
        mock_file = MagicMock()
        mock_file.readline.return_value = "OK|123457\n"
        mock_sock.makefile.return_value = mock_file
        mock_socket_class.return_value = mock_sock

        bridge = MT4Bridge()
        bridge.connect()
        result = bridge.sell(symbol="XAUUSD", lots=0.01, sl=1950.0, tp=1800.0)

        assert result["ok"] is True
        assert result["ticket"] == 123457
        mock_sock.sendall.assert_called_with(b"SELL|XAUUSD|0.01|1950.0|1800.0\n")

    @patch("src.mt4.bridge.socket.socket")
    def test_close_position_success(self, mock_socket_class):
        """Test closing a position."""
        mock_sock = MagicMock()
        mock_file = MagicMock()
        mock_file.readline.return_value = "OK|closed\n"
        mock_sock.makefile.return_value = mock_file
        mock_socket_class.return_value = mock_sock

        bridge = MT4Bridge()
        bridge.connect()
        result = bridge.close(ticket=123456)

        assert result["ok"] is True
        assert result["data"] == "closed"
        mock_sock.sendall.assert_called_with(b"CLOSE|123456\n")

    @patch("src.mt4.bridge.socket.socket")
    def test_close_position_error(self, mock_socket_class):
        """Test closing non-existent position."""
        mock_sock = MagicMock()
        mock_file = MagicMock()
        mock_file.readline.return_value = "ERROR|4108|Invalid ticket\n"
        mock_sock.makefile.return_value = mock_file
        mock_socket_class.return_value = mock_sock

        bridge = MT4Bridge()
        bridge.connect()
        with pytest.raises(MT4CommandError):
            bridge.close(ticket=999999)


class TestMT4BridgeModifications:
    """Test position modification commands."""

    @patch("src.mt4.bridge.socket.socket")
    def test_modify_sl_tp(self, mock_socket_class):
        """Test modifying SL/TP of position."""
        mock_sock = MagicMock()
        mock_file = MagicMock()
        mock_file.readline.return_value = "OK|modified\n"
        mock_sock.makefile.return_value = mock_file
        mock_socket_class.return_value = mock_sock

        bridge = MT4Bridge()
        bridge.connect()
        result = bridge.modify(ticket=123456, sl=1790.0, tp=1960.0)

        assert result["ok"] is True
        assert result["data"] == "modified"
        mock_sock.sendall.assert_called_with(b"MODIFY|123456|1790.0|1960.0\n")

    @patch("src.mt4.bridge.socket.socket")
    def test_timeframe_change(self, mock_socket_class):
        """Test changing timeframe."""
        mock_sock = MagicMock()
        mock_file = MagicMock()
        mock_file.readline.return_value = "OK|timeframe_sent\n"
        mock_sock.makefile.return_value = mock_file
        mock_socket_class.return_value = mock_sock

        bridge = MT4Bridge()
        bridge.connect()
        result = bridge.set_timeframe(symbol="XAUUSD", period="H1")

        assert result["ok"] is True
        mock_sock.sendall.assert_called_with(b"TIMEFRAME|XAUUSD|H1\n")

    @patch("src.mt4.bridge.socket.socket")
    def test_timeframe_change_multiple_periods(self, mock_socket_class):
        """Test changing to different timeframes."""
        mock_sock = MagicMock()
        mock_file = MagicMock()
        mock_file.readline.return_value = "OK|timeframe_sent\n"
        mock_sock.makefile.return_value = mock_file
        mock_socket_class.return_value = mock_sock

        bridge = MT4Bridge()
        bridge.connect()

        for period in ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"]:
            result = bridge.set_timeframe(symbol="XAUUSD", period=period)
            assert result["ok"] is True


class TestMT4BridgeStatus:
    """Test status queries."""

    @patch("src.mt4.bridge.socket.socket")
    def test_status_no_orders(self, mock_socket_class):
        """Test status with no open orders."""
        mock_sock = MagicMock()
        mock_file = MagicMock()
        mock_file.readline.return_value = "OK|0\n"
        mock_sock.makefile.return_value = mock_file
        mock_socket_class.return_value = mock_sock

        bridge = MT4Bridge()
        bridge.connect()
        result = bridge.status()

        assert result["ok"] is True
        assert result["orders_count"] == 0

    @patch("src.mt4.bridge.socket.socket")
    def test_status_with_orders(self, mock_socket_class):
        """Test status with open orders."""
        mock_sock = MagicMock()
        mock_file = MagicMock()
        mock_file.readline.return_value = "OK|3\n"
        mock_sock.makefile.return_value = mock_file
        mock_socket_class.return_value = mock_sock

        bridge = MT4Bridge()
        bridge.connect()
        result = bridge.status()

        assert result["ok"] is True
        assert result["orders_count"] == 3


class TestMT4BridgeErrorHandling:
    """Test error handling and edge cases."""

    @patch("src.mt4.bridge.socket.socket")
    def test_invalid_response_format(self, mock_socket_class):
        """Test handling of invalid response format."""
        mock_sock = MagicMock()
        mock_file = MagicMock()
        mock_file.readline.return_value = "INVALID\n"
        mock_sock.makefile.return_value = mock_file
        mock_socket_class.return_value = mock_sock

        bridge = MT4Bridge()
        bridge.connect()
        with pytest.raises(MT4CommandError):
            bridge.status()

    @patch("src.mt4.bridge.socket.socket")
    def test_empty_response(self, mock_socket_class):
        """Test handling of empty response (connection closed)."""
        mock_sock = MagicMock()
        mock_file = MagicMock()
        mock_file.readline.return_value = "\n"
        mock_sock.makefile.return_value = mock_file
        mock_socket_class.return_value = mock_sock

        bridge = MT4Bridge()
        bridge.connect()
        with pytest.raises(MT4ConnectionError):
            bridge.status()

    @patch("src.mt4.bridge.socket.socket")
    def test_invalid_ticket_format(self, mock_socket_class):
        """Test handling of invalid ticket in BUY response."""
        mock_sock = MagicMock()
        mock_file = MagicMock()
        mock_file.readline.return_value = "OK|not_a_number\n"
        mock_sock.makefile.return_value = mock_file
        mock_socket_class.return_value = mock_sock

        bridge = MT4Bridge()
        bridge.connect()
        with pytest.raises(MT4CommandError):
            bridge.buy(symbol="XAUUSD", lots=0.01, sl=1800.0, tp=1950.0)

    @patch("src.mt4.bridge.socket.socket")
    def test_socket_error_on_send(self, mock_socket_class):
        """Test handling of socket error during send."""
        mock_sock = MagicMock()
        mock_file = MagicMock()
        mock_sock.sendall.side_effect = socket.error("Connection reset")
        mock_sock.makefile.return_value = mock_file
        mock_socket_class.return_value = mock_sock

        bridge = MT4Bridge()
        bridge.connect()
        result = bridge.ping()
        assert result is False


class TestMT4BridgeContextManager:
    """Test context manager functionality."""

    @patch("src.mt4.bridge.socket.socket")
    def test_context_manager(self, mock_socket_class):
        """Test using bridge as context manager."""
        mock_sock = MagicMock()
        mock_file = MagicMock()
        mock_file.readline.return_value = "PONG\n"
        mock_sock.makefile.return_value = mock_file
        mock_socket_class.return_value = mock_sock

        with MT4Bridge() as bridge:
            result = bridge.ping()
            assert result is True

        mock_socket_class.assert_called_once()


class TestMT4BridgePaperTradingScenarios:
    """Integration scenarios for paper trading."""

    @patch("src.mt4.bridge.socket.socket")
    def test_full_trade_cycle_buy_and_close(self, mock_socket_class):
        """Test complete BUY → MODIFY → CLOSE cycle."""
        mock_sock = MagicMock()
        mock_file = MagicMock()
        mock_socket_class.return_value = mock_sock
        mock_sock.makefile.return_value = mock_file

        # Sequence of responses for each command
        responses = [
            "OK|0\n",  # STATUS: no orders initially
            "OK|123456\n",  # BUY: returns ticket
            "OK|modified\n",  # MODIFY: success
            "OK|1\n",  # STATUS: 1 order open
            "OK|closed\n",  # CLOSE: success
            "OK|0\n",  # STATUS: no orders after close
        ]
        mock_file.readline.side_effect = responses

        bridge = MT4Bridge()
        bridge.connect()

        # Check no orders initially
        status = bridge.status()
        assert status["orders_count"] == 0

        # Open BUY position
        buy_result = bridge.buy(symbol="XAUUSD", lots=0.01, sl=1800.0, tp=1950.0)
        assert buy_result["ok"] is True
        ticket = buy_result["ticket"]

        # Modify position
        modify_result = bridge.modify(ticket=ticket, sl=1810.0, tp=1960.0)
        assert modify_result["ok"] is True

        # Check order is open
        status = bridge.status()
        assert status["orders_count"] == 1

        # Close position
        close_result = bridge.close(ticket=ticket)
        assert close_result["ok"] is True

        # Verify no orders left
        status = bridge.status()
        assert status["orders_count"] == 0

    @patch("src.mt4.bridge.socket.socket")
    def test_full_trade_cycle_sell_and_close(self, mock_socket_class):
        """Test complete SELL → MODIFY → CLOSE cycle."""
        mock_sock = MagicMock()
        mock_file = MagicMock()
        mock_socket_class.return_value = mock_sock
        mock_sock.makefile.return_value = mock_file

        responses = [
            "OK|0\n",  # STATUS: no orders
            "OK|123457\n",  # SELL: returns ticket
            "OK|modified\n",  # MODIFY: success
            "OK|1\n",  # STATUS: 1 order open
            "OK|closed\n",  # CLOSE: success
            "OK|0\n",  # STATUS: no orders
        ]
        mock_file.readline.side_effect = responses

        bridge = MT4Bridge()
        bridge.connect()

        status = bridge.status()
        assert status["orders_count"] == 0

        sell_result = bridge.sell(symbol="XAUUSD", lots=0.01, sl=1950.0, tp=1800.0)
        assert sell_result["ok"] is True
        ticket = sell_result["ticket"]

        modify_result = bridge.modify(ticket=ticket, sl=1940.0, tp=1790.0)
        assert modify_result["ok"] is True

        status = bridge.status()
        assert status["orders_count"] == 1

        close_result = bridge.close(ticket=ticket)
        assert close_result["ok"] is True

        status = bridge.status()
        assert status["orders_count"] == 0

    @patch("src.mt4.bridge.socket.socket")
    def test_multiple_concurrent_positions(self, mock_socket_class):
        """Test managing multiple concurrent positions."""
        mock_sock = MagicMock()
        mock_file = MagicMock()
        mock_socket_class.return_value = mock_sock
        mock_sock.makefile.return_value = mock_file

        responses = [
            "OK|0\n",  # STATUS: initial
            "OK|111111\n",  # BUY #1
            "OK|111112\n",  # BUY #2
            "OK|2\n",  # STATUS: 2 orders
            "OK|closed\n",  # CLOSE #1
            "OK|1\n",  # STATUS: 1 order
            "OK|closed\n",  # CLOSE #2
            "OK|0\n",  # STATUS: final
        ]
        mock_file.readline.side_effect = responses

        bridge = MT4Bridge()
        bridge.connect()

        status = bridge.status()
        assert status["orders_count"] == 0

        # Open two positions
        pos1 = bridge.buy(symbol="XAUUSD", lots=0.01, sl=1800.0, tp=1950.0)
        pos2 = bridge.buy(symbol="XAUUSD", lots=0.01, sl=1805.0, tp=1955.0)

        ticket1 = pos1["ticket"]
        ticket2 = pos2["ticket"]

        status = bridge.status()
        assert status["orders_count"] == 2

        # Close first position
        bridge.close(ticket=ticket1)
        status = bridge.status()
        assert status["orders_count"] == 1

        # Close second position
        bridge.close(ticket=ticket2)
        status = bridge.status()
        assert status["orders_count"] == 0
