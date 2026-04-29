#!/usr/bin/env python3
"""
Demo visual del TUI — sin MT4 ni agente.
Ejecutar: python tests/tui_demo.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import threading
from tui import TUI

ACCOUNT = {
    "balance": 3986.58,
    "equity": 3986.58,
    "free_margin": 3821.30,
    "currency": "USD",
}

MARKET = {
    "price": {"bid": 4568.20, "ask": 4568.53, "spread": 0.33},
    "atr_h1": 15.45,
    "session": "London",
    "day_ohlc": {
        "prev_high": 4701.19,
        "prev_low": 4554.91,
        "prev_close": 4595.62,
        "today_open": 4595.64,
    },
}

POSITIONS = [
    {
        "ticket": 73811639,
        "type": "SELL",
        "lots": 0.03,
        "open": 4583.00,
        "sl": 4610.00,
        "tp": 4530.00,
        "profit": -14.22,
    }
]

LOG_ENTRIES = [
    ("CYCLE START", "INFO"),
    ("DATA OK — price=4568.20  session=London  positions=1", "INFO"),
    ("AGENT — decision=SELL  confidence=0.65", "INFO"),
    (
        "AGENT REASONING — H4 structure is firmly bearish: price broke below the 4620 area "
        "in a single aggressive candle, extending to a new weekly low at 4550.81",
        "INFO",
    ),
    ("EXECUTOR — SELL executed ticket=73811639 lots=0.03 sl=4610.00 tp=4530.00", "OK"),
    ("CYCLE END (113.8s)", "INFO"),
    ("Sleeping 786.1s until next cycle", "INFO"),
    ("CYCLE START", "INFO"),
    ("DATA OK — price=4555.71  session=London  positions=1", "INFO"),
    ("AGENT — decision=WAIT  confidence=0.00", "INFO"),
    (
        "AGENT REASONING — H4 bias is firmly bearish: the structure from 04/28 shows a clean "
        "BOS to the downside, a cascade from ~4730 to ~4550 with lower highs and lower lows",
        "INFO",
    ),
    ("EXECUTOR — WAIT: no action", "INFO"),
    ("CYCLE END (57.6s)", "INFO"),
    ("Sleeping 842.5s until next cycle", "INFO"),
]


def run_demo(tui: TUI) -> None:
    # fase 1: sin conexión inicial
    tui.set_state("Conectando a MT4...", "Ciclo 0")
    time.sleep(0.8)

    # fase 2: datos de cuenta y mercado
    tui.update_account(ACCOUNT)
    tui.update_market(MARKET)
    tui.update_positions([])
    tui.set_state("Recopilando datos...", "Ciclo 1  ·  Turno 1/3")

    for msg, lvl in LOG_ENTRIES[:3]:
        tui.log(msg, lvl)
        time.sleep(0.15)

    time.sleep(0.4)

    # fase 3: decisión del agente
    tui.set_state("Consultando agente...", "Ciclo 1  ·  Turno 2/3")
    tui.log(LOG_ENTRIES[3][0], LOG_ENTRIES[3][1])
    time.sleep(0.8)

    tui.update_decision({
        "decision": "SELL",
        "reasoning": (
            "H4 structure is firmly bearish following a decisive BOS on 04.28 "
            "when price broke below the 4620 area in a single aggressive candle, "
            "extending to a new weekly low at 4550.81."
        ),
    })

    # fase 4: ejecución con posición abierta
    tui.set_state("Ejecutando...", "Ciclo 1  ·  Turno 3/3")
    time.sleep(0.4)
    tui.update_positions(POSITIONS)
    tui.log(LOG_ENTRIES[4][0], LOG_ENTRIES[4][1])
    tui.log(LOG_ENTRIES[5][0], LOG_ENTRIES[5][1])
    time.sleep(0.3)

    # fase 5: ciclo 2 con timer
    cycle_secs = 30
    tui.set_state("Esperando próximo ciclo...", "Ciclo 1  ·  Turno 1/3")
    tui.start_timer(1, cycle_secs)
    tui.log(f"Sleeping {cycle_secs}s until next cycle", "INFO")

    for msg, lvl in LOG_ENTRIES[6:]:
        tui.log(msg, lvl)
        time.sleep(0.08)

    # fase 6: ciclo 2
    tui.set_state("Recopilando datos...", "Ciclo 2  ·  Turno 1/3")
    tui.update_market({**MARKET, "price": {"bid": 4555.71, "ask": 4556.04, "spread": 0.33}})
    time.sleep(0.3)
    tui.set_state("Consultando agente...", "Ciclo 2  ·  Turno 2/3")
    time.sleep(0.6)
    tui.update_decision({
        "decision": "WAIT",
        "reasoning": (
            "Already in a SELL position; structure unchanged. "
            "Waiting for TP at 4530 or stop condition."
        ),
    })
    tui.set_state("Esperando próximo ciclo...", "Ciclo 2  ·  Turno 1/3")
    tui.start_timer(2, 806)

    # dejar el timer corriendo para que se vea la barra en movimiento
    try:
        while True:
            time.sleep(1)
    except Exception:
        pass


def main() -> None:
    tui = TUI()
    tui.start()

    demo_thread = threading.Thread(target=run_demo, args=(tui,), daemon=True)
    demo_thread.start()

    try:
        demo_thread.join()
    except KeyboardInterrupt:
        pass
    finally:
        tui.stop()


if __name__ == "__main__":
    main()
