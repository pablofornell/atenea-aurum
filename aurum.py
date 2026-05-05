import importlib
import os
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
from state.io import load_state, save_state
from state.schema import default_bot_managed, validate_bot_managed
from state.updater import update_code_managed_state
from tui import TUI


def _tp_progress(pos: dict, current_price: float) -> float:
    """Returns TP progress as a fraction 0.0–1.0+ (can exceed 1.0 past TP)."""
    entry = pos["open"]
    tp    = pos["tp"]
    if tp == 0 or tp == entry:
        return 0.0
    is_buy = str(pos["type"]).upper() in ("BUY", "0")
    return (
        (current_price - entry) / (tp - entry)
        if is_buy
        else (entry - current_price) / (entry - tp)
    )


def _near_target(pos: dict, current_price: float) -> bool:
    """True when a position has progressed ≥80% of its TP distance from entry."""
    return _tp_progress(pos, current_price) >= 0.80


def _handle_reset(state_file: str) -> None:
    """Reset bot_managed state to defaults without touching code_managed."""
    state = load_state(state_file)
    state["bot_managed"] = default_bot_managed()
    save_state(state, state_file)
    print("bot_managed state reset to defaults.")
    print(f"State file: {state_file}")


def main():
    # Resolve --mode before any config use so importlib.reload picks it up
    if "--mode" in sys.argv:
        idx = sys.argv.index("--mode")
        if idx + 1 >= len(sys.argv):
            print("Error: --mode requires an argument (demo or prod)")
            sys.exit(1)
        mode = sys.argv[idx + 1].lower()
        if mode not in ("demo", "prod"):
            print(f"Error: unknown mode '{mode}'. Use 'demo' or 'prod'.")
            sys.exit(1)
        os.environ["AURUM_MODE"] = mode

    if "--reset-bot-state" in sys.argv:
        importlib.reload(config)
        _handle_reset(config.STATE_FILE)
        return

    importlib.reload(config)  # apply AURUM_MODE before creating MT4Client
    tui    = TUI()
    logger = AurumLogger(tui=tui)
    mt4    = MT4Client(config.MT4_HOST, config.MT4_PORT)
    sched  = Scheduler()

    cycle_num        = [0]
    last_result      = [None]
    last_decision    = [None]   # previous cycle's full decision dict

    def cycle():
        importlib.reload(config)
        n = cycle_num[0] + 1
        cycle_num[0] = n

        logger.cycle_start()

        # Phase 1 — data collection
        tui.set_state("Collecting data...", f"Cycle {n}  ·  Step 1/4")
        context = build_context(mt4)
        tui.update_account(context["account"])
        tui.update_market(context)
        tui.update_positions(context["positions"])

        # Phase 2 — state update
        tui.set_state("Updating state...", f"Cycle {n}  ·  Step 2/4")
        state = load_state(config.STATE_FILE)
        changes = update_code_managed_state(
            state, context, last_decision[0], config
        )
        logger.log_state_changes(changes)

        # Breakeven guard — move SL to entry when ≥50% TP progress
        for pos in context["positions"]:
            price  = context["price"]["bid"]
            entry  = pos["open"]
            sl     = pos["sl"]
            tp     = pos["tp"]
            ticket = pos["ticket"]
            is_buy = str(pos["type"]).upper() in ("BUY", "0")
            at_be  = (sl >= entry) if is_buy else (sl <= entry)
            if not at_be and _tp_progress(pos, price) >= 0.50:
                if mt4.modify(ticket, entry, tp):
                    be_msg = f"BE — SL moved to entry {entry:.2f} (ticket={ticket}, ≥50% TP progress)"
                    logger.info(be_msg)
                    last_result[0] = be_msg

        # Phase 3 — agent
        tui.set_state("Querying agent...", f"Cycle {n}  ·  Step 3/4")
        market_text   = serialize_for_prompt(
            context,
            last_result=last_result[0],
            structural_state=state,
        )
        system_prompt = open(f"{config.STRATEGY_DIR}/system_prompt.md", encoding="utf-8").read()
        decision      = call_agent(market_text, system_prompt, config.STRATEGY_DIR)
        tui.update_decision(decision)

        # Validate and merge bot_managed_state from response
        raw_bm = decision.pop("_bot_managed_state", None)
        if raw_bm is not None:
            ok, err = validate_bot_managed(raw_bm)
            if ok:
                logger.log_state_decision_check(decision, state)
                state["bot_managed"] = raw_bm
            else:
                logger.warn(f"bot_managed_state validation failed: {err} — keeping previous")
        else:
            logger.warn("bot_managed_state missing from response — keeping previous")

        save_state(state, config.STATE_FILE)

        # Phase 4 — execution
        tui.set_state("Executing...", f"Cycle {n}  ·  Step 4/4")
        result = execute(decision, context, mt4, config)
        last_result[0] = result
        last_decision[0] = decision

        logger.log_cycle(context, decision, result)

        # Phase 5 — adaptive interval
        # Refresh positions from MT4 if a new order was just placed so the
        # interval reflects actual state (context snapshot was taken pre-execution)
        positions = context["positions"]
        action = decision.get("decision", "").upper()
        if action in ("BUY", "SELL") and not result.startswith(("WAIT", "ERROR")):
            try:
                positions = mt4.get_positions()
            except Exception:
                pass
        price = context["price"]["bid"]
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
                          f"Cycle {n}  ·  Step 1/4")
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
    _mt4_poll_ok = [True]

    def _poll_mt4():
        while not _stop_poll.wait(5.0):
            try:
                tui.update_positions(mt4.get_positions())
                tui.update_account(mt4.get_account())
                tui.update_market({"price": mt4.get_price(config.SYMBOL)})
                if not _mt4_poll_ok[0]:
                    _mt4_poll_ok[0] = True
                    logger.info("MT4 reconnected")
            except MT4ConnectionError:
                if _mt4_poll_ok[0]:
                    _mt4_poll_ok[0] = False
                    logger.error("MT4 connection lost")
                tui.set_disconnected()
            except Exception:
                pass

    try:
        tui.start()
        logger.info(f"AURUM starting... mode={config.MODE.upper()}  symbol={config.SYMBOL}  port={config.MT4_PORT}")

        try:
            mt4.connect()
            tui.set_connecting()
        except MT4ConnectionError as e:
            logger.error(str(e))
            tui.set_state("No MT4 connection — retrying each cycle")

        threading.Thread(target=_poll_mt4, daemon=True, name="mt4-poll").start()
        sched.run(cycle, cfg=config, on_sleep=on_sleep, on_error=on_error)

    except KeyboardInterrupt:
        pass
    finally:
        _stop_poll.set()
        tui.stop()


if __name__ == "__main__":
    main()
