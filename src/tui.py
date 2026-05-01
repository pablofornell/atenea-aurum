"""
AURUM TUI — Textual-based terminal interface.
Proper box-drawing character fusion via textual's layout engine.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widgets import RichLog, Static


_DECISION_COLORS: dict[str, str] = {
    "BUY":   "bright_green bold",
    "SELL":  "bright_red bold",
    "DONE":  "bright_green bold",
    "CLOSE": "yellow bold",
    "HOLD":  "yellow bold",
    "WAIT":  "white",
}


# ── Widgets ────────────────────────────────────────────────────────────────────

class _Header(Static):
    def on_mount(self) -> None:
        self.refresh_display()
        self.set_interval(1.0, self.refresh_display)

    def refresh_display(self) -> None:
        clock = datetime.now(timezone.utc).strftime("%H:%M:%S")
        t = Text(justify="center")
        t.append(" AURUM ", style="bold white on red")
        t.append("  XAUUSD · Gold/USD   ", style="white")
        t.append(clock, style="bright_cyan")
        self.update(t)


class _AccountPanel(Static):
    def on_mount(self) -> None:
        self.border_title = "ACCOUNT"
        self.update(Text("No MT4 connection", style="red italic"))

    def set_data(self, account: dict, connected: bool) -> None:
        if not connected or not account:
            self.update(Text("No MT4 connection", style="red italic"))
            return
        a = account
        t = Text()
        t.append(f"Balance  {a.get('balance', 0):.2f} {a.get('currency', '')}\n")
        t.append(f"Equity   {a.get('equity', 0):.2f}\n")
        t.append(f"Margin   {a.get('free_margin', 0):.2f}")
        self.update(t)


class _MarketPanel(Static):
    def on_mount(self) -> None:
        self.border_title = "MARKET"
        self.update(Text("No market data", style="dim italic"))

    def set_data(self, market: dict) -> None:
        if not market:
            self.update(Text("No market data", style="dim italic"))
            return
        ctx = market
        p   = ctx.get("price", {})
        d   = ctx.get("day_ohlc", {})
        t   = Text()
        t.append(f"Bid {p.get('bid', 0):.2f}  Ask {p.get('ask', 0):.2f}  Spread {p.get('spread', 0):.2f}\n")
        t.append(f"ATR(H1,14) {ctx.get('atr_h1', 0):.2f}   Session: {ctx.get('session', '-')}\n")
        t.append(f"Prev  H:{d.get('prev_high', 0):.2f}  L:{d.get('prev_low', 0):.2f}  C:{d.get('prev_close', 0):.2f}\n")
        t.append(f"Today O:{d.get('today_open', 0):.2f}")
        self.update(t)


class _StatusPanel(Static):
    def on_mount(self) -> None:
        self.border_title = "STATUS"
        self.update(Text("Starting...", style="yellow"))

    def set_data(self, state: str, sub: str) -> None:
        if "Waiting" in state or state == "OK":
            dot_style = "bright_green"
        elif "Error" in state or "error" in state:
            dot_style = "bright_red"
        else:
            dot_style = "yellow"
        t = Text()
        t.append("● ", style=dot_style)
        t.append(state, style="white bold")
        if sub:
            t.append(f"\n{sub}", style="dim")
        self.update(t)


class _PositionsPanel(Static):
    def on_mount(self) -> None:
        self.border_title = "OPEN POSITIONS  (0)"
        self.update(Text("No open positions", style="dim italic"))

    def set_data(self, positions: list) -> None:
        n = len(positions)
        self.border_title = f"OPEN POSITIONS  ({n})"
        if n:
            self.add_class("has-positions")
        else:
            self.remove_class("has-positions")
        if not positions:
            self.update(Text("No open positions", style="dim italic"))
            return
        t = Text()
        for p in positions[:3]:
            profit = p.get("profit", 0.0)
            if profit > 0:
                col = "bright_green"
            elif profit < 0:
                col = "bright_red"
            else:
                col = "white"
            line = (f"#{p['ticket']}  {p['type']}  {p['lots']} lots"
                    f"  open={p['open']:.2f}  SL={p['sl']:.2f}  TP={p['tp']:.2f}"
                    f"  P&L={p['profit']:+.2f}")
            t.append(line + "\n", style=col)
        self.update(t)


class _DecisionPanel(Static):
    def on_mount(self) -> None:
        self.border_title = "LAST DECISION"
        self.update(Text("No decisions yet", style="dim italic"))

    def set_data(self, decision: dict) -> None:
        if not decision:
            self.update(Text("No decisions yet", style="dim italic"))
            return
        d      = decision
        ts     = d.get("_ts", "")
        raw    = d.get("decision", "WAIT").upper()
        label  = "DONE" if raw == "WAIT" else raw
        reason = d.get("reasoning", "")
        t = Text(no_wrap=True, overflow="ellipsis")
        t.append(f"[{ts}]  ", style="dim")
        t.append(label, style=_DECISION_COLORS.get(label, "white"))
        t.append("  —  ", style="white")
        t.append(reason, style="white")
        self.update(t)


class _TimerPanel(Static):
    _t_start: float = 0.0
    _t_total: float = 900.0

    def on_mount(self) -> None:
        self.border_title = "NEXT CYCLE"
        self.set_interval(0.1, self._tick)

    def start_timer(self, total_secs: float) -> None:
        self._t_start = time.monotonic()
        self._t_total = max(1.0, total_secs)

    def _tick(self) -> None:
        if not self._t_start:
            return
        elapsed = min(time.monotonic() - self._t_start, self._t_total)
        total   = self._t_total
        ratio   = elapsed / total

        try:
            w = self.content_size.width
        except Exception:
            w = 80

        label  = self._fmt(int(elapsed), int(total))
        bar_w  = max(5, w - len(label))
        filled = int(ratio * bar_w)

        t = Text(no_wrap=True)
        t.append(" " * filled,         style="on cyan")
        t.append(" " * (bar_w - filled))
        t.append(label,                 style="bold white")
        self.update(t)

    @staticmethod
    def _fmt(e: int, t: int) -> str:
        em, es = divmod(e, 60)
        tm, ts = divmod(t, 60)
        return f"  {em:02d}:{es:02d} / {tm:02d}:{ts:02d}"


# ── App ────────────────────────────────────────────────────────────────────────

_CSS = """
Screen {
    background: #0d0d0d;
    color: white;
    scrollbar-size: 0 0;
}

