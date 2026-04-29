import socket
import time


class MT4Error(Exception):
    pass


class MT4ConnectionError(MT4Error):
    pass


_TF_MAP = {
    1: "M1", 5: "M5", 15: "M15", 30: "M30",
    60: "H1", 240: "H4", 1440: "D1", 10080: "W1",
}


class MT4Client:
    TIMEOUT = 10.0
    RECONNECT_DELAY = 5.0

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self._sock: socket.socket | None = None

    # ── connection ────────────────────────────────────────────────────────────

    def connect(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(self.TIMEOUT)
        try:
            self._sock.connect((self.host, self.port))
        except OSError as e:
            self._sock = None
            raise MT4ConnectionError(f"Cannot connect to MT4 at {self.host}:{self.port}: {e}") from e

    def disconnect(self):
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def _reconnect(self):
        self.disconnect()
        time.sleep(self.RECONNECT_DELAY)
        self.connect()

    # ── low-level transport ───────────────────────────────────────────────────

    def send_command(self, cmd: str) -> str:
        payload = (cmd.strip() + "\n").encode()
        for attempt in range(2):
            try:
                if self._sock is None:
                    self.connect()
                self._sock.sendall(payload)
                return self._recv_line()
            except (OSError, socket.timeout) as e:
                if attempt == 0:
                    self._reconnect()
                    continue
                raise MT4ConnectionError(f"send_command failed after reconnect: {e}") from e

    def _recv_line(self) -> str:
        buf = b""
        while True:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise MT4ConnectionError("Connection closed by MT4")
            buf += chunk
            if b"\n" in buf:
                break
        line = buf.split(b"\n")[0].decode().strip()
        if line.startswith("ERROR|"):
            raise MT4Error(line[6:])
        # Strip "OK|" prefix present on all successful MT4 responses except PONG
        if line.startswith("OK|"):
            return line[3:]
        return line

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _tf_str(minutes: int) -> str:
        return _TF_MAP.get(minutes, str(minutes))

    @staticmethod
    def _parse_candles(raw: str) -> list[dict]:
        candles = []
        for entry in raw.split(";"):
            entry = entry.strip()
            if not entry:
                continue
            parts = entry.split(",")
            if len(parts) < 5:
                continue
            candles.append({
                "time":  parts[0],
                "open":  float(parts[1]),
                "high":  float(parts[2]),
                "low":   float(parts[3]),
                "close": float(parts[4]),
            })
        return candles

    # ── high-level API ────────────────────────────────────────────────────────

    def ping(self) -> bool:
        try:
            resp = self.send_command("PING")
            return resp == "PONG"
        except MT4Error:
            return False

    def get_candles(self, symbol: str, timeframe: int, count: int) -> list[dict]:
        tf = self._tf_str(timeframe)
        resp = self.send_command(f"GET_CANDLES|{symbol}|{tf}|{count}")
        return self._parse_candles(resp)

    def get_price(self, symbol: str) -> dict:
        resp = self.send_command(f"GET_PRICE|{symbol}")
        f = resp.split(",")
        return {"bid": float(f[0]), "ask": float(f[1]), "spread": float(f[2])}

    def get_account(self) -> dict:
        resp = self.send_command("GET_ACCOUNT")
        f = resp.split(",")
        return {
            "balance":     float(f[0]),
            "equity":      float(f[1]),
            "free_margin": float(f[2]),
            "currency":    f[3],
        }

    def get_positions(self) -> list[dict]:
        resp = self.send_command("GET_POSITIONS")
        if not resp:
            return []
        positions = []
        for entry in resp.split(";"):
            entry = entry.strip()
            if not entry:
                continue
            f = entry.split(",")
            if len(f) < 7:
                continue
            # MT4 field order: ticket, type, symbol, lots, open, sl, tp, profit
            positions.append({
                "ticket": int(f[0]),
                "type":   f[1],
                "symbol": f[2],
                "lots":   float(f[3]),
                "open":   float(f[4]),
                "sl":     float(f[5]),
                "tp":     float(f[6]),
                "profit": float(f[7]) if len(f) > 7 else 0.0,
            })
        return positions

    def get_atr(self, symbol: str, period: int, timeframe: int) -> float:
        tf = self._tf_str(timeframe)
        resp = self.send_command(f"GET_ATR|{symbol}|{period}|{tf}")
        return float(resp)

    def get_day_ohlc(self, symbol: str) -> dict:
        resp = self.send_command(f"GET_DAY_OHLC|{symbol}")
        f = resp.split(",")
        return {
            "prev_open":  float(f[0]),
            "prev_high":  float(f[1]),
            "prev_low":   float(f[2]),
            "prev_close": float(f[3]),
            "today_open": float(f[4]),
        }

    def get_week_hl(self, symbol: str) -> dict:
        resp = self.send_command(f"GET_WEEK_HL|{symbol}")
        f = resp.split(",")
        return {
            "prev_high": float(f[0]),
            "prev_low":  float(f[1]),
            "curr_high": float(f[2]),
            "curr_low":  float(f[3]),
        }

    def get_stoplevel(self, symbol: str) -> float:
        resp = self.send_command(f"GET_STOPLEVEL|{symbol}")
        return float(resp)

    def buy(self, symbol: str, lots: float, sl: float, tp: float) -> int:
        resp = self.send_command(f"BUY|{symbol}|{lots}|{sl}|{tp}")
        return int(resp)

    def sell(self, symbol: str, lots: float, sl: float, tp: float) -> int:
        resp = self.send_command(f"SELL|{symbol}|{lots}|{sl}|{tp}")
        return int(resp)

    def close(self, ticket: int) -> bool:
        resp = self.send_command(f"CLOSE|{ticket}")
        return resp == "closed"

    def modify(self, ticket: int, sl: float, tp: float) -> bool:
        resp = self.send_command(f"MODIFY|{ticket}|{sl}|{tp}")
        return resp == "modified"
