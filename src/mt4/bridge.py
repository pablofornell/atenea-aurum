"""MT4 TCP Socket Bridge — communicate with AURUM_Bridge.mq4 EA."""
import socket
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class MT4BridgeError(Exception):
    """Base exception for MT4 bridge errors."""
    pass


class MT4ConnectionError(MT4BridgeError):
    """Connection to MT4 failed or was lost."""
    pass


class MT4CommandError(MT4BridgeError):
    """Command failed on MT4 side."""
    pass


class MT4Bridge:
    """Client for TCP communication with MT4 AURUM_Bridge EA."""

    def __init__(self, host: str = "127.0.0.1", port: int = 5555, timeout: float = 5.0):
        """Initialize MT4 bridge.

        Args:
            host: IP address of MT4 (default: localhost)
            port: TCP port of AURUM_Bridge EA (default: 5555)
            timeout: Socket timeout in seconds
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None
        self.file_obj = None

    def connect(self) -> bool:
        """Connect to MT4 TCP server. Returns True on success."""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(self.timeout)
            self.sock.connect((self.host, self.port))
            self.file_obj = self.sock.makefile("r")
            logger.info(f"Connected to MT4 at {self.host}:{self.port}")
            return True
        except socket.error as e:
            logger.error(f"Failed to connect to MT4: {e}")
            self.sock = None
            self.file_obj = None
            raise MT4ConnectionError(f"Cannot connect to MT4 at {self.host}:{self.port}: {e}")

    def _send_cmd(self, cmd: str) -> str:
        """Send command and receive response. Raises MT4ConnectionError if disconnected."""
        if self.sock is None or self.file_obj is None:
            raise MT4ConnectionError("Not connected to MT4")

        try:
            self.sock.sendall((cmd + "\n").encode())
            response = self.file_obj.readline().strip()
            if not response:
                raise MT4ConnectionError("MT4 closed connection (empty response)")
            return response
        except socket.timeout:
            raise MT4ConnectionError("MT4 command timeout")
        except socket.error as e:
            raise MT4ConnectionError(f"MT4 socket error: {e}")

    def _parse_response(self, response: str) -> dict:
        """Parse MT4 response. Format: OK|data or ERROR|code|msg"""
        parts = response.split("|", 2)
        if not parts:
            raise MT4CommandError(f"Invalid response: {response}")

        status = parts[0]
        if status == "OK":
            return {"ok": True, "data": parts[1] if len(parts) > 1 else None}
        elif status == "ERROR":
            code = parts[1] if len(parts) > 1 else "unknown"
            msg = parts[2] if len(parts) > 2 else ""
            raise MT4CommandError(f"MT4 error {code}: {msg}")
        else:
            raise MT4CommandError(f"Unknown response status: {status}")

    def ping(self) -> bool:
        """Test connection to MT4. Returns True if alive."""
        try:
            response = self._send_cmd("PING")
            return response == "PONG"
        except MT4BridgeError:
            return False

    def buy(self, symbol: str, lots: float, sl: float, tp: float) -> dict:
        """Open BUY position.

        Returns:
            {"ok": True, "ticket": int}
        """
        sl = float(sl) if sl is not None and sl > 0 else 0.0
        tp = float(tp) if tp is not None and tp > 0 else 0.0
        cmd = f"BUY|{symbol}|{lots}|{sl}|{tp}"
        response = self._send_cmd(cmd)
        result = self._parse_response(response)
        if result["ok"]:
            try:
                result["ticket"] = int(result["data"])
            except (ValueError, TypeError):
                raise MT4CommandError(f"Invalid ticket in response: {result['data']}")
        return result

    def sell(self, symbol: str, lots: float, sl: float, tp: float) -> dict:
        """Open SELL position.

        Returns:
            {"ok": True, "ticket": int}
        """
        sl = float(sl) if sl is not None and sl > 0 else 0.0
        tp = float(tp) if tp is not None and tp > 0 else 0.0
        cmd = f"SELL|{symbol}|{lots}|{sl}|{tp}"
        response = self._send_cmd(cmd)
        result = self._parse_response(response)
        if result["ok"]:
            try:
                result["ticket"] = int(result["data"])
            except (ValueError, TypeError):
                raise MT4CommandError(f"Invalid ticket in response: {result['data']}")
        return result

    def close(self, ticket: int) -> dict:
        """Close position by ticket.

        Returns:
            {"ok": True, "data": "closed"}
        """
        cmd = f"CLOSE|{ticket}"
        response = self._send_cmd(cmd)
        return self._parse_response(response)

    def modify(self, ticket: int, sl: float, tp: float) -> dict:
        """Modify SL/TP of an open position.

        Returns:
            {"ok": True, "data": "modified"}
        """
        cmd = f"MODIFY|{ticket}|{sl}|{tp}"
        response = self._send_cmd(cmd)
        return self._parse_response(response)

    def set_timeframe(self, symbol: str, period: str) -> dict:
        """Change chart timeframe. Period: M1, M5, M15, M30, H1, H4, D1, W1, MN1.

        Returns:
            {"ok": True, "data": "timeframe_sent"}
        """
        cmd = f"TIMEFRAME|{symbol}|{period}"
        response = self._send_cmd(cmd)
        return self._parse_response(response)

    def status(self) -> dict:
        """Get count of open orders.

        Returns:
            {"ok": True, "orders_count": int}
        """
        response = self._send_cmd("STATUS")
        result = self._parse_response(response)
        if result["ok"]:
            try:
                result["orders_count"] = int(result["data"])
            except (ValueError, TypeError):
                result["orders_count"] = 0
        return result

    def close_connection(self):
        """Cleanup (no-op for file-based bridge)."""
        logger.info("MT4 bridge closed")

    def __enter__(self):
        """Context manager support."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager support."""
        self.close_connection()
