import sys
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


def main():
    tui    = TUI()
    logger = AurumLogger(tui=tui)
    mt4    = MT4Client(config.MT4_HOST, config.MT4_PORT)
    sched  = Scheduler()

    cycle_num = [0]

    def cycle():
        n = cycle_num[0] + 1
        cycle_num[0] = n

        logger.cycle_start()

        # Phase 1 — data collection
        tui.set_state("Recopilando datos...", f"Ciclo {n}  ·  Turno 1/3")
        context = build_context(mt4)
        tui.update_account(context["account"])
        tui.update_market(context)
        tui.update_positions(context["positions"])

        # Phase 2 — agent
        tui.set_state("Consultando agente...", f"Ciclo {n}  ·  Turno 2/3")
        market_text   = serialize_for_prompt(context)
        system_prompt = open(f"{config.STRATEGY_DIR}/system_prompt.md", encoding="utf-8").read()
        decision      = call_agent(market_text, system_prompt, config.STRATEGY_DIR)
        tui.update_decision(decision)

        # Phase 3 — execution
        tui.set_state("Ejecutando...", f"Ciclo {n}  ·  Turno 3/3")
        result = execute(decision, context, mt4, config)

        logger.log_cycle(context, decision, result)

    def on_sleep(secs, weekend=False):
        n = cycle_num[0]
        if weekend:
            tui.set_state("Fin de semana — mercado cerrado",
                          f"Ciclo {n}")
        else:
            tui.set_state("Esperando próximo ciclo...",
                          f"Ciclo {n}  ·  Turno 1/3")
        tui.start_timer(n, secs)
        logger.info(f"Sleeping {secs:.1f}s until next cycle")

    def on_error(exc):
        logger.error(str(exc))
        if isinstance(exc, MT4ConnectionError):
            tui.set_disconnected()
            tui.set_state("Sin conexión MT4", str(exc)[:80])
        else:
            tui.set_state(f"Error: {type(exc).__name__}", str(exc)[:80])

    try:
        tui.start()
        logger.info("AURUM iniciando...")

        try:
            mt4.connect()
        except MT4ConnectionError as e:
            logger.error(str(e))
            tui.set_state("Sin conexión MT4 — reintentando en cada ciclo")

        sched.run(cycle, on_sleep=on_sleep, on_error=on_error)

    except KeyboardInterrupt:
        pass
    finally:
        tui.stop()


if __name__ == "__main__":
    main()
