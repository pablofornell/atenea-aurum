"""Structured event logger for the Aurum feedback loop.

Writes one JSON line per event to logs/aurum_events.jsonl.
Each record carries enough context for SessionReporter to reconstruct
a full narrative of what happened and why.
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

LOGS_DIR = Path("logs")
EVENTS_FILE = LOGS_DIR / "aurum_events.jsonl"


class FeedbackLogger:
    """Append-only structured event log for one agent run (start → Ctrl-C)."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        LOGS_DIR.mkdir(exist_ok=True)
        self._start_ts = time.time()

    # ------------------------------------------------------------------
    # Internal writer
    # ------------------------------------------------------------------

    def _write(self, event: str, data: dict,
               session_id: Optional[str] = None, turn: int = 0):
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            "session_id": session_id,
            "turn": turn,
            "event": event,
            "data": data,
        }
        with open(EVENTS_FILE, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    # ------------------------------------------------------------------
    # Run-level events
    # ------------------------------------------------------------------

    def run_start(self, cycle_interval: int):
        self._write("run_start", {
            "cycle_interval_s": cycle_interval,
            "events_file": str(EVENTS_FILE),
        })

    def run_end(self, total_cycles: int, total_errors: int,
                start_balance: Optional[float], end_balance: Optional[float],
                start_equity: Optional[float], end_equity: Optional[float]):
        duration = round(time.time() - self._start_ts)
        pnl = round(end_balance - start_balance, 2) if (end_balance and start_balance) else None
        self._write("run_end", {
            "duration_s": duration,
            "total_cycles": total_cycles,
            "total_errors": total_errors,
            "start_balance": start_balance,
            "end_balance": end_balance,
            "start_equity": start_equity,
            "end_equity": end_equity,
            "realised_pnl": pnl,
        })

    # ------------------------------------------------------------------
    # Cycle-level events
    # ------------------------------------------------------------------

    def cycle_start(self, session_id: str):
        self._write("cycle_start", {}, session_id=session_id)

    def cycle_end(self, session_id: str, duration_s: float, final_action: str):
        self._write("cycle_end", {
            "duration_s": round(duration_s, 1),
            "final_action": final_action,
        }, session_id=session_id)

    # ------------------------------------------------------------------
    # Per-turn events
    # ------------------------------------------------------------------

    def market_context(self, session_id: str, turn: int, context: dict):
        """Log snapshot of what MT4 reported at decision time."""
        safe = {
            "price": context.get("price"),
            "account": context.get("account"),
            "positions": context.get("positions", []),
            "server_time": context.get("server_time"),
            "connection_ok": context.get("price") is not None,
        }
        self._write("market_context", safe, session_id=session_id, turn=turn)

    def screenshot(self, session_id: str, turn: int, path: str):
        self._write("screenshot", {"path": path}, session_id=session_id, turn=turn)

    def claude_decision(self, session_id: str, turn: int,
                        action: dict, raw_response: str, elapsed_s: float):
        """Log Claude's full decision: action, reasoning, and response time."""
        self._write("claude_decision", {
            "action_type": action.get("action"),
            "reasoning": action.get("reasoning", ""),
            "params": {k: v for k, v in action.items()
                       if k not in ("action", "reasoning", "done")},
            "raw_preview": raw_response[:800],
            "claude_elapsed_s": round(elapsed_s, 2),
        }, session_id=session_id, turn=turn)

    def action_result(self, session_id: str, turn: int,
                      action_type: str, ok: bool, detail: dict):
        """Log the outcome of executing an action (order placed, modify failed, etc.)."""
        self._write("action_result", {
            "action": action_type,
            "ok": ok,
            **detail,
        }, session_id=session_id, turn=turn)

    # ------------------------------------------------------------------
    # Error events
    # ------------------------------------------------------------------

    def error(self, error_type: str, detail: str, context: Optional[dict] = None,
              session_id: Optional[str] = None, turn: int = 0):
        """Log any error with type classification for pattern analysis."""
        self._write("error", {
            "type": error_type,   # timeout | connection | modify_failed | order_failed | screenshot
            "detail": detail,
            "context": context or {},
        }, session_id=session_id, turn=turn)

    def reconnect(self, success: bool, attempts: int,
                  session_id: Optional[str] = None):
        self._write("reconnect", {
            "success": success,
            "attempts": attempts,
        }, session_id=session_id)

    def connection_lost(self, session_id: Optional[str] = None, turn: int = 0):
        self._write("connection_lost", {}, session_id=session_id, turn=turn)
