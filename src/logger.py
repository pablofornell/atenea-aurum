import json
import logging
import os
import time
from datetime import datetime, timezone


class AurumLogger:
    LOG_DIR        = "./logs"
    LOG_FILE       = "aurum.log"
    DECISIONS_FILE = "decisions.jsonl"

    def __init__(self, tui=None):
        self._tui = tui
        os.makedirs(self.LOG_DIR, exist_ok=True)
        log_path = os.path.join(self.LOG_DIR, self.LOG_FILE)

        fmt          = logging.Formatter("[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(fmt)

        self._log = logging.getLogger("aurum")
        self._log.setLevel(logging.DEBUG)
        if not self._log.handlers:
            self._log.addHandler(file_handler)
            if not tui:
                # when TUI is active, stdout belongs to curses — no StreamHandler
                console = logging.StreamHandler()
                console.setFormatter(fmt)
                self._log.addHandler(console)

        self._decisions_path = os.path.join(self.LOG_DIR, self.DECISIONS_FILE)
        self._cycle_start: float = 0.0

    # ── public log API ────────────────────────────────────────────────────────

    def info(self, msg: str):
        self._emit(msg, "INFO")

    def error(self, msg: str):
        self._emit(msg, "ERROR")

    def cycle_start(self):
        self._cycle_start = time.time()
        self._emit("CYCLE START", "INFO")

    def log_cycle(self, context: dict, decision: dict, result: str):
        elapsed = time.time() - self._cycle_start if self._cycle_start else 0.0
        price   = context["price"]["bid"]
        session = context["session"]
        n_pos   = len(context["positions"])
        action  = decision.get("decision", "?")
        conf    = decision.get("confidence", 0.0)
        reason  = decision.get("reasoning", "")

        self._emit(f"DATA OK — price={price:.2f} session={session} positions={n_pos}")
        self._emit(f"AGENT — decision={action} confidence={conf:.2f}")
        if reason:
            self._emit(f"AGENT REASONING — {reason}")
        dbg = decision.get("_debug")
        if dbg:
            self._emit(f"AGENT DEBUG — rc={dbg['returncode']} | stderr={dbg['stderr']!r}", "ERROR")
            self._emit(f"AGENT DEBUG — raw_stdout={dbg['raw_stdout']!r}", "ERROR")
        self._emit(f"EXECUTOR — {result}")
        self._emit(f"CYCLE END ({elapsed:.1f}s)")

        self._append_decision(context, decision, result)

    # ── internals ─────────────────────────────────────────────────────────────

    def _emit(self, msg: str, level: str = "INFO"):
        if level == "ERROR":
            self._log.error(msg)
        else:
            self._log.info(msg)
        if self._tui:
            self._tui.log(msg, level)

    def _append_decision(self, context: dict, decision: dict, result: str):
        record = {
            "ts":       datetime.now(timezone.utc).isoformat(),
            "session":  context["session"],
            "price":    context["price"],
            "decision": decision,
            "result":   result,
        }
        with open(self._decisions_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
