import config
from agent.caller import call_agent
from bridge.mt4_client import MT4Client
from data.processor import build_context, serialize_for_prompt
from logger import AurumLogger
from risk.executor import execute
from scheduler import Scheduler


def main():
    logger = AurumLogger()
    mt4    = MT4Client(config.MT4_HOST, config.MT4_PORT)
    sched  = Scheduler()

    def cycle():
        logger.cycle_start()
        context       = build_context(mt4)
        market_text   = serialize_for_prompt(context)
        system_prompt = open(f"{config.STRATEGY_DIR}/system_prompt.md", encoding="utf-8").read()
        decision      = call_agent(market_text, system_prompt, config.STRATEGY_DIR)
        result        = execute(decision, context, mt4, config)
        logger.log_cycle(context, decision, result)

    logger.info("AURUM starting...")
    mt4.connect()
    sched.run(cycle)


if __name__ == "__main__":
    main()
