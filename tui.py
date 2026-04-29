"""
AURUM TUI — pure ANSI escape codes.
No external dependencies. Works on Windows Terminal, Linux, macOS.
"""
import os
import re
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone

# ── Windows: enable VT100 processing ─────────────────────────────────────────
if os.name == "nt":
    import ctypes
    try:
        _h = ctypes.windll.kernel32.GetStdHandle(-11)
        ctypes.windll.kernel32.SetConsoleMode(_h, 7)
    except Exception:
        pass

# ── ANSI codes ────────────────────────────────────────────────────────────────
_R  = "\033[0m"   # reset
_B  = "\033[1m"   # bold
_I  = "\033[3m"   # italic
_D  = "\033[2m"   # dim

_CYAN    = "\033[36m"
_GREEN   = "\033[32m"
_RED     = "\033[31m"
_YELLOW  = "\033[33m"
_WHITE   = "\033[37m"
_BCYAN   = "\033[96m"
_BGREEN  = "\033[92m"
_BRED    = "\033[91m"
_BWHITE  = "\033[97m"
_BG_RED  = "\033[41m"
_BG_CYAN = "\033[46m"

_DEC_COLOR = {
    "BUY":  _BGREEN + _B,
    "SELL": _BRED   + _B,
    "DONE": _BGREEN + _B,
    "CLOSE":_YELLOW + _B,
    "HOLD": _YELLOW + _B,
    "WAIT": _WHITE,
}

# ── panel heights ─────────────────────────────────────────────────────────────
_H_TOP   = 7
_H_POS   = 5
_H_DEC   = 4
_H_TIMER = 3
_LOG_MAX = 500

# ── string helpers ────────────────────────────────────────────────────────────
_ANSI_RE = re.compile(r"\033\[[^m]*m")

def _vis(s: str) -> int:
    """Visible (printable) length of a string that may contain ANSI codes."""
    return len(_ANSI_RE.sub("", s))

def _vpad(s: str, w: int) -> str:
    """Pad a (possibly ANSI-styled) string to exactly w visible chars."""
    n = w - _vis(s)
    return s + " " * max(0, n)

def _clip(raw: str, w: int) -> str:
    """Clip a plain (unstyled) string to w chars."""
    if w <= 0:
        return ""
    return raw[:w] if len(raw) > w else raw

def _terminal_size() -> tuple[int, int]:
    try:
        s = os.get_terminal_size()
        return s.lines, s.columns
    except OSError:
        return 24, 80


# ── row builders ──────────────────────────────────────────────────────────────

def _border_line(width: int, title: str = "", title_style: str = "") -> str:
    """Full-width ─── TITLE ─── horizontal border."""
    seg  = f"─── {title} ───" if title else ""
    pad  = max(0, width - len(seg))
    lp   = pad // 2
    rp   = pad - lp
    line = "─" * lp + seg + "─" * rp
    line = line[:width]                         # safety clip
    if not title:
        return _CYAN + line + _R
    pre  = "─" * lp + "─── "
    post = " ───" + "─" * rp
    return _CYAN + pre[:width] + _R + title_style + _B + title + _R + _CYAN + post + _R

def _side_row(width: int, content: str = "", content_style: str = "") -> str:
    """│ content │ row for a full-width panel."""
    iw   = width - 4                            # 2 chars border+space on each side
    text = _vpad(content_style + _clip(content, iw) + (_R if content_style else ""), iw)
    return _CYAN + "│" + _R + " " + text + " " + _CYAN + "│" + _R

def _side_row_raw(width: int, raw_styled: str) -> str:
    """│ raw_styled │ — caller pre-styled content, already clipped to width-4 visible chars."""
    return _CYAN + "│" + _R + " " + _vpad(raw_styled, width - 4) + " " + _CYAN + "│" + _R

