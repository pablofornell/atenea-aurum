import json
import logging
import os
import time
from datetime import datetime, timezone


def _session_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")


class _LineBufferedFileHandler(logging.FileHandler):
    """FileHandler with buffering=1 (line-buffered): each line is flushed to disk immediately."""
    def _open(self):
        return open(self.baseFilename, self.mode, buffering=1, encoding=self.encoding)


class AurumLogger:
    LOG_DIR = "./logs"

    def __init__(self, tui=None):
        self._tui = tui
        os.makedirs(self.LOG_DIR, exist_ok=True)

        ts = _session_ts()
        self._log_path       = os.path.join(self.LOG_DIR, f"aurum_session_{ts}.log")
        self._decisions_path = os.path.join(self.LOG_DIR, f"aurum_decisions_{ts}.jsonl")
        self._cycle_start: float = 0.0

        fmt     = logging.Formatter("[%(asctime)s] %(message)s", datefmt="%H:%M:%S")
        handler = _LineBufferedFileHandler(self._log_path, encoding="utf-8")
        handler.setFormatter(fmt)

        self._log = logging.getLogger(f"aurum.{ts}")
        self._log.setLevel(logging.DEBUG)
        self._log.propagate = False
        self._log.addHandler(handler)

        if not tui:
            console = logging.StreamHandler()
            console.setFormatter(fmt)
            self._log.addHandler(console)

    # ── public API ────────────────────────────────────────────────────────────

    def info(self, msg: str):
        self._emit(msg, "INFO")

    def error(self, msg: str):
        self._emit(msg, "ERROR")

    def cycle_start(self):
        self._cycle_start = time.time()
        self._emit("CYCLE START")

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
        with open(self._decisions_path, "a", buffering=1, encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
