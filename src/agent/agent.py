"""Aurum trading agent — orchestrates analysis and order execution."""
import time
import logging
import uuid
from typing import TYPE_CHECKING, Optional, Dict, Any

from src.mt4.bridge import MT4Bridge, MT4BridgeError
from src.mt4.screenshot import capture_mt4, ScreenshotError
from src.bridge.claude_bridge import call_claude
from src.db.storage import SessionStorage
from src.agent.prompts import SYSTEM_PROMPT
from src.agent.feedback_logger import FeedbackLogger

if TYPE_CHECKING:
    from src.ui.tui import AurumTUI

logger = logging.getLogger(__name__)


class AurumAgent:
    """Autonomous trading agent for XAUUSD on MT4."""

    def __init__(
        self,
        mt4_bridge: MT4Bridge,
        storage: SessionStorage,
        feedback_logger: Optional[FeedbackLogger] = None,
        cycle_interval: int = 900,
        tui: Optional["AurumTUI"] = None,
    ):
        self.mt4_bridge = mt4_bridge
        self.storage = storage
        self.flog = feedback_logger
        self.cycle_interval = cycle_interval
        self.tui = tui
        self.running = False

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self):
        """Main loop: run analysis cycles indefinitely."""
        self.running = True
        logger.info("Aurum agent starting main loop")

        if self.flog:
            self.flog.run_start(cycle_interval=self.cycle_interval)

        total_cycles = 0
        total_errors = 0
        start_account = self._safe_account()

        try:
            while self.running:
                session_id = str(uuid.uuid4())
                total_cycles += 1
                logger.info(f"Starting cycle {total_cycles}: {session_id}")

                if self.tui:
                    self.tui.set_status("Iniciando ciclo…", cycle=total_cycles)

                if self.flog:
                    self.flog.cycle_start(session_id)

                cycle_start = time.time()
                try:
                    self.run_cycle(session_id, cycle_num=total_cycles)
                except Exception as e:
                    logger.error(f"Cycle error: {e}", exc_info=True)
                    total_errors += 1
                    if self.flog:
                        self.flog.error("cycle_exception", str(e), session_id=session_id)

                cycle_dur = time.time() - cycle_start
                if self.flog:
                    self.flog.cycle_end(session_id, cycle_dur, final_action="—")

                interval = self._current_interval()
                remaining = interval - cycle_dur
                if remaining > 0:
                    logger.info(f"Sleeping {remaining:.1f}s until next cycle")
                    if self.tui:
                        self.tui.set_status("Esperando próximo ciclo…", cycle=total_cycles)
                        self.tui.set_next_cycle(remaining, interval)
                    time.sleep(remaining)

        except KeyboardInterrupt:
            logger.info("Agent stopped by user (Ctrl+C)")
        finally:
            self.running = False
            if self.flog:
                end_account = self._safe_account()
                self.flog.run_end(
                    total_cycles=total_cycles,
                    total_errors=total_errors,
                    start_balance=start_account.get("balance") if start_account else None,
                    end_balance=end_account.get("balance") if end_account else None,
                    start_equity=start_account.get("equity") if start_account else None,
                    end_equity=end_account.get("equity") if end_account else None,
                )

    def _safe_account(self) -> Optional[dict]:
        try:
            return self.mt4_bridge.get_account()
        except Exception:
            return None

    def _current_interval(self) -> int:
        """5 min if a position is open, 15 min if flat."""
        try:
            if self.mt4_bridge.get_positions():
                return 300
        except Exception:
            pass
        return self.cycle_interval

    # ------------------------------------------------------------------
    # Cycle
    # ------------------------------------------------------------------

    def run_cycle(self, session_id: str, cycle_num: int = 0):
        """Execute one full analysis cycle (may span multiple turns for timeframe changes)."""
        logger.info(f"Cycle {session_id}: Starting")

        if self.tui:
            self.tui.set_status("Capturando pantalla MT4…", cycle=cycle_num)

        try:
            screenshot_path = capture_mt4()
            logger.info(f"Screenshot captured: {screenshot_path}")
        except ScreenshotError as e:
            logger.error(f"Failed to capture MT4: {e}")
            if self.tui:
                self.tui.set_status("Error: captura de pantalla fallida", cycle=cycle_num)
            if self.flog:
                self.flog.error("screenshot", str(e), session_id=session_id)
            return

        if self.flog:
            self.flog.screenshot(session_id, turn=0, path=screenshot_path)

        current_timeframe = "H1"
        turn = 0
        max_turns = 10

        while turn < max_turns:
            turn += 1
            logger.info(f"Cycle {session_id}: Turn {turn}")

            if self.tui:
                self.tui.set_status("Obteniendo contexto de mercado…",
                                    cycle=cycle_num, turn=turn, max_turns=max_turns)

            market_context = self._get_market_context()

            if self.tui:
                self.tui.update_account(market_context.get("account"))
                self.tui.update_positions(market_context.get("positions", []))
                self.tui.update_market(
                    market_context.get("price"),
                    market_context.get("server_time"),
                )

            if self._is_connection_lost(market_context):
                logger.warning("MT4 connection lost, attempting reconnect...")
                if self.tui:
                    self.tui.set_status("Reconectando a MT4…", cycle=cycle_num, turn=turn)
                if self.flog:
                    self.flog.connection_lost(session_id=session_id, turn=turn)
                reconnected = self.mt4_bridge.reconnect()
                if self.flog:
                    self.flog.reconnect(reconnected, attempts=5, session_id=session_id)
                if not reconnected:
                    logger.error("Could not reconnect to MT4, skipping cycle")
                    if self.tui:
                        self.tui.set_status("Error: reconexión MT4 fallida", cycle=cycle_num)
                    if self.flog:
                        self.flog.error("connection", "Reconnect failed, cycle aborted",
                                        session_id=session_id, turn=turn)
                    return
                market_context = self._get_market_context()

            if self.flog:
                self.flog.market_context(session_id, turn, market_context)

            analysis_prompt = self._build_analysis_prompt(market_context)
            history = self.storage.get_session_history(session_id)

            if self.tui:
                self.tui.set_status("Llamando a Claude…", cycle=cycle_num, turn=turn)

            claude_start = time.time()
            try:
                response = call_claude(
                    prompt=analysis_prompt,
                    screenshot_path=screenshot_path,
                    session_history=history,
                    system_prompt=SYSTEM_PROMPT
                )
            except Exception as e:
                logger.error(f"Claude call failed: {e}")
                if self.tui:
                    self.tui.set_status("Error: llamada a Claude fallida", cycle=cycle_num)
                if self.flog:
                    self.flog.error("claude_call", str(e), session_id=session_id, turn=turn)
                return
            claude_elapsed = time.time() - claude_start
            logger.info(f"Claude responded in {claude_elapsed:.1f}s")

            if not response.get("ok"):
                err = response.get("error", "unknown")
                logger.error(f"Claude error: {err}")
                if self.tui:
                    self.tui.set_status(f"Error Claude: {err[:50]}", cycle=cycle_num)
                error_type = "timeout" if "timed out" in err else "claude_error"
                if self.flog:
                    self.flog.error(error_type, err, session_id=session_id, turn=turn)
                self.storage.save_turn(session_id=session_id, role="system",
                                       content=f"Error calling Claude: {err}")
                return

            action = response.get("action")
            raw_response = response.get("raw", "")

            if self.flog and action:
                self.flog.claude_decision(session_id, turn, action, raw_response, claude_elapsed)

            if action and self.tui:
                self.tui.set_status("Procesando decisión…", cycle=cycle_num, turn=turn)
                self.tui.set_last_action(
                    action.get("action", "?"),
                    action.get("reasoning", ""),
                )

            self.storage.save_turn(
                session_id=session_id,
                role="assistant",
                content=raw_response,
                screenshot_path=screenshot_path,
                timeframe=current_timeframe
            )

            if not action:
                logger.warning(f"Invalid action from Claude: {raw_response}")
                self.storage.save_turn(session_id=session_id, role="system",
                                       content="Failed to parse action JSON")
                if self.flog:
                    self.flog.error("parse_error", f"Could not parse JSON: {raw_response[:200]}",
                                    session_id=session_id, turn=turn)
                return

            cycle_done = self._execute_action(action, session_id, screenshot_path, turn,
                                              cycle_num=cycle_num)

            if cycle_done:
                logger.info(f"Cycle {session_id}: Complete (action={action.get('action')})")
                return

            if action.get("action") == "CHANGE_TIMEFRAME":
                new_timeframe = action.get("timeframe", current_timeframe)
                logger.info(f"Changing timeframe to {new_timeframe}")
                if self.tui:
                    self.tui.set_status(f"Cambiando timeframe a {new_timeframe}…",
                                        cycle=cycle_num, turn=turn)

                time.sleep(2)
                reconnected = self.mt4_bridge.reconnect()
                if self.flog:
                    self.flog.reconnect(reconnected, attempts=5, session_id=session_id)
                if not reconnected:
                    logger.error("Lost MT4 connection after timeframe change, ending cycle")
                    if self.tui:
                        self.tui.set_status("Error: reconexión tras cambio de TF", cycle=cycle_num)
                    if self.flog:
                        self.flog.error("connection", "Reconnect failed after CHANGE_TIMEFRAME",
                                        session_id=session_id, turn=turn)
                    return

                try:
                    screenshot_path = capture_mt4()
                    current_timeframe = new_timeframe
                    logger.info(f"New screenshot: {screenshot_path}")
                    if self.flog:
                        self.flog.screenshot(session_id, turn=turn, path=screenshot_path)
                except ScreenshotError as e:
                    logger.error(f"Failed to capture new screenshot: {e}")
                    if self.flog:
                        self.flog.error("screenshot", str(e), session_id=session_id, turn=turn)
                    return

                continue

    # ------------------------------------------------------------------
    # Action execution
    # ------------------------------------------------------------------

    def _execute_action(self, action: Dict[str, Any], session_id: str,
                        screenshot_path: str, turn: int, cycle_num: int = 0) -> bool:
        """Execute a trading action. Returns True if cycle should end."""
        action_type = action.get("action")
        reasoning = action.get("reasoning", "")
        logger.info(f"Executing action: {action_type}")
        if self.tui:
            self.tui.set_status(f"Ejecutando: {action_type}", cycle=cycle_num, turn=turn)

        if action_type == "DONE":
            logger.info("Claude finished analysis (DONE)")
            self.storage.save_turn(session_id=session_id, role="system",
                                   content="Analysis complete, waiting for next cycle")
            if self.flog:
                self.flog.action_result(session_id, turn, "DONE", ok=True, detail={})
            return True

        elif action_type == "CHANGE_TIMEFRAME":
            timeframe = action.get("timeframe")
            logger.info(f"Claude requested timeframe change: {timeframe}")
            try:
                self.mt4_bridge.set_timeframe("XAUUSD", timeframe)
                self.storage.save_turn(session_id=session_id, role="system",
                                       content=f"Timeframe changed to {timeframe}")
                if self.flog:
                    self.flog.action_result(session_id, turn, "CHANGE_TIMEFRAME", ok=True,
                                            detail={"timeframe": timeframe})
            except MT4BridgeError as e:
                logger.error(f"Failed to change timeframe: {e}")
                self.storage.save_turn(session_id=session_id, role="system",
                                       content=f"Error changing timeframe: {e}")
                if self.flog:
                    self.flog.action_result(session_id, turn, "CHANGE_TIMEFRAME", ok=False,
                                            detail={"error": str(e)})
                return True
            return False

        elif action_type == "BUY":
            return self._place_order("BUY", action, session_id, turn, reasoning)

        elif action_type == "SELL":
            return self._place_order("SELL", action, session_id, turn, reasoning)

        elif action_type == "CLOSE":
            ticket = action.get("ticket")
            try:
                self.mt4_bridge.close(ticket)
                self.storage.log_order(session_id=session_id, action="CLOSE",
                                       symbol="XAUUSD", lots=0, sl=0, tp=0,
                                       ticket=ticket, result="OK")
                logger.info(f"Position closed: ticket={ticket}")
                self.storage.save_turn(session_id=session_id, role="system",
                                       content=f"Position closed (ticket={ticket})")
                if self.flog:
                    self.flog.action_result(session_id, turn, "CLOSE", ok=True,
                                            detail={"ticket": ticket})
            except Exception as e:
                logger.error(f"Close order failed: {e}")
                self.storage.save_turn(session_id=session_id, role="system",
                                       content=f"Close failed: {e}")
                if self.flog:
                    self.flog.action_result(session_id, turn, "CLOSE", ok=False,
                                            detail={"ticket": ticket, "error": str(e)})
                    self.flog.error("order_failed", str(e), session_id=session_id, turn=turn)
            return True

        elif action_type == "MODIFY":
            ticket = action.get("ticket")
            sl = action.get("sl")
            tp = action.get("tp")
            try:
                self.mt4_bridge.modify(ticket, sl, tp)
                self.storage.log_order(session_id=session_id, action="MODIFY",
                                       symbol="XAUUSD", lots=0, sl=sl, tp=tp,
                                       ticket=ticket, result="OK")
                logger.info(f"Position modified: ticket={ticket}, sl={sl}, tp={tp}")
                self.storage.save_turn(session_id=session_id, role="system",
                                       content=f"Position modified (ticket={ticket}, SL={sl}, TP={tp})")
                if self.flog:
                    self.flog.action_result(session_id, turn, "MODIFY", ok=True,
                                            detail={"ticket": ticket, "sl": sl, "tp": tp})
            except MT4BridgeError as e:
                error_str = str(e)
                hint = ""
                if "modify_failed" in error_str:
                    try:
                        stop_level = self.mt4_bridge.get_stop_level("XAUUSD")
                        hint = (
                            f" Broker stop level for XAUUSD is {stop_level:.2f} pts. "
                            f"SL must be at least {stop_level:.2f} away from current price."
                        )
                    except Exception:
                        hint = " Likely cause: SL too close to current price (broker stop level)."
                logger.error(f"Modify order failed: {e}{hint}")
                self.storage.save_turn(session_id=session_id, role="system",
                                       content=f"Modify failed: {e}{hint}")
                if self.flog:
                    self.flog.action_result(session_id, turn, "MODIFY", ok=False,
                                            detail={"ticket": ticket, "sl": sl, "tp": tp,
                                                    "error": error_str + hint})
                    self.flog.error("modify_failed", error_str + hint,
                                    context={"ticket": ticket, "sl": sl, "tp": tp},
                                    session_id=session_id, turn=turn)
            except Exception as e:
                logger.error(f"Modify order failed: {e}")
                self.storage.save_turn(session_id=session_id, role="system",
                                       content=f"Modify failed: {e}")
                if self.flog:
                    self.flog.error("modify_failed", str(e), session_id=session_id, turn=turn)
            return True

        else:
            logger.warning(f"Unknown action: {action_type}")
            self.storage.save_turn(session_id=session_id, role="system",
                                   content=f"Unknown action: {action_type}")
            if self.flog:
                self.flog.error("unknown_action", f"Unrecognised action: {action_type}",
                                session_id=session_id, turn=turn)
            return True

    def _place_order(self, side: str, action: dict, session_id: str,
                     turn: int, reasoning: str) -> bool:
        """Shared BUY/SELL logic with duplicate-position guard."""
        symbol = action.get("symbol", "XAUUSD")
        lots = action.get("lots", 0.1)
        sl = action.get("sl")
        tp = action.get("tp")

        try:
            existing = self.mt4_bridge.get_positions()
            if existing:
                tickets = [str(p["ticket"]) for p in existing]
                msg = f"{side} rejected: position(s) already open ({', '.join(tickets)}). Close or modify instead."
                logger.warning(f"{side} blocked: {tickets}")
                self.storage.save_turn(session_id=session_id, role="system", content=msg)
                if self.flog:
                    self.flog.action_result(session_id, turn, side, ok=False,
                                            detail={"reason": "duplicate_position",
                                                    "open_tickets": tickets})
                    self.flog.error("duplicate_position", msg,
                                    context={"open_tickets": tickets},
                                    session_id=session_id, turn=turn)
                return True

            fn = self.mt4_bridge.buy if side == "BUY" else self.mt4_bridge.sell
            result = fn(symbol, lots, sl, tp)
            ticket = result.get("ticket")
            self.storage.log_order(session_id=session_id, action=side, symbol=symbol,
                                   lots=lots, sl=sl, tp=tp, ticket=ticket, result="OK")
            logger.info(f"{side} order placed: ticket={ticket}, lots={lots}")
            self.storage.save_turn(
                session_id=session_id, role="system",
                content=f"{side} order placed successfully (ticket={ticket})\nReasoning: {reasoning}"
            )
            if self.flog:
                self.flog.action_result(session_id, turn, side, ok=True,
                                        detail={"ticket": ticket, "lots": lots,
                                                "sl": sl, "tp": tp, "symbol": symbol})

        except Exception as e:
            logger.error(f"{side} order failed: {e}")
            self.storage.log_order(session_id=session_id, action=side, symbol=symbol,
                                   lots=lots, sl=sl, tp=tp, result="ERROR",
                                   error_message=str(e))
            self.storage.save_turn(session_id=session_id, role="system",
                                   content=f"{side} order failed: {e}")
            if self.flog:
                self.flog.action_result(session_id, turn, side, ok=False,
                                        detail={"error": str(e), "sl": sl, "tp": tp})
                self.flog.error("order_failed", str(e),
                                context={"side": side, "sl": sl, "tp": tp},
                                session_id=session_id, turn=turn)

        return True

    # ------------------------------------------------------------------
    # Market context
    # ------------------------------------------------------------------

    def _is_connection_lost(self, context: dict) -> bool:
        """Returns True if all MT4 data calls failed simultaneously."""
        return (
            context.get("price") is None
            and context.get("account") is None
            and context.get("positions") == []
            and context.get("server_time") is None
        )

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

        try:
            context["atr"] = self.mt4_bridge.get_atr("XAUUSD", 14)
        except Exception as e:
            logger.warning(f"get_atr failed: {e}")
            context["atr"] = None

        try:
            context["day_ohlc"] = self.mt4_bridge.get_day_ohlc("XAUUSD")
        except Exception as e:
            logger.warning(f"get_day_ohlc failed: {e}")
            context["day_ohlc"] = None

        try:
            context["week_hl"] = self.mt4_bridge.get_week_hl("XAUUSD")
        except Exception as e:
            logger.warning(f"get_week_hl failed: {e}")
            context["week_hl"] = None

        return context

    @staticmethod
    def _trading_session(server_time: str) -> str:
        """Derive trading session name from MT4 server time string (broker = GMT+2/+3)."""
        try:
            hour = int(server_time[11:13])
        except (TypeError, IndexError, ValueError):
            return "Unknown"
        # Approximate GMT offsets: broker server is typically GMT+2 (winter) / GMT+3 (summer).
        # We treat server time as GMT+2 for a conservative estimate.
        gmt = (hour - 2) % 24
        if 0 <= gmt < 7:
            return "Asia (low volatility — tight ranges, avoid breakout trades)"
        if 7 <= gmt < 10:
            return "London Open (rising volatility — watch for trend initiation)"
        if 10 <= gmt < 13:
            return "London (high volatility — trend-following preferred)"
        if 13 <= gmt < 17:
            return "London/NY Overlap (peak volatility — highest liquidity, strong moves)"
        if 17 <= gmt < 22:
            return "New York (moderate-high volatility — continuation or reversal setups)"
        return "Late NY / Pre-Asia (low volatility — avoid new entries)"

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
            session = self._trading_session(server_time)
            lines.append(f"Server Time: {server_time}  |  Session: {session}")

        atr = market_context.get("atr")
        if atr is not None:
            sl_1x = round(atr * 1.0, 2)
            sl_15x = round(atr * 1.5, 2)
            lines.append(
                f"ATR(14): {atr:.2f} USD  →  "
                f"Suggested SL buffer: {sl_1x:.2f} (1×ATR) – {sl_15x:.2f} (1.5×ATR)"
            )

        ohlc = market_context.get("day_ohlc")
        if ohlc:
            bias = "BULLISH" if ohlc["td_open"] > ohlc["pd_close"] else "BEARISH"
            lines.append(
                f"\n## Key Daily Levels (XAUUSD)\n"
                f"  Prev Day  Open: {ohlc['pd_open']:.2f} | High: {ohlc['pd_high']:.2f} | "
                f"Low: {ohlc['pd_low']:.2f} | Close: {ohlc['pd_close']:.2f}\n"
                f"  Today     Open: {ohlc['td_open']:.2f}  "
                f"(gap bias vs PDC: {bias})"
            )

        week = market_context.get("week_hl")
        if week:
            lines.append(
                f"  Prev Week High: {week['pw_high']:.2f} | Low: {week['pw_low']:.2f}  |  "
                f"Curr Week High: {week['cw_high']:.2f} | Low: {week['cw_low']:.2f}"
            )

        positions = market_context.get("positions", [])
        if positions:
            lines.append(f"\nOpen Positions ({len(positions)}):")
            for p in positions:
                lines.append(
                    f"  #{p['ticket']} {p['type']} {p['lots']} lot @ {p['open_price']:.5f} | "
                    f"SL: {p['sl']:.5f} | TP: {p['tp']:.5f} | P&L: {p['profit']:+.2f}"
                )
        else:
            lines.append("\nOpen Positions: None")

        lines.append("""
## Chart Analysis
Analyze the chart screenshot together with the numerical context above and decide your next action.

Look for:
- Confluence between price action and the Key Daily/Weekly Levels listed above
- Trend direction and strength relative to PDC (previous day close) bias
- Momentum indicators visible on chart (RSI, EMAs)
- Entry and exit points with SL sized using the ATR buffer suggested above
- Risk/reward ratios (minimum 1:2); TP should be the next key level

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