def _three_title_row(cols: int, w: int) -> str:
    """Single row with three panel titles side by side, sharing the ─ baseline."""
    def seg(title, width):
        s   = f"─── {title} ───"
        pad = max(0, width - len(s))
        lp  = pad // 2
        rp  = pad - lp
        return (_CYAN + "─" * lp + "─── " + _R
                + _BCYAN + _B + title + _R
                + _CYAN + " ───" + "─" * rp + _R)

    # widths: w, w, cols-2w  (three panels that together span cols)
    p1 = seg("CUENTA",  w)
    p2 = seg("MERCADO", w)
    p3 = seg("ESTADO",  cols - 2 * w)
    return p1 + p2 + p3

def _three_content_row(cols: int, w: int,
                        left: str, mid: str, right: str) -> str:
    """
    │ left │ mid │ right │
    Widths per inner content area:
      left  = w - 3   (│ + space + content + space, but right space is shared border)
      mid   = w - 3
      right = cols - 2w - 4
    Total visible = 1 + (w-3) + 2 + 1 + (w-3) + 2 + 1 + (cols-2w-4) + 2 + 1 = cols
    """
    lw = w - 3
    rw = cols - 2 * w - 4
    l  = " " + _vpad(left,  lw) + " "   # w-1 visible
    m  = " " + _vpad(mid,   lw) + " "   # w-1 visible
    r  = " " + _vpad(right, rw) + " "   # cols-2w-2 visible
    return (_CYAN + "│" + _R + l
          + _CYAN + "│" + _R + m
          + _CYAN + "│" + _R + r
          + _CYAN + "│" + _R)

def _three_bot_row(cols: int) -> str:
    return _CYAN + "─" * cols + _R


# ── TUI class ─────────────────────────────────────────────────────────────────