#header {
    height: 1;
    content-align: center middle;
    background: #0d0d0d;
}

#top-row {
    height: 7;
    width: 100%;
}

#account, #market, #status {
    width: 1fr;
    height: 100%;
    border: solid cyan;
    border-title-color: ansi_bright_cyan;
    padding: 0 1;
}

#positions {
    height: 5;
    border: solid cyan;
    border-title-color: ansi_bright_cyan;
    padding: 0 1;
}

#decision {
    height: 4;
    border: solid cyan;
    border-title-color: ansi_bright_cyan;
    padding: 0 1;
}

#timer {
    height: 3;
    border: solid cyan;
    border-title-color: ansi_bright_cyan;
    padding: 0 1;
}

#activity {
    height: 1fr;
    border: solid cyan;
    border-title-color: ansi_bright_cyan;
    padding: 0 1;
    scrollbar-size: 0 0;
}

#positions.has-positions {
    border: solid lime;
    border-title-color: ansi_bright_green;
}
"""


class _AurumApp(App[None]):
    CSS = _CSS

    def __init__(self, ready: threading.Event) -> None:
        super().__init__()
        self._ready_event = ready

    def compose(self) -> ComposeResult:
        yield _Header(id="header")
        with Horizontal(id="top-row"):
            yield _AccountPanel(id="account")
            yield _MarketPanel(id="market")
            yield _StatusPanel(id="status")
        yield _PositionsPanel(id="positions")
        yield _DecisionPanel(id="decision")
        yield _TimerPanel(id="timer")
        yield RichLog(id="activity", markup=True, highlight=False, wrap=False,
                      auto_scroll=True)

    def on_mount(self) -> None:
        self.query_one("#header", _Header).refresh_display()
        self.query_one("#activity").border_title = "ACTIVITY"
        self._ready_event.set()


# ── Public TUI ─────────────────────────────────────────────────────────────────

class TUI:
    def __init__(self) -> None:
        self._app: _AurumApp | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._connected = False

    # ── lifecycle ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._ready.clear()
        self._app = _AurumApp(self._ready)

        def _run() -> None:
            import signal as _sig
            _orig = _sig.signal

            def _safe(signum, handler):
                try:
                    return _orig(signum, handler)
                except ValueError:
                    pass  # signal.signal() only works in main thread; ignore here

            _sig.signal = _safe
            try:
                self._app.run()
            finally:
                _sig.signal = _orig

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5.0)

    def stop(self) -> None:
        if self._app:
            try:
                self._app.call_from_thread(self._app.exit)
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=2.0)

    # ── internal ───────────────────────────────────────────────────────────────

    def _call(self, fn) -> None:
        if self._app and self._ready.is_set():
            try:
                self._app.call_from_thread(fn)
            except Exception:
                pass

    # ── public API ─────────────────────────────────────────────────────────────

    def update_account(self, acct: dict) -> None:
        self._connected = True
        _a = acct
        self._call(lambda: self._app.query_one("#account", _AccountPanel).set_data(_a, True))

    def update_market(self, ctx: dict) -> None:
        _c = ctx
        self._call(lambda: self._app.query_one("#market", _MarketPanel).set_data(_c))

    def update_positions(self, pos: list) -> None:
        _p = list(pos)
        self._call(lambda: self._app.query_one("#positions", _PositionsPanel).set_data(_p))

    def update_decision(self, dec: dict) -> None:
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        _d = {**dec, "_ts": ts}
        self._call(lambda: self._app.query_one("#decision", _DecisionPanel).set_data(_d))

    def set_state(self, text: str, sub: str = "") -> None:
        _t, _s = text, sub
        self._call(lambda: self._app.query_one("#status", _StatusPanel).set_data(_t, _s))

    def set_disconnected(self) -> None:
        self._connected = False
        self._call(lambda: self._app.query_one("#account", _AccountPanel).set_data({}, False))

    def start_timer(self, cycle_num: int, total_secs: float) -> None:
        _ts = float(total_secs)
        self._call(lambda: self._app.query_one("#timer", _TimerPanel).start_timer(_ts))

    def log(self, msg: str, level: str = "INFO") -> None:
        ts  = datetime.now(timezone.utc).strftime("%H:%M:%S")
        lv  = level.upper()
        col = {
            "ERROR": "bright_red", "WARN": "yellow",
            "WARNING": "yellow",   "OK":   "bright_green",
        }.get(lv, "white")
        t = Text(no_wrap=True)
        t.append(f"[{ts}]  ", style="dim")
        t.append(msg, style=col)

        def _write() -> None:
            self._app.query_one("#activity", RichLog).write(t)

        self._call(_write)
