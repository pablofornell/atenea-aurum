import json
import logging
import os
import time
from datetime import datetime, timezone


class AurumLogger:
    LOG_DIR = "./logs"
    LOG_FILE = "aurum.log"
    DECISIONS_FILE = "decisions.jsonl"

    def __init__(self):
        os.makedirs(self.LOG_DIR, exist_ok=True)
        log_path = os.path.join(self.LOG_DIR, self.LOG_FILE)

        fmt = logging.Formatter("[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(fmt)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(fmt)

        self._log = logging.getLogger("aurum")
        self._log.setLevel(logging.DEBUG)
        if not self._log.handlers:
            self._log.addHandler(file_handler)
            self._log.addHandler(console_handler)

        self._decisions_path = os.path.join(self.LOG_DIR, self.DECISIONS_FILE)
        self._cycle_start: float = 0.0

    def info(self, msg: str):
        self._log.info(msg)

    def error(self, msg: str):
        self._log.error(msg)

    def log_cycle(self, context: dict, decision: dict, result: str):
        elapsed = time.time() - self._cycle_start if self._cycle_start else 0.0

        price   = context["price"]["bid"]
        session = context["session"]
        n_pos   = len(context["positions"])
        action  = decision.get("decision", "?")
        conf    = decision.get("confidence", 0.0)
        reason  = decision.get("reasoning", "")

        self._log.info(f"DATA OK — price={price:.2f} session={session} positions={n_pos}")
        self._log.info(f"AGENT — decision={action} confidence={conf:.2f}")
        if reason:
            self._log.info(f"AGENT REASONING — {reason}")
        self._log.info(f"EXECUTOR — {result}")
        self._log.info(f"CYCLE END ({elapsed:.1f}s)")

        self._append_decision(context, decision, result)

    def cycle_start(self):
        self._cycle_start = time.time()
        self._log.info("CYCLE START")

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