class TUI:
    def __init__(self):
        self._lock    = threading.Lock()
        self._running = False
        self._thread  : threading.Thread | None = None

        self._account   : dict  = {}
        self._market    : dict  = {}
        self._positions : list  = []
        self._decision  : dict  = {}
        self._state     : str   = "Iniciando..."
        self._sub       : str   = ""
        self._connected : bool  = False
        self._cycle_num : int   = 0
        self._t_start   : float = 0.0
        self._t_total   : float = 900.0
        self._logs      : deque = deque(maxlen=_LOG_MAX)

    # ── public API ────────────────────────────────────────────────────────────

    def update_account(self, acct: dict):
        with self._lock:
            self._account   = acct
            self._connected = True
        self._render()

    def update_market(self, ctx: dict):
        with self._lock:
            self._market = ctx
        self._render()

    def update_positions(self, pos: list):
        with self._lock:
            self._positions = pos
        self._render()

    def update_decision(self, dec: dict):
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        with self._lock:
            self._decision = {**dec, "_ts": ts}
        self._render()

    def set_state(self, text: str, sub: str = ""):
        with self._lock:
            self._state = text
            self._sub   = sub
        self._render()

    def set_disconnected(self):
        with self._lock:
            self._connected = False
            self._account   = {}
        self._render()

    def start_timer(self, cycle_num: int, total_secs: float):
        with self._lock:
            self._cycle_num = cycle_num
            self._t_start   = time.monotonic()
            self._t_total   = max(1.0, float(total_secs))
        self._render()

    def log(self, msg: str, level: str = "INFO"):
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        with self._lock:
            self._logs.append((ts, msg, level.upper()))
        self._render()

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        sys.stdout.write("\033[?1049h\033[?25l")   # alt screen + hide cursor
        sys.stdout.flush()
        self._running = True
        self._thread  = threading.Thread(target=self._tick, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        sys.stdout.write("\033[?25h\033[?1049l")   # show cursor + restore screen
        sys.stdout.flush()

    # ── rendering ─────────────────────────────────────────────────────────────

    def _tick(self):
        while self._running:
            self._render()
            time.sleep(0.1)

    def _render(self):
        with self._lock:
            rows_n, cols = _terminal_size()
            lines = self._build(rows_n, cols)
            out = "\033[H" + "\n".join(lines)
            try:
                sys.stdout.write(out)
                sys.stdout.flush()
            except OSError:
                pass

    def _build(self, rows_n: int, cols: int) -> list[str]:
        lines: list[str] = []
        w = cols // 3          # width of each of the three top panels

        # ── header ────────────────────────────────────────────────────────────
        clock  = datetime.now(timezone.utc).strftime("%H:%M:%S")
        badge  = " AURUM "
        center = "XAUUSD · Gold/USD"
        full   = badge + "  " + center + "   " + clock
        pad    = max(0, (cols - len(full)) // 2)
        hr = (" " * pad
              + _BG_RED + _BWHITE + _B + badge + _R
              + _WHITE + "  " + center + "   " + _R
              + _BCYAN + clock + _R)
        lines.append(_vpad(hr, cols))

        # ── three top panels ──────────────────────────────────────────────────
        if len(lines) + _H_TOP <= rows_n:
            lines.append(_three_title_row(cols, w))
            c_rows  = self._cuenta_rows(w)
            m_rows  = self._mercado_rows(w)
            e_rows  = self._estado_rows(cols - 2 * w)
            for i in range(_H_TOP - 2):
                lines.append(_three_content_row(
                    cols, w,
                    c_rows[i] if i < len(c_rows) else "",
                    m_rows[i] if i < len(m_rows) else "",
                    e_rows[i] if i < len(e_rows) else "",
                ))
            lines.append(_three_bot_row(cols))

        # ── positions ─────────────────────────────────────────────────────────
        if len(lines) + _H_POS <= rows_n:
            n  = len(self._positions)
            tc = _BGREEN if n else _BCYAN
            lines.append(_border_line(cols, f"POSICIONES ABIERTAS  ({n})", tc))
            content: list[str] = []
            if not self._positions:
                content.append(_side_row(cols, "Sin posiciones abiertas", _D + _I))
            else:
                for p in self._positions[:_H_POS - 2]:
                    col = _BGREEN if p.get("type") == "BUY" else _BRED
                    ln  = (f"  #{p['ticket']}  {p['type']}  {p['lots']} lots"
                           f"  open={p['open']:.2f}  SL={p['sl']:.2f}  TP={p['tp']:.2f}"
                           f"  P&L={p['profit']:+.2f}")
                    content.append(_side_row(cols, ln, col))
            while len(content) < _H_POS - 2:
                content.append(_side_row(cols))
            lines.extend(content)
            lines.append(_border_line(cols))

        # ── last decision ─────────────────────────────────────────────────────
        if len(lines) + _H_DEC <= rows_n:
            lines.append(_border_line(cols, "ULTIMA DECISION", _BCYAN))
            lines.append(_side_row(cols))
            lines.append(self._decision_row(cols))
            lines.append(_border_line(cols))

        # ── timer ─────────────────────────────────────────────────────────────
        if len(lines) + _H_TIMER <= rows_n:
            lines.append(_border_line(cols, "PROXIMO CICLO", _BCYAN))
            lines.append(self._timer_row(cols))
            lines.append(_border_line(cols))

        # ── activity log ──────────────────────────────────────────────────────
        avail = rows_n - len(lines)
        if avail >= 3:
            lines.append(_border_line(cols, "ACTIVIDAD", _BCYAN))
            log_lines = avail - 2
            entries   = list(self._logs)[-log_lines:]
            for ts, msg, level in entries:
                col = _BRED   if level == "ERROR" \
                     else _YELLOW if level in ("WARN", "WARNING") \
                     else _BGREEN if level == "OK" \
                     else _WHITE
                max_msg = cols - 4 - len(ts) - 4
                styled  = _D + f"[{ts}]  " + _R + col + _clip(msg, max_msg) + _R
                lines.append(_side_row_raw(cols, styled))
            while len(lines) < rows_n - 1:
                lines.append(_side_row(cols))
            lines.append(_border_line(cols))

        # pad to screen height
        while len(lines) < rows_n:
            lines.append(" " * cols)

        return lines[:rows_n]

    # ── panel content helpers ─────────────────────────────────────────────────

    def _cuenta_rows(self, w: int) -> list[str]:
        """Returns _H_TOP-2 styled strings, each for inner content (visible width = w-3)."""
        iw = w - 3
        if not self._connected or not self._account:
            return [_RED + _I + _clip("Sin conexion MT4", iw) + _R] + [""] * (_H_TOP - 3)
        a = self._account
        return [
            _WHITE + _clip(f"Balance    {a.get('balance',0):.2f} {a.get('currency','')}", iw) + _R,
            _WHITE + _clip(f"Equity     {a.get('equity',0):.2f}", iw) + _R,
            _WHITE + _clip(f"Margin     {a.get('free_margin',0):.2f}", iw) + _R,
        ] + [""] * (_H_TOP - 5)

    def _mercado_rows(self, w: int) -> list[str]:
        iw = w - 3
        if not self._market:
            return [_D + _I + _clip("Sin datos de mercado", iw) + _R] + [""] * (_H_TOP - 3)
        ctx = self._market
        p   = ctx.get("price", {})
        d   = ctx.get("day_ohlc", {})
        return [
            _WHITE + _clip(f"Bid {p.get('bid',0):.2f}  Ask {p.get('ask',0):.2f}  Spread {p.get('spread',0):.2f}", iw) + _R,
            _WHITE + _clip(f"ATR(H1,14) {ctx.get('atr_h1',0):.2f}   Sesión: {ctx.get('session','-')}", iw) + _R,
            _WHITE + _clip(f"Prev  H:{d.get('prev_high',0):.2f}  L:{d.get('prev_low',0):.2f}  C:{d.get('prev_close',0):.2f}", iw) + _R,
            _WHITE + _clip(f"Hoy O:{d.get('today_open',0):.2f}", iw) + _R,
        ]

    def _estado_rows(self, pw: int) -> list[str]:
        iw  = pw - 3
        st  = self._state
        dot = _BGREEN if "Esperando" in st or st == "OK" \
              else _BRED if "Error" in st or "error" in st \
              else _YELLOW
        row1 = dot + "○ " + _R + _WHITE + _B + _clip(st, iw - 2) + _R
        rows = [row1]
        if self._sub:
            rows.append(_D + _clip(self._sub, iw) + _R)
        return rows + [""] * max(0, _H_TOP - 2 - len(rows))

    def _decision_row(self, cols: int) -> str:
        if not self._decision:
            return _side_row(cols, "Sin decisiones aún", _D + _I)
        d      = self._decision
        ts     = d.get("_ts", "")
        raw    = d.get("decision", "WAIT").upper()
        label  = "DONE" if raw == "WAIT" else raw
        reason = d.get("reasoning", "")
        ac     = _DEC_COLOR.get(label, _WHITE)
        iw     = cols - 4
        prefix = f"[{ts}]  "
        rest   = _clip(reason, iw - len(prefix) - len(label) - 5)
        styled = _D + prefix + _R + ac + label + _R + _WHITE + "  —  " + rest + _R
        return _side_row_raw(cols, styled)

    def _timer_row(self, cols: int) -> str:
        iw      = cols - 4
        elapsed = max(0.0, time.monotonic() - self._t_start) if self._t_start else 0.0
        total   = self._t_total
        elapsed = min(elapsed, total)
        bar_w   = max(10, iw - 15)
        filled  = min(bar_w, int((elapsed / total) * bar_w))
        em, es  = divmod(int(elapsed), 60)
        tm, ts_ = divmod(int(total),   60)
        label   = f"  {em:02d}:{es:02d} / {tm:02d}:{ts_:02d}"

        bar = (_BG_CYAN + " " * filled + _R
               + " " * (bar_w - filled)
               + _WHITE + _B + label + _R)
        return _side_row_raw(cols, bar)
