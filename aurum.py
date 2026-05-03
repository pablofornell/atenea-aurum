import importlib
import sys
import threading
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import config
from agent.caller import call_agent
from bridge.mt4_client import MT4Client, MT4ConnectionError
from data.processor import build_context, serialize_for_prompt
from logger import AurumLogger
from risk.executor import execute
from scheduler import Scheduler
from tui import TUI


def _near_target(pos: dict, current_price: float) -> bool:
    """True when a position has progressed ≥80% of its TP distance from entry."""
    entry = pos["open"]
    tp    = pos["tp"]
    if tp == 0 or tp == entry:
        return False
    is_buy   = str(pos["type"]).upper() in ("BUY", "0")
    progress = (
        (current_price - entry) / (tp - entry)
        if is_buy
        else (entry - current_price) / (entry - tp)
    )
    return progress >= 0.80


def main():
    tui    = TUI()
    logger = AurumLogger(tui=tui)
    mt4    = MT4Client(config.MT4_HOST, config.MT4_PORT)
    sched  = Scheduler()

    cycle_num   = [0]
    last_result = [None]

    def cycle():
        importlib.reload(config)
        n = cycle_num[0] + 1
        cycle_num[0] = n

        logger.cycle_start()

        # Phase 1 — data collection
        tui.set_state("Collecting data...", f"Cycle {n}  ·  Step 1/3")
        context = build_context(mt4)
        tui.update_account(context["account"])
        tui.update_market(context)
        tui.update_positions(context["positions"])

        # Phase 2 — agent (receives last cycle result so it can react to errors)
        tui.set_state("Querying agent...", f"Cycle {n}  ·  Step 2/3")
        market_text   = serialize_for_prompt(context, last_result=last_result[0])
        system_prompt = open(f"{config.STRATEGY_DIR}/system_prompt.md", encoding="utf-8").read()
        decision      = call_agent(market_text, system_prompt, config.STRATEGY_DIR)
        tui.update_decision(decision)

        # Phase 3 — execution
        tui.set_state("Executing...", f"Cycle {n}  ·  Step 3/3")
        result = execute(decision, context, mt4, config)
        last_result[0] = result

        logger.log_cycle(context, decision, result)

        # Phase 4 — adaptive interval
        positions = context["positions"]
        price     = context["price"]["bid"]
        if positions and _near_target(positions[0], price):
            base_secs = config.INTERVAL_NEAR_TARGET
        elif positions:
            base_secs = config.INTERVAL_WITH_POSITION
        else:
            base_secs = config.INTERVAL_NO_POSITION

        agent_mins = decision.get("next_check_minutes")
        if isinstance(agent_mins, (int, float)) and 1 <= agent_mins <= 15:
            agent_secs = int(agent_mins) * 60
            next_secs  = min(base_secs, agent_secs)
            if next_secs < base_secs:
                logger.info(
                    f"Agent accelerated poll: {agent_mins}min → {next_secs}s (base {base_secs}s)"
                )
        else:
            next_secs = base_secs

        return next_secs

    def on_sleep(secs, weekend=False, killzone=False):
        n = cycle_num[0]
        if weekend:
            tui.set_state("Weekend — market closed",
                          f"Cycle {n}")
        elif killzone:
            tui.set_state("Outside killzone — waiting",
                          f"Cycle {n}")
        else:
            tui.set_state("Waiting for next cycle...",
                          f"Cycle {n}  ·  Step 1/3")
        tui.start_timer(n, secs)
        logger.info(f"Sleeping {secs:.1f}s until next cycle")

    def on_error(exc):
        logger.error(str(exc))
        if isinstance(exc, MT4ConnectionError):
            tui.set_disconnected()
            tui.set_state("No MT4 connection", str(exc)[:80])
        else:
            tui.set_state(f"Error: {type(exc).__name__}", str(exc)[:80])

    _stop_poll = threading.Event()

    def _poll_positions():
        while not _stop_poll.wait(5.0):
            try:
                tui.update_positions(mt4.get_positions())
            except Exception:
                pass

    try:
        tui.start()
        logger.info("AURUM starting...")

        try:
            mt4.connect()
        except MT4ConnectionError as e:
            logger.error(str(e))
            tui.set_state("No MT4 connection — retrying each cycle")

        threading.Thread(target=_poll_positions, daemon=True, name="positions-poll").start()
        sched.run(cycle, cfg=config, on_sleep=on_sleep, on_error=on_error)

    except KeyboardInterrupt:
        pass
    finally:
        _stop_poll.set()
        tui.stop()


if __name__ == "__main__":
    main()
