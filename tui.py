import curses
import threading
import time
from collections import deque
from datetime import datetime, timezone

# ── color pair IDs ────────────────────────────────────────────────────────────
_C_BORDER = 1   # cyan — panel borders & titles
_C_GREEN  = 2
_C_RED    = 3
_C_YELLOW = 4
_C_WHITE  = 5
_C_BADGE  = 6   # AURUM badge: white-on-red
_C_DIM    = 7   # grey — placeholder / secondary text
_C_BAR    = 8   # progress bar fill: black-on-cyan

# decision → color
_DEC_COLOR = {
    "BUY":  _C_GREEN,
    "SELL": _C_RED,
    "DONE": _C_GREEN,   # WAIT displayed as DONE after a clean cycle
    "CLOSE":_C_YELLOW,
    "HOLD": _C_YELLOW,
    "WAIT": _C_WHITE,
}

# ── fixed panel heights ───────────────────────────────────────────────────────
_H_TOP   = 7   # CUENTA | MERCADO | ESTADO
_H_POS   = 5   # POSICIONES ABIERTAS
_H_DEC   = 4   # ULTIMA DECISION
_H_TIMER = 3   # PROXIMO CICLO

_LOG_MAX = 500


# ── helpers ───────────────────────────────────────────────────────────────────

def _put(scr, r, c, text, attr=0):
    try:
        scr.addstr(r, c, text, attr)
    except curses.error:
        pass


def _clip(s: str, w: int) -> str:
    if w <= 0:
        return ""
    return s if len(s) <= w else s[: w - 1] + "…"


# ── TUI class ─────────────────────────────────────────────────────────────────

