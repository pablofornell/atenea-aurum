"""Aurum trading agent — orchestrates analysis and order execution."""
import json
import time
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from src.mt4.bridge import MT4Bridge, MT4BridgeError
from src.mt4.screenshot import capture_mt4, ScreenshotError
from src.bridge.claude_bridge import call_claude
from src.db.storage import SessionStorage
from src.agent.prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class AurumAgent:
    """Autonomous trading agent for XAUUSD on MT4.

    Orchestrates screenshot capture, Claude analysis, order execution, and 15-minute cycles.
    """

    def __init__(
        self,
        mt4_bridge: MT4Bridge,
        storage: SessionStorage,
        cycle_interval: int = 900,  # 15 minutes in seconds
    ):
        """Initialize Aurum agent.

        Args:
            mt4_bridge: Connected MT4Bridge instance
            storage: SessionStorage instance for persistence
            cycle_interval: Seconds between major analysis cycles (default: 900 = 15 min)
        """
        self.mt4_bridge = mt4_bridge
        self.storage = storage
        self.cycle_interval = cycle_interval
        self.running = False

    def run(self):
        """Main loop: run analysis cycles indefinitely."""
        self.running = True
        logger.info("Aurum agent starting main loop")

        try:
            while self.running:
                session_id = str(uuid.uuid4())
                logger.info(f"Starting new cycle: {session_id}")

                cycle_start = time.time()
                try:
                    self.run_cycle(session_id)
                except Exception as e:
                    logger.error(f"Cycle error: {e}", exc_info=True)

                # Wait until next cycle
                elapsed = time.time() - cycle_start
                remaining = self.cycle_interval - elapsed
                if remaining > 0:
                    logger.info(f"Sleeping for {remaining:.1f}s until next cycle")
                    time.sleep(remaining)

        except KeyboardInterrupt:
            logger.info("Agent stopped by user (Ctrl+C)")
        finally:
            self.running = False

    def run_cycle(self, session_id: str):
        """Execute one full analysis cycle (may have multiple turns for timeframe changes).

        Args:
            session_id: Unique identifier for this cycle
        """
        logger.info(f"Cycle {session_id}: Starting")

        # Capture initial screenshot
        try:
            screenshot_path = capture_mt4()
            logger.info(f"Screenshot captured: {screenshot_path}")
        except ScreenshotError as e:
            logger.error(f"Failed to capture MT4: {e}")
            return

        # Get current chart timeframe from screenshot
        # (For now, assume H1 — Claude can request timeframe change if needed)
        current_timeframe = "H1"

        # Multi-turn loop: keep going until Claude says "DONE"
        turn = 0
        max_turns = 10  # Prevent infinite loops

        while turn < max_turns:
            turn += 1
            logger.info(f"Cycle {session_id}: Turn {turn}")

            # Build analysis prompt
            market_context = self._get_market_context()
            analysis_prompt = self._build_analysis_prompt(market_context)

            # Get session history (all previous turns in this cycle)
            history = self.storage.get_session_history(session_id)

            # Call Claude
            try:
                response = call_claude(
                    prompt=analysis_prompt,
                    screenshot_path=screenshot_path,
                    session_history=history,
                    system_prompt=SYSTEM_PROMPT
                )
            except Exception as e:
                logger.error(f"Claude call failed: {e}")
                return

            if not response.get("ok"):
                logger.error(f"Claude error: {response.get('error')}")
                self.storage.save_turn(
                    session_id=session_id,
                    role="system",
                    content=f"Error calling Claude: {response.get('error')}"
                )
                return

            # Extract action
            action = response.get("action")
            raw_response = response.get("raw", "")

            logger.debug(f"Claude action: {action.get('action') if action else 'None'}")
            logger.debug(f"Raw response: {raw_response[:200]}...")

            # Save Claude's turn in history
            self.storage.save_turn(
                session_id=session_id,
                role="assistant",
                content=raw_response,
                screenshot_path=screenshot_path,
                timeframe=current_timeframe
            )

            if not action:
                logger.warning(f"Invalid action from Claude: {raw_response}")
                self.storage.save_turn(
                    session_id=session_id,
                    role="system",
                    content="Failed to parse action JSON"
                )
                return

            # Execute action
            cycle_done = self._execute_action(
                action=action,
                session_id=session_id,
                screenshot_path=screenshot_path
            )

            if cycle_done:
                logger.info(f"Cycle {session_id}: Complete (action={action.get('action')})")
                return

            # If we changed timeframe, capture new screenshot for next turn
            if action.get("action") == "CHANGE_TIMEFRAME":
                new_timeframe = action.get("timeframe", current_timeframe)
                logger.info(f"Changing timeframe to {new_timeframe}")

                # Wait for chart to update
                time.sleep(2)

                # Capture new screenshot
                try:
                    screenshot_path = capture_mt4()
                    current_timeframe = new_timeframe
                    logger.info(f"New screenshot: {screenshot_path}")
                except ScreenshotError as e:
                    logger.error(f"Failed to capture new screenshot: {e}")
                    return

                # Continue loop for next turn (Claude will see new chart)
                continue

            # If we got here with no special action, something unexpected happened
            # (e.g., Claude didn't specify DONE but also didn't specify another action)
            logger.warning("Unexpected: Claude action did not trigger DONE or CHANGE_TIMEFRAME")
            break

    def _execute_action(self, action: Dict[str, Any], session_id: str, screenshot_path: str) -> bool:
        """Execute a trading action. Returns True if cycle should end.

        Args:
            action: Action dict from Claude
            session_id: Session identifier for logging
            screenshot_path: Path to current screenshot (for logging)

        Returns:
            True if cycle is complete (DONE), False if cycle should continue
        """
        action_type = action.get("action")
        reasoning = action.get("reasoning", "")

        logger.info(f"Executing action: {action_type}")

        if action_type == "DONE":
            logger.info("Claude finished analysis (DONE)")
            self.storage.save_turn(
                session_id=session_id,
                role="system",
                content="Analysis complete, waiting for next cycle"
            )
            return True

        elif action_type == "CHANGE_TIMEFRAME":
            timeframe = action.get("timeframe")
            logger.info(f"Claude requested timeframe change: {timeframe}")
            try:
                self.mt4_bridge.set_timeframe("XAUUSD", timeframe)
                self.storage.save_turn(
                    session_id=session_id,
                    role="system",
                    content=f"Timeframe changed to {timeframe}, waiting for chart update"
                )
            except MT4BridgeError as e:
                logger.error(f"Failed to change timeframe: {e}")
                self.storage.save_turn(
                    session_id=session_id,
                    role="system",
                    content=f"Error changing timeframe: {e}"
                )
                return True  # End cycle on error
            return False  # Continue cycle

        elif action_type == "BUY":
            symbol = action.get("symbol", "XAUUSD")
            lots = action.get("lots", 0.1)
            sl = action.get("sl")
            tp = action.get("tp")
            try:
                result = self.mt4_bridge.buy(symbol, lots, sl, tp)
                ticket = result.get("ticket")
                self.storage.log_order(
                    session_id=session_id,
                    action="BUY",
                    symbol=symbol,
                    lots=lots,
                    sl=sl,
                    tp=tp,
                    ticket=ticket,
                    result="OK"
                )
                logger.info(f"BUY order placed: ticket={ticket}, lots={lots}")
                self.storage.save_turn(
                    session_id=session_id,
                    role="system",
                    content=f"BUY order placed successfully (ticket={ticket})\nReasoning: {reasoning}"
                )
            except Exception as e:
                logger.error(f"BUY order failed: {e}")
                self.storage.log_order(
                    session_id=session_id,
                    action="BUY",
                    symbol=symbol,
                    lots=lots,
                    sl=sl,
                    tp=tp,
                    result="ERROR",
                    error_message=str(e)
                )
                self.storage.save_turn(
                    session_id=session_id,
                    role="system",
                    content=f"BUY order failed: {e}"
                )
            return False  # Continue cycle

        elif action_type == "SELL":
            symbol = action.get("symbol", "XAUUSD")
            lots = action.get("lots", 0.1)
            sl = action.get("sl")
            tp = action.get("tp")
            try:
                result = self.mt4_bridge.sell(symbol, lots, sl, tp)
                ticket = result.get("ticket")
                self.storage.log_order(
                    session_id=session_id,
                    action="SELL",
                    symbol=symbol,
                    lots=lots,
                    sl=sl,
                    tp=tp,
                    ticket=ticket,
                    result="OK"
                )
                logger.info(f"SELL order placed: ticket={ticket}, lots={lots}")
                self.storage.save_turn(
                    session_id=session_id,
                    role="system",
                    content=f"SELL order placed successfully (ticket={ticket})\nReasoning: {reasoning}"
                )
            except Exception as e:
                logger.error(f"SELL order failed: {e}")
                self.storage.log_order(
                    session_id=session_id,
                    action="SELL",
                    symbol=symbol,
                    lots=lots,
                    sl=sl,
                    tp=tp,
                    result="ERROR",
                    error_message=str(e)
                )
                self.storage.save_turn(
                    session_id=session_id,
                    role="system",
                    content=f"SELL order failed: {e}"
                )
            return False

        elif action_type == "CLOSE":
            ticket = action.get("ticket")
            try:
                self.mt4_bridge.close(ticket)
                self.storage.log_order(
                    session_id=session_id,
                    action="CLOSE",
                    symbol="XAUUSD",
                    lots=0,
                    sl=0,
                    tp=0,
                    ticket=ticket,
                    result="OK"
                )
                logger.info(f"Position closed: ticket={ticket}")
                self.storage.save_turn(
                    session_id=session_id,
                    role="system",
                    content=f"Position closed (ticket={ticket})"
                )
            except Exception as e:
                logger.error(f"Close order failed: {e}")
                self.storage.save_turn(
                    session_id=session_id,
                    role="system",
                    content=f"Close failed: {e}"
                )
            return False

        elif action_type == "MODIFY":
            ticket = action.get("ticket")
            sl = action.get("sl")
            tp = action.get("tp")
            try:
                self.mt4_bridge.modify(ticket, sl, tp)
                self.storage.log_order(
                    session_id=session_id,
                    action="MODIFY",
                    symbol="XAUUSD",
                    lots=0,
                    sl=sl,
                    tp=tp,
                    ticket=ticket,
                    result="OK"
                )
                logger.info(f"Position modified: ticket={ticket}, sl={sl}, tp={tp}")
                self.storage.save_turn(
                    session_id=session_id,
                    role="system",
                    content=f"Position modified (ticket={ticket}, SL={sl}, TP={tp})"
                )
            except Exception as e:
                logger.error(f"Modify order failed: {e}")
                self.storage.save_turn(
                    session_id=session_id,
                    role="system",
                    content=f"Modify failed: {e}"
                )
            return False

        else:
            logger.warning(f"Unknown action: {action_type}")
            self.storage.save_turn(
                session_id=session_id,
                role="system",
                content=f"Unknown action: {action_type}"
            )
            return True

    def _get_market_context(self) -> dict:
        """Query MT4 for current market state. Failures return None/empty gracefully."""
        context = {}

        try:
            context["positions"] = self.mt4_bridge.get_positions()
        except Exception as e:
            logger.warning(f"get_positions failed: {e}")
            context["positions"] = []

        try:
            context["account"] = self.mt4_bridge.get_account()
        except Exception as e:
            logger.warning(f"get_account failed: {e}")
            context["account"] = None

        try:
            context["price"] = self.mt4_bridge.get_price("XAUUSD")
        except Exception as e:
            logger.warning(f"get_price failed: {e}")
            context["price"] = None

        try:
            context["server_time"] = self.mt4_bridge.get_server_time()
        except Exception as e:
            logger.warning(f"get_server_time failed: {e}")
            context["server_time"] = None

        return context

    def _build_analysis_prompt(self, market_context: dict) -> str:
        """Build the prompt for Claude to analyze the current chart."""
        lines = ["## Current Market Context"]

        account = market_context.get("account")
        if account:
            lines.append(
                f"Balance: {account['balance']:.2f} {account['currency']} | "
                f"Equity: {account['equity']:.2f} | "
                f"Free Margin: {account['free_margin']:.2f}"
            )

        price = market_context.get("price")
        if price:
            lines.append(
                f"Bid: {price['bid']:.5f} | Ask: {price['ask']:.5f} | "
                f"Spread: {price['spread']:.1f} pts"
            )

        server_time = market_context.get("server_time")
        if server_time:
            lines.append(f"Server Time: {server_time}")

        positions = market_context.get("positions", [])
        if positions:
            lines.append(f"\nOpen Positions ({len(positions)}):")
            for p in positions:
                lines.append(
                    f"  #{p['ticket']} {p['type']} {p['lots']} lot @ {p['open_price']:.5f} | "
                    f"SL: {p['sl']:.5f} | TP: {p['tp']:.5f} | P&L: {p['profit']:+.2f}"
                )
        else:
            lines.append("Open Positions: None")

        lines.append("""
## Chart Analysis
Analyze the chart screenshot and decide your next action.

Look for:
- Support and resistance levels
- Trend direction and strength
- Momentum indicators (if visible)
- Entry and exit points
- Risk/reward ratios (minimum 1:2)

Use the market context above when sizing positions and setting SL/TP.

Respond with ONE of these actions:
- BUY: Open a long position with specific lots, SL, TP
- SELL: Open a short position with specific lots, SL, TP
- CLOSE: Close an open position (provide ticket number)
- MODIFY: Adjust SL/TP on open position (provide ticket, new SL, new TP)
- CHANGE_TIMEFRAME: Request a different timeframe to confirm signal (provide timeframe)
- DONE: No high-confidence setup found, wait for next cycle

IMPORTANT: Respond with ONLY a JSON object, no other text.""")

        return "\n".join(lines)
