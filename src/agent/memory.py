"""Cross-cycle decision memory — injects recent trading history into each Claude prompt."""
import logging
from typing import List, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.db.storage import SessionStorage

logger = logging.getLogger(__name__)


class CycleMemory:
    """Reads and formats recent cycle decisions for injection into the analysis prompt.

    This gives Claude awareness of what was decided in previous cycles within the same
    run — which timeframe was analyzed, what entry was taken, what the reasoning was,
    and what the P&L looked like at the time of the decision.
    """

    def __init__(self, storage: "SessionStorage"):
        self.storage = storage

    def get_formatted(self, run_id: str, n: int = 5) -> str:
        """Return a formatted string of the last N cycle decisions for prompt injection.

        Returns empty string if no history exists yet.
        """
        try:
            decisions = self.storage.get_recent_cycle_decisions(run_id, n)
        except Exception as e:
            logger.warning(f"CycleMemory: failed to fetch history — {e}")
            return ""

        if not decisions:
            return ""

        lines = [f"## Recent Cycle History (last {len(decisions)} cycles — same run)"]
        for d in decisions:
            ts_raw = d.get("created_at", "")
            ts = ts_raw[11:16] if len(ts_raw) >= 16 else ts_raw  # HH:MM from "YYYY-MM-DD HH:MM:SS"
            action = d.get("action", "?")
            price = d.get("price")
            sl = d.get("sl")
            tp = d.get("tp")
            lots = d.get("lots")
            atr = d.get("atr")
            session = d.get("session_name", "")
            pnl = d.get("pnl_at_decision")
            reasoning = (d.get("reasoning") or "")[:120]

            # Build concise header line
            header_parts = [f"[{ts} UTC] {action}"]
            if price:
                header_parts.append(f"@ {price:.2f}")
            if sl and tp and action in ("BUY", "SELL"):
                header_parts.append(f"SL={sl:.2f} TP={tp:.2f}")
            if lots and action in ("BUY", "SELL"):
                header_parts.append(f"{lots}lot")
            if atr:
                header_parts.append(f"ATR={atr:.1f}")
            if session:
                header_parts.append(f"| {session}")
            if pnl is not None and action not in ("BUY", "SELL"):
                header_parts.append(f"| open P&L: {pnl:+.2f}")

            lines.append("  " + " ".join(header_parts))
            if reasoning:
                lines.append(f"    → {reasoning}{'…' if len(d.get('reasoning', '')) > 120 else ''}")

        return "\n".join(lines)

    def save(
        self,
        run_id: str,
        session_id: str,
        cycle_num: int,
        action: dict,
        market_context: dict,
    ) -> None:
        """Persist a cycle decision after Claude responds. Safe to call even if storage fails."""
        try:
            action_type = action.get("action", "UNKNOWN")
            reasoning = action.get("reasoning", "")
            lots = action.get("lots")
            sl = action.get("sl")
            tp = action.get("tp")

            price_data = market_context.get("price")
            price = price_data.get("bid") if price_data else None
            atr = market_context.get("atr")

            positions = market_context.get("positions", [])
            pnl = sum(p.get("profit", 0) for p in positions) if positions else None

            # Derive session name from server_time if available
            server_time = market_context.get("server_time", "")
            session_name = _derive_session(server_time)

            self.storage.save_cycle_decision(
                run_id=run_id,
                session_id=session_id,
                cycle_num=cycle_num,
                action=action_type,
                reasoning=reasoning,
                price=price,
                sl=sl,
                tp=tp,
                lots=lots,
                atr=atr,
                session_name=session_name,
                pnl_at_decision=pnl,
            )
        except Exception as e:
            logger.warning(f"CycleMemory.save failed (non-critical): {e}")


def _derive_session(server_time: str) -> str:
    """Derive session name from MT4 server time string (broker = GMT+2)."""
    try:
        hour = int(server_time[11:13])
    except (TypeError, IndexError, ValueError):
        return ""
    gmt = (hour - 2) % 24
    if 0 <= gmt < 7:
        return "Asia"
    if 7 <= gmt < 10:
        return "London Open"
    if 10 <= gmt < 13:
        return "London"
    if 13 <= gmt < 17:
        return "London/NY Overlap"
    if 17 <= gmt < 22:
        return "New York"
    return "Late NY"