class TUI:
    def __init__(self):
        self._lock    = threading.Lock()
        self._scr     = None
        self._running = False
        self._thread  : threading.Thread | None = None

        # shared state (written via update methods, read inside _draw)
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

        self._logs: deque = deque(maxlen=_LOG_MAX)

    # ── public update API ─────────────────────────────────────────────────────

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
        self._scr = curses.initscr()
        curses.start_color()
        curses.use_default_colors()
        curses.noecho()
        curses.cbreak()
        curses.curs_set(0)
        self._scr.keypad(True)
        self._scr.nodelay(True)

        curses.init_pair(_C_BORDER, curses.COLOR_CYAN,   -1)
        curses.init_pair(_C_GREEN,  curses.COLOR_GREEN,  -1)
        curses.init_pair(_C_RED,    curses.COLOR_RED,    -1)
        curses.init_pair(_C_YELLOW, curses.COLOR_YELLOW, -1)
        curses.init_pair(_C_WHITE,  curses.COLOR_WHITE,  -1)
        curses.init_pair(_C_BADGE,  curses.COLOR_WHITE,  curses.COLOR_RED)
        curses.init_pair(_C_DIM,    curses.COLOR_WHITE,  -1)
        curses.init_pair(_C_BAR,    curses.COLOR_BLACK,  curses.COLOR_CYAN)

        self._running = True
        self._thread  = threading.Thread(target=self._tick, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        if self._scr:
            try:
                curses.nocbreak()
                self._scr.keypad(False)
                curses.echo()
                curses.endwin()
            except curses.error:
                pass

    # ── internal ──────────────────────────────────────────────────────────────

    def _tick(self):
        while self._running:
            self._render()
            time.sleep(0.1)

    def _render(self):
        if not self._scr:
            return
        with self._lock:
            try:
                self._draw()
            except curses.error:
                pass

    def _draw(self):
        scr = self._scr
        rows, cols = scr.getmaxyx()
        scr.erase()
        row = 0

        # ── header ────────────────────────────────────────────────────────────
        clock  = datetime.now(timezone.utc).strftime("%H:%M:%S")
        badge  = " AURUM "
        center = f"XAUUSD · Gold/USD"
        line   = f"{badge}  {center}   {clock}"
        x = max(0, (cols - len(line)) // 2)
        _put(scr, 0, x, badge, curses.color_pair(_C_BADGE) | curses.A_BOLD)
        _put(scr, 0, x + len(badge), f"  {center}   ",
             curses.color_pair(_C_WHITE))
        _put(scr, 0, x + len(badge) + 2 + len(center) + 3, clock,
             curses.color_pair(_C_BORDER))
        row = 1

        # ── top three panels ──────────────────────────────────────────────────
        if row + _H_TOP <= rows:
            w = cols // 3
            self._panel(scr, row, 0,   _H_TOP, w,        "CUENTA")
            self._panel(scr, row, w,   _H_TOP, w,        "MERCADO")
            self._panel(scr, row, w*2, _H_TOP, cols-w*2, "ESTADO")
            self._fill_cuenta  (scr, row, 0,   w)
            self._fill_mercado (scr, row, w,   w)
            self._fill_estado  (scr, row, w*2, cols - w*2)
            row += _H_TOP

        # ── positions ─────────────────────────────────────────────────────────
        if row + _H_POS <= rows:
            n  = len(self._positions)
            tc = _C_GREEN if n else _C_BORDER
            self._panel(scr, row, 0, _H_POS, cols,
                        f"POSICIONES ABIERTAS  ({n})", title_c=tc)
            self._fill_positions(scr, row, cols)
            row += _H_POS

        # ── last decision ─────────────────────────────────────────────────────
        if row + _H_DEC <= rows:
            self._panel(scr, row, 0, _H_DEC, cols, "ULTIMA DECISION")
            self._fill_decision(scr, row, cols)
            row += _H_DEC

        # ── timer ─────────────────────────────────────────────────────────────
        if row + _H_TIMER <= rows:
            self._panel(scr, row, 0, _H_TIMER, cols, "PROXIMO CICLO")
            self._fill_timer(scr, row, cols)
            row += _H_TIMER

        # ── activity log ──────────────────────────────────────────────────────
        avail = rows - row
        if avail >= 3:
            self._panel(scr, row, 0, avail, cols, "ACTIVIDAD")
            self._fill_log(scr, row, cols, avail)

        scr.refresh()

    # ── panel border ──────────────────────────────────────────────────────────

    def _panel(self, scr, r, c, h, w, title, title_c=_C_BORDER):
        ba = curses.color_pair(_C_BORDER)
        ta = curses.color_pair(title_c) | curses.A_BOLD
        seg = f"─── {title} ───"
        pad = max(0, w - len(seg))
        lp  = pad // 2
        rp  = pad - lp
        top = "─" * lp + seg + "─" * rp
        _put(scr, r, c, top[:w], ba)
        _put(scr, r, c + lp + 4, title, ta)
        rows, _cols = scr.getmaxyx()
        for row in range(r + 1, min(r + h - 1, rows)):
            _put(scr, row, c, "│", ba)
            if c + w - 1 < _cols:
                _put(scr, row, c + w - 1, "│", ba)
        _put(scr, r + h - 1, c, ("─" * w)[:w], ba)

    # ── panel fill ────────────────────────────────────────────────────────────

    def _fill_cuenta(self, scr, r, c, w):
        ic, iw = c + 2, w - 4
        if not self._connected or not self._account:
            _put(scr, r + 2, ic, _clip("Sin conexion MT4", iw),
                 curses.color_pair(_C_RED) | curses.A_ITALIC)
            return
        a = self._account
        for i, line in enumerate([
            f"Balance    {a.get('balance', 0):.2f} {a.get('currency', '')}",
            f"Equity     {a.get('equity', 0):.2f}",
            f"Margin     {a.get('free_margin', 0):.2f}",
        ]):
            _put(scr, r + 1 + i, ic, _clip(line, iw), curses.color_pair(_C_WHITE))

    def _fill_mercado(self, scr, r, c, w):
        ic, iw = c + 2, w - 4
        if not self._market:
            _put(scr, r + 2, ic, _clip("Sin datos de mercado", iw),
                 curses.color_pair(_C_DIM) | curses.A_ITALIC)
            return
        ctx = self._market
        p   = ctx.get("price", {})
        d   = ctx.get("day_ohlc", {})
        for i, line in enumerate([
            f"Bid {p.get('bid',0):.2f}  Ask {p.get('ask',0):.2f}  Spread {p.get('spread',0):.2f}",
            f"ATR(H1,14) {ctx.get('atr_h1',0):.2f}   Sesión: {ctx.get('session','-')}",
            f"Prev  H:{d.get('prev_high',0):.2f}  L:{d.get('prev_low',0):.2f}  C:{d.get('prev_close',0):.2f}",
            f"Hoy O:{d.get('today_open',0):.2f}",
        ][: _H_TOP - 2]):
            _put(scr, r + 1 + i, ic, _clip(line, iw), curses.color_pair(_C_WHITE))

    def _fill_estado(self, scr, r, c, w):
        ic, iw = c + 2, w - 4
        st = self._state
        dot_c = _C_GREEN  if "Esperando" in st or st == "OK" \
                else _C_RED    if "Error" in st or "error" in st \
                else _C_YELLOW
        _put(scr, r + 1, ic, "○ ", curses.color_pair(dot_c))
        _put(scr, r + 1, ic + 2, _clip(st, iw - 2),
             curses.color_pair(_C_WHITE) | curses.A_BOLD)
        if self._sub:
            _put(scr, r + 2, ic, _clip(self._sub, iw),
                 curses.color_pair(_C_DIM))

    def _fill_positions(self, scr, r, cols):
        ic, iw = 2, cols - 4
        if not self._positions:
            _put(scr, r + 2, ic, "Sin posiciones abiertas",
                 curses.color_pair(_C_DIM) | curses.A_ITALIC)
            return
        for i, p in enumerate(self._positions[: _H_POS - 2]):
            col = _C_GREEN if p.get("type") == "BUY" else _C_RED
            line = (f"  #{p['ticket']}  {p['type']}  {p['lots']} lots"
                    f"  open={p['open']:.2f}  SL={p['sl']:.2f}  TP={p['tp']:.2f}"
                    f"  P&L={p['profit']:+.2f}")
            _put(scr, r + 1 + i, ic, _clip(line, iw), curses.color_pair(col))

    def _fill_decision(self, scr, r, cols):
        ic, iw = 2, cols - 4
        if not self._decision:
            _put(scr, r + 2, ic, "Sin decisiones aún",
                 curses.color_pair(_C_DIM) | curses.A_ITALIC)
            return
        d      = self._decision
        ts     = d.get("_ts", "")
        raw    = d.get("decision", "WAIT").upper()
        label  = "DONE" if raw == "WAIT" else raw  # WAIT → DONE: cycle completed, decided to stay out
        reason = d.get("reasoning", "")
        ac     = curses.color_pair(_DEC_COLOR.get(label, _C_WHITE)) | curses.A_BOLD

        prefix = f"[{ts}]  "
        _put(scr, r + 2, ic, prefix, curses.color_pair(_C_DIM))
        ax = ic + len(prefix)
        _put(scr, r + 2, ax, label, ac)
        ax += len(label)
        _put(scr, r + 2, ax, _clip("  —  " + reason, iw - (ax - ic)),
             curses.color_pair(_C_WHITE))

    def _fill_timer(self, scr, r, cols):
        ic, iw  = 2, cols - 4
        elapsed = max(0.0, time.monotonic() - self._t_start) if self._t_start else 0.0
        total   = self._t_total
        elapsed = min(elapsed, total)

        bar_w  = max(10, iw - 22)
        filled = min(bar_w, int((elapsed / total) * bar_w))
        em, es = divmod(int(elapsed), 60)
        tm, ts = divmod(int(total),   60)
        label  = f"  {em:02d}:{es:02d} / {tm:02d}:{ts:02d}"

        _put(scr, r + 1, ic, " " * filled,           curses.color_pair(_C_BAR))
        _put(scr, r + 1, ic + filled, " " * (bar_w - filled), curses.color_pair(_C_WHITE))
        _put(scr, r + 1, ic + bar_w + 1, label,
             curses.color_pair(_C_WHITE) | curses.A_BOLD)

    def _fill_log(self, scr, r, cols, height):
        ic, iw    = 2, cols - 4
        max_lines = height - 2
        entries   = list(self._logs)[-max_lines:]
        for i, (ts, msg, level) in enumerate(entries):
            col = _C_RED    if level == "ERROR" \
                 else _C_YELLOW if level in ("WARN", "WARNING") \
                 else _C_GREEN  if level == "OK" \
                 else _C_WHITE
            _put(scr, r + 1 + i, ic, _clip(f"[{ts}]  {msg}", iw),
                 curses.color_pair(col))
