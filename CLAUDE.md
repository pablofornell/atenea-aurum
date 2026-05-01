# AURUM

Algorithmic trading bot for Gold/XAUUSD. Runs cycles every ~15 min: collects data from MT4, consults Claude as an agent, executes the decision via the risk manager.

**Developer:** Pablo Fornell — pablo.fornell.perinan@gmail.com

## Stack

- Python 3.13, textual (TUI), rich
- Claude API invoked as a subprocess (`agent/caller.py` calls the `claude` CLI)
- MT4 via TCP socket (MQL4 ↔ Python bridge in `bridge/`)

## Folder map

| Path | Responsibility |
|---|---|
| `aurum.py` | Entry point. Adds `src/` to the path and orchestrates the cycle. |
| `src/config.py` | Global constants (MT4 host, symbol, magic number). |
| `src/scheduler.py` | Cycle timing control, weekend sleep, error backoff. |
| `src/tui.py` | Textual terminal interface. API: `TUI.start/stop/log/update_*`. |
| `src/logger.py` | `AurumLogger`: writes to `logs/aurum.log` and the TUI simultaneously. |
| `src/agent/caller.py` | Calls the `claude` CLI in a subprocess, parses JSON response. |
| `src/bridge/mt4_client.py` | TCP client for MT4. Raises `MT4ConnectionError` on failure. |
| `src/bridge/AURUM_Bridge.mq4` | Expert Advisor in MT4 that serves the socket. |
| `src/data/processor.py` | Builds the market context and serializes it for the prompt. |
| `src/risk/executor.py` | Validates the agent decision and executes orders in MT4. |
| `src/strategy/system_prompt.md` | Agent system prompt. Edit to change the strategy. |
| `tests/` | Manual test scripts. Do not require MT4 or an active agent. |
| `logs/` | Runtime logs. Ignored by git. |

## Common commands

```bash
python aurum.py          # start the bot
python tests/tui_demo.py # preview the TUI with simulated data
```

## Conventions

- The agent returns JSON with `decision` ∈ {BUY, SELL, WAIT, CLOSE}.
- `confidence < 0.60` → executor forces WAIT without opening a position.
- Single symbol (XAUUSD). No simultaneous multi-position by design.
- Structured logs in `logs/aurum.log` (manual rotation).
