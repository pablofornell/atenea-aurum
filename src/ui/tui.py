"""Aurum Terminal UI — rich-based live dashboard for XAUUSD trading."""
import io
import logging
import sys
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from rich import box
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text


_ACTION_COLORS: Dict[str, str] = {
    "BUY": "bold cyan",
    "SELL": "bold magenta",
    "CLOSE": "bold yellow",
    "MODIFY": "bold blue",
    "DONE": "bold green",
    "CHANGE_TIMEFRAME": "bold white",
}


class TUILogHandler(logging.Handler):
    """Routes log records into the TUI log panel instead of stdout."""

    def __init__(self, tui: "AurumTUI"):
        super().__init__()
        self._tui = tui

    def emit(self, record: logging.LogRecord):
        try:
            self._tui._add_log(record.levelname, record.getMessage())
        except Exception:
            pass


class _LiveRenderable:
    """Thin wrapper so rich calls _build_display() on every refresh tick."""

    def __init__(self, tui: "AurumTUI"):
        self._tui = tui

    def __rich__(self):
        return self._tui._build_display()


class AurumTUI:
    """Full-screen live terminal dashboard for the Aurum trading system.

    Usage:
        tui = AurumTUI()
        with tui:
            tui.set_status("Listo")
            agent.run()
    """

    def __init__(self):
        # Force UTF-8 stdout and ANSI mode to avoid cp1252 codec errors in
        # Windows Terminal when rendering Unicode block/arrow characters.
        try:
            _stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        except AttributeError:
            _stdout = sys.stdout
        self.console = Console(highlight=False, legacy_windows=False, file=_stdout)
        self._lock = threading.Lock()
        self._live: Optional[Live] = None

        # ── Market state ──────────────────────────────────────────────────
        self._account: Dict[str, Any] = {}
        self._positions: List[Dict] = []
        self._price: Dict[str, Any] = {}
        self._server_time: str = "—"

        # ── Agent state ───────────────────────────────────────────────────
        self._status: str = "Iniciando..."
        self._cycle_num: int = 0
        self._turn_num: int = 0
        self._max_turns: int = 10

        # ── Last action ───────────────────────────────────────────────────
        self._last_action_type: str = "—"
        self._last_action_reasoning: str = ""
        self._last_action_time: Optional[datetime] = None

        # ── Countdown ─────────────────────────────────────────────────────
        self._next_cycle_at: Optional[datetime] = None
        self._cycle_total: int = 900

        # ── Log ring-buffer ───────────────────────────────────────────────
        self._log_lines: List[Tuple[str, str, str]] = []  # (level, ts, msg)
        self._MAX_LOGS = 8

    # ── Public state API (all thread-safe) ────────────────────────────────

    def update_account(self, account: Optional[dict]):
        with self._lock:
            self._account = account or {}

    def update_positions(self, positions: Optional[list]):
        with self._lock:
            self._positions = positions or []

    def update_market(self, price: Optional[dict], server_time: Optional[str] = None):
        with self._lock:
            self._price = price or {}
            if server_time is not None:
                self._server_time = str(server_time)

    def set_status(self, status: str, cycle: Optional[int] = None,
                   turn: Optional[int] = None, max_turns: Optional[int] = None):
        with self._lock:
            self._status = status
            if cycle is not None:
                self._cycle_num = cycle
            if turn is not None:
                self._turn_num = turn
            if max_turns is not None:
                self._max_turns = max_turns

    def set_last_action(self, action_type: str, reasoning: str):
        with self._lock:
            self._last_action_type = action_type
            cap = 110
            self._last_action_reasoning = (
                reasoning[:cap] + "…" if len(reasoning) > cap else reasoning
            )
            self._last_action_time = datetime.now()

    def set_next_cycle(self, seconds_remaining: float, total_interval: int):
        with self._lock:
            self._next_cycle_at = datetime.now() + timedelta(seconds=seconds_remaining)
            self._cycle_total = total_interval

    def _add_log(self, level: str, message: str):
        with self._lock:
            ts = datetime.now().strftime("%H:%M:%S")
            self._log_lines.append((level, ts, message))
            if len(self._log_lines) > self._MAX_LOGS:
                self._log_lines.pop(0)

    def log(self, message: str, level: str = "INFO"):
        self._add_log(level, message)

    # ── Rendering ─────────────────────────────────────────────────────────

    def _snapshot(self) -> dict:
        with self._lock:
            return {
                "account": dict(self._account),
                "positions": list(self._positions),
                "price": dict(self._price),
                "server_time": self._server_time,
                "status": self._status,
                "cycle_num": self._cycle_num,
                "turn_num": self._turn_num,
                "max_turns": self._max_turns,
                "last_action_type": self._last_action_type,
                "last_action_reasoning": self._last_action_reasoning,
                "last_action_time": self._last_action_time,
                "next_cycle_at": self._next_cycle_at,
                "cycle_total": self._cycle_total,
                "log_lines": list(self._log_lines),
            }

    def _panel_account(self, s: dict) -> Panel:
        acc = s["account"]
        if acc:
            balance = acc.get("balance", 0.0)
            equity = acc.get("equity", 0.0)
            free_margin = acc.get("free_margin", 0.0)
            currency = acc.get("currency", "USD")
            diff = equity - balance
            eq_color = "green" if diff >= 0 else "red"
            arrow = "+" if diff >= 0 else "-"

            t = Text()
            t.append("Bal  ", style="dim")
            t.append(f"{balance:,.2f} {currency}\n", style="bold white")
            t.append("Eqt  ", style="dim")
            t.append(f"{equity:,.2f}", style=f"bold {eq_color}")
            t.append(f"  ({arrow}{abs(diff):,.2f})\n", style=eq_color)
            t.append("Mgn  ", style="dim")
            t.append(f"{free_margin:,.2f}", style="white")
        else:
            t = Text("Sin conexion MT4", style="dim red")

        return Panel(t, title="[bold]CUENTA[/bold]",
                     border_style="blue", padding=(0, 1))

    def _panel_market(self, s: dict) -> Panel:
        p = s["price"]
        if p:
            bid = p.get("bid", 0.0)
            ask = p.get("ask", 0.0)
            spread = p.get("spread", 0.0)

            t = Text()
            t.append("Bid  ", style="dim")
            t.append(f"{bid:.2f}\n", style="bold yellow")
            t.append("Ask  ", style="dim")
            t.append(f"{ask:.2f}  ", style="yellow")
            t.append(f"spr {spread:.2f}\n", style="dim")
            t.append("Hora ", style="dim")
            t.append(f"{s['server_time']}", style="dim white")
        else:
            t = Text("Sin datos de mercado", style="dim red")

        return Panel(t, title="[bold]MERCADO[/bold]",
                     border_style="blue", padding=(0, 1))

    def _panel_status(self, s: dict) -> Panel:
        status = s["status"]
        if any(x in status for x in ("Claude", "Llamando", "Analizando", "Procesando")):
            dot, dot_style = "◉", "bold yellow"
        elif any(x in status for x in ("error", "Error", "fallo", "Fallo")):
            dot, dot_style = "◉", "bold red"
        elif any(x in status for x in ("Esperando", "próximo", "Durmiendo")):
            dot, dot_style = "○", "bold cyan"
        else:
            dot, dot_style = "◉", "bold green"

        t = Text()
        t.append(f"{dot} ", style=dot_style)
        t.append(f"{status}\n", style="white")
        if s["cycle_num"] > 0:
            t.append(f"Ciclo {s['cycle_num']}", style="dim")
            if s["turn_num"] > 0:
                t.append(f"  ·  Turno {s['turn_num']}/{s['max_turns']}", style="dim")

        return Panel(t, title="[bold]ESTADO[/bold]",
                     border_style="blue", padding=(0, 1))

    def _panel_positions(self, s: dict) -> Panel:
        positions = s["positions"]
        balance = s["account"].get("balance", 0.0) if s["account"] else 0.0
        n = len(positions)
        title = f"[bold green]POSICIONES ABIERTAS  ({n})[/bold green]"

        if not positions:
            return Panel(
                Text("  Sin posiciones abiertas", style="dim italic"),
                title=title, border_style="green", padding=(0, 1),
            )

        tbl = Table(
            box=box.SIMPLE_HEAD,
            show_header=True,
            header_style="dim",
            padding=(0, 1),
            expand=True,
            show_edge=False,
        )
        tbl.add_column("#TKT", justify="right", style="dim", no_wrap=True)
        tbl.add_column("TIPO", justify="center", no_wrap=True)
        tbl.add_column("LOTS", justify="right", no_wrap=True)
        tbl.add_column("ENTRADA", justify="right", no_wrap=True)
        tbl.add_column("SL", justify="right", no_wrap=True)
        tbl.add_column("TP", justify="right", no_wrap=True)
        tbl.add_column("P&L $", justify="right", no_wrap=True)
        tbl.add_column("% BAL", justify="right", no_wrap=True)

        for pos in positions:
            profit = pos.get("profit", 0.0)
            pnl_color = "green" if profit >= 0 else "red"
            pct = (profit / balance * 100) if balance > 0 else 0.0
            pct_color = "green" if pct >= 0 else "red"
            ptype = pos.get("type", "?")
            type_color = "cyan" if ptype == "BUY" else "magenta"
            sl = pos.get("sl", 0.0)
            tp = pos.get("tp", 0.0)

            tbl.add_row(
                str(pos.get("ticket", "?")),
                Text(ptype, style=f"bold {type_color}"),
                f"{pos.get('lots', 0):.2f}",
                f"{pos.get('open_price', 0):.2f}",
                f"{sl:.2f}" if sl else "—",
                f"{tp:.2f}" if tp else "—",
                Text(f"{profit:+.2f}", style=f"bold {pnl_color}"),
                Text(f"{pct:+.3f}%", style=pct_color),
            )

        return Panel(tbl, title=title, border_style="green", padding=(0, 0))

    def _panel_last_action(self, s: dict) -> Panel:
        last_time = s["last_action_time"]
        if last_time:
            ts = last_time.strftime("%H:%M:%S")
            color = _ACTION_COLORS.get(s["last_action_type"], "white")
            t = Text()
            t.append(f"[{ts}]  ", style="dim")
            t.append(s["last_action_type"], style=color)
            if s["last_action_reasoning"]:
                t.append(f"  —  {s['last_action_reasoning']}", style="dim white")
        else:
            t = Text("Sin decisiones aún en esta sesión", style="dim italic")

        return Panel(t, title="[bold]ULTIMA DECISION[/bold]",
                     border_style="dim blue", padding=(0, 1))

    def _panel_countdown(self, s: dict) -> Panel:
        next_at = s["next_cycle_at"]
        if next_at:
            remaining = max(0.0, (next_at - datetime.now()).total_seconds())
            total = s["cycle_total"]
            progress = 1.0 - (remaining / total) if total > 0 else 1.0
            progress = max(0.0, min(1.0, progress))

            bar_w = 40
            filled = int(bar_w * progress)
            t = Text()
            t.append("█" * filled, style="bold cyan")
            t.append("░" * (bar_w - filled), style="dim blue")
            mins_r, secs_r = divmod(int(remaining), 60)
            mins_t, secs_t = divmod(total, 60)
            t.append(f"  {mins_r:02d}:{secs_r:02d}", style="bold white")
            t.append(f" / {mins_t:02d}:{secs_t:02d}", style="dim")
        else:
            t = Text("Calculando próximo ciclo…", style="dim italic")

        return Panel(t, title="[bold]PROXIMO CICLO[/bold]",
                     border_style="dim blue", padding=(0, 1))

    def _panel_log(self, s: dict) -> Panel:
        t = Text()
        for level, ts, msg in s["log_lines"]:
            if level == "ERROR":
                msg_style = "red"
            elif level == "WARNING":
                msg_style = "yellow"
            else:
                msg_style = "dim white"
            t.append(f"[{ts}]  ", style="dim")
            t.append(f"{msg}\n", style=msg_style)

        if not s["log_lines"]:
            t.append("Sin actividad reciente", style="dim italic")

        return Panel(t, title="[bold]ACTIVIDAD[/bold]",
                     border_style="dim", padding=(0, 1))

    def _build_display(self) -> Layout:
        s = self._snapshot()
        now = datetime.now().strftime("%H:%M:%S")

        header = Rule(
            title=(
                f"[bold white on dark_red] AURUM [/bold white on dark_red]"
                f"  [bold yellow]XAUUSD · Gold/USD[/bold yellow]"
                f"  [dim]{now}[/dim]"
            ),
            style="blue",
        )

        top = Layout(name="top")
        top.split_row(
            Layout(self._panel_account(s), name="account"),
            Layout(self._panel_market(s), name="market"),
            Layout(self._panel_status(s), name="status"),
        )

        root = Layout(name="root")
        # Positions panel height: 4 lines overhead + 1 per position, min 5
        pos_size = max(5, 4 + len(s["positions"]))
        root.split_column(
            Layout(header, name="header", size=1),
            Layout(top, name="top_row", size=5),
            Layout(self._panel_positions(s), name="positions", size=pos_size),
            Layout(self._panel_last_action(s), name="action", size=3),
            Layout(self._panel_countdown(s), name="countdown", size=3),
            Layout(self._panel_log(s), name="log"),
        )
        return root

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def start(self):
        # _LiveRenderable lets rich call _build_display() on every auto-refresh
        # tick instead of holding a stale snapshot. screen=False renders inline
        # (no alternate buffer), which is reliable across all Windows terminals.
        renderable = _LiveRenderable(self)
        self._live = Live(
            renderable,
            console=self.console,
            screen=False,
            auto_refresh=True,
            refresh_per_second=1,
            vertical_overflow="visible",
        )
        self._live.start()

    def stop(self):
        if self._live:
            self._live.stop()
            self._live = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()
