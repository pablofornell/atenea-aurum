"""Tiered memory system for AURUM — injects L1/L2/L3 context into each Claude prompt."""
import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any, TYPE_CHECKING

from src.agent.memory import CycleMemory

if TYPE_CHECKING:
    from src.db.storage import SessionStorage

logger = logging.getLogger(__name__)

TOKEN_BUDGET = {
    "L1": 500,
    "L2": 800,
    "L3": 400,
    "total": 1700,
}

_TOKENS = lambda text: len(text) // 4


class TieredMemoryManager:
    """Three-level memory: strategy insights (L3), session summaries (L2), current-run cycles (L1).

    L3 — ~400 tokens, bullet-point patterns learned across all sessions (stable).
    L2 — ~800 tokens, one-line summary per recent session (last 14).
    L1 — ~500 tokens, last 8 cycle decisions from the current run.
    """

    def __init__(
        self,
        storage: "SessionStorage",
        claude_cli_path: str = "claude",
        strategy_dir: Optional[str] = None,
    ):
        self.storage = storage
        self.claude_cli = claude_cli_path
        self.strategy_dir = strategy_dir
        self._cycle_memory = CycleMemory(storage)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_context(self, run_id: str, max_tokens: int = 1700) -> str:
        """Assemble all three memory levels respecting the token budget.

        Priority: L3 always complete → L1 always complete → L2 with what remains.
        If L2 does not fit fully, fewer sessions are included.
        """
        l3_text = self._build_l3()
        l1_text = self._build_l1(run_id)

        l3_tokens = _TOKENS(l3_text) if l3_text else 0
        l1_tokens = _TOKENS(l1_text) if l1_text else 0
        remaining = max_tokens - TOKEN_BUDGET["L3"] - TOKEN_BUDGET["L1"]

        l2_text = self._build_l2_within_budget(remaining)

        l3_section = l3_text if l3_text else "(no data yet)"
        l1_section = l1_text if l1_text else "(no data yet)"
        l2_n = self._count_l2_lines(l2_text)
        l2_section = l2_text if l2_text else "(no data yet)"

        parts = [
            "=== TRADING MEMORY ===",
            "",
            "[L3 — Strategy Insights]",
            l3_section,
            "",
            f"[L2 — Recent Sessions (last {l2_n})]",
            l2_section,
            "",
            "[L1 — Current Run, last 8 decisions]",
            l1_section,
        ]
        return "\n".join(parts)

    def save_cycle(
        self,
        run_id: str,
        session_id: str,
        cycle_num: int,
        action: dict,
        market_context: dict,
    ) -> None:
        """Proxy to CycleMemory.save."""
        self._cycle_memory.save(
            run_id=run_id,
            session_id=session_id,
            cycle_num=cycle_num,
            action=action,
            market_context=market_context,
        )

    def compress_session(
        self,
        run_id: str,
        session_date: str,
        pnl: float,
        trades: List[Dict[str, Any]],
    ) -> Optional[str]:
        """Generate a compressed one-sentence summary of the session and persist it.

        Calls Claude CLI to produce the lesson. Falls back to a simple auto-summary
        if Claude fails. After saving, triggers update_strategy_insights().

        Returns the lesson string, or None if storage itself fails.
        """
        if not trades:
            logger.info("compress_session: no trades this session — skipping lesson generation")
            return None

        wins = sum(1 for t in trades if t.get("outcome") in ("win", "tp", "WIN", "TP"))
        losses = sum(1 for t in trades if t.get("outcome") in ("loss", "sl", "LOSS", "SL"))

        lesson = self._call_claude_for_lesson(session_date, pnl, trades, wins, losses)
        if lesson is None:
            lesson = f"P&L {pnl:+.2f}: {len(trades)} trade(s), {wins}W/{losses}L"

        try:
            self.storage.save_session_summary(
                run_id=run_id,
                session_date=session_date,
                pnl=pnl,
                trades_taken=len(trades),
                wins=wins,
                losses=losses,
                key_errors="",
                lesson=lesson,
            )
        except Exception as e:
            logger.error(f"TieredMemoryManager.compress_session: failed to save summary — {e}")
            return None

        self.update_strategy_insights()
        return lesson

    def update_strategy_insights(self) -> None:
        """Regenerate L3 strategy insights from all session summaries via Claude CLI."""
        try:
            sessions = self.storage.get_all_session_summaries()
        except Exception as e:
            logger.error(f"TieredMemoryManager.update_strategy_insights: fetch failed — {e}")
            return

        meaningful_sessions = [s for s in sessions if s.get('trades_taken', 0) > 0]
        if len(meaningful_sessions) < 3:
            logger.debug("update_strategy_insights: fewer than 3 sessions with real trades, skipping")
            return

        summaries_text = "\n".join(
            f"[{s['session_date']}] P&L:{s['pnl']:+.2f} "
            f"({s['trades_taken']}T {s['wins']}W/{s['losses']}L) — {s['lesson']}"
            for s in sessions
        )

        prompt = (
            "Based on these trading sessions, generate 8-12 actionable strategy insights "
            "as bullet points. Each insight: max 20 words. "
            "Format: '• [N/5] insight' where N is confidence (1=uncertain, 5=very confident). "
            "Focus on: entry timing, HTF context failures, session patterns, what setups worked vs failed.\n\n"
            f"Sessions:\n{summaries_text}"
        )

        raw = self._call_claude_raw(prompt, timeout=60)
        if raw is None:
            return

        insights = self._parse_insights(raw, source_label=f"{len(sessions)} sessions")
        if not insights:
            logger.warning("update_strategy_insights: no bullet points parsed from Claude response")
            return

        try:
            self.storage.save_strategy_insights(insights)
        except Exception as e:
            logger.error(f"update_strategy_insights: failed to save insights — {e}")

    # ------------------------------------------------------------------
    # Level builders
    # ------------------------------------------------------------------

    def _build_l1(self, run_id: str) -> str:
        return self._cycle_memory.get_formatted(run_id=run_id, n=8)

    def _build_l2(self, n_sessions: int = 14) -> str:
        try:
            sessions = self.storage.get_session_summaries(n=n_sessions)
        except Exception as e:
            logger.warning(f"TieredMemoryManager._build_l2: fetch failed — {e}")
            return ""

        if not sessions:
            return ""

        lines = []
        for s in reversed(sessions):  # chronological order
            lines.append(
                f"[{s['session_date']}] P&L:{s['pnl']:+.2f} "
                f"({s['trades_taken']}T {s['wins']}W/{s['losses']}L) — {s['lesson']}"
            )
        return "\n".join(lines)

    def _build_l2_within_budget(self, budget_tokens: int) -> str:
        """Return L2 text that fits within the token budget, reducing N if needed."""
        for n in range(14, 0, -1):
            text = self._build_l2(n_sessions=n)
            if _TOKENS(text) <= budget_tokens:
                return text
        return ""

    def _build_l3(self) -> str:
        try:
            insights = self.storage.get_strategy_insights()
        except Exception as e:
            logger.warning(f"TieredMemoryManager._build_l3: fetch failed — {e}")
            return ""

        if not insights:
            return ""

        lines = [f"• [{row['confidence']}/5] {row['insight']}" for row in insights]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _count_l2_lines(self, l2_text: str) -> int:
        if not l2_text:
            return 0
        return len([ln for ln in l2_text.splitlines() if ln.strip()])

    def _call_claude_for_lesson(
        self,
        session_date: str,
        pnl: float,
        trades: List[Dict[str, Any]],
        wins: int,
        losses: int,
    ) -> Optional[str]:
        trades_text = "\n".join(
            f"  ticket={t.get('ticket','?')} {t.get('side','?')} {t.get('lots','?')}lot "
            f"entry={t.get('entry','?')} sl={t.get('sl','?')} tp={t.get('tp','?')} "
            f"pnl={t.get('pnl_trade','?')} outcome={t.get('outcome','?')}"
            for t in trades
        ) or "  (no trades)"

        prompt = (
            f"Trading session {session_date}: P&L {pnl:+.2f}, {len(trades)} trade(s), "
            f"{wins}W/{losses}L.\n"
            f"Trades:\n{trades_text}\n\n"
            "Summarize this trading session in ONE sentence (max 25 words) focused on the "
            "KEY mistake or key success. Be specific about price levels and context if relevant."
        )

        raw = self._call_claude_raw(prompt, timeout=45)
        if raw is None:
            return None

        lesson = raw.strip().split("\n")[0].strip()
        return lesson if lesson else None

    def _call_claude_raw(self, prompt: str, timeout: int = 60) -> Optional[str]:
        """Invoke Claude CLI and return the plain text result, or None on failure."""
        cmd = [self.claude_cli, "--dangerously-skip-permissions", "--output-format", "json"]
        cwd = str(self.strategy_dir) if self.strategy_dir else None

        try:
            result = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                cwd=cwd,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            logger.warning(f"TieredMemoryManager: Claude CLI timed out after {timeout}s")
            return None
        except Exception as e:
            logger.error(f"TieredMemoryManager: subprocess error — {e}")
            return None

        if result.returncode != 0:
            logger.warning(
                f"TieredMemoryManager: Claude CLI exit {result.returncode}: "
                f"{(result.stderr or result.stdout)[:300]}"
            )
            return None

        try:
            response_json = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            logger.warning(f"TieredMemoryManager: JSON parse error — {e}")
            return None

        if response_json.get("type") != "result":
            logger.warning(
                f"TieredMemoryManager: unexpected response type '{response_json.get('type')}'"
            )
            return None

        return response_json.get("result", "") or None

    def _parse_insights(
        self, raw: str, source_label: str
    ) -> List[Dict[str, Any]]:
        """Extract bullet-point insights from Claude's response text."""
        insights = []
        for line in raw.splitlines():
            line = line.strip()
            if not line.startswith("•"):
                continue
            confidence = 3
            match = re.search(r"\[(\d)/5\]", line)
            if match:
                confidence = int(match.group(1))
            text = re.sub(r"^•\s*\[\d/5\]\s*", "", line).strip()
            if text:
                insights.append(
                    {
                        "insight": text,
                        "confidence": confidence,
                        "source_sessions": source_label,
                    }
                )
        return insights
