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
| `aurum.py` | Entry point. Orchestrates the 4-phase cycle: data → state → agent → execute. |
| `src/config.py` | Global constants (MT4 host, symbol, magic number, `STATE_FILE`). |
| `src/scheduler.py` | Cycle timing control, weekend sleep, killzone filter, error backoff. |
| `src/tui.py` | Textual terminal interface. API: `TUI.start/stop/log/update_*`. |
| `src/logger.py` | `AurumLogger`: writes to `logs/` and the TUI simultaneously. |
| `src/agent/caller.py` | Calls the `claude` CLI in a subprocess, parses JSON response and `bot_managed_state`. |
| `src/bridge/mt4_client.py` | TCP client for MT4. Raises `MT4ConnectionError` on failure. |
| `src/bridge/AURUM_Bridge.mq4` | Expert Advisor in MT4 that serves the socket. |
| `src/data/processor.py` | Builds the market context and serializes it for the prompt (injects `STRUCTURAL_STATE`). |
| `src/risk/executor.py` | Validates the agent decision and executes orders in MT4. |
| `src/strategy/system_prompt.md` | Agent system prompt. Edit to change the strategy. |
| `src/strategy/.claude/settings.json` | Disables Claude Code auto-memory for the agent subprocess. |
| `src/state/schema.py` | Default state structure, `validate_bot_managed()`, `default_bot_managed()`. |
| `src/state/io.py` | `load_state()` / `save_state()` with automatic `.previous.json` backup. |
| `src/state/updater.py` | `update_code_managed_state()`: detects BOS/CHoCH, liquidity sweeps, POIs, distances, ATR. |
| `state/structural_state.json` | Persistent structural state (auto-created, human-readable JSON). |
| `state/structural_state.previous.json` | Backup of the previous cycle's state (auto-created). |
| `state/economic_events.json` | Manual economic calendar. Edit to add upcoming high-impact events. |
| `tests/` | Manual test scripts. Do not require MT4 or an active agent. |
| `logs/` | Runtime logs. Ignored by git. |

## Common commands

```bash
python aurum.py                  # start the bot
python aurum.py --reset-bot-state  # reset bot interpretive memory (keeps code_managed)
python tests/tui_demo.py         # preview the TUI with simulated data
```

## Conventions

- The agent returns JSON with `decision` ∈ {BUY, SELL, WAIT, CLOSE, HOLD}.
- `confidence < 0.60` → executor forces WAIT without opening a position.
- Single symbol (XAUUSD). No simultaneous multi-position by design.
- Structured logs in `logs/aurum_session_*.log` and `logs/aurum_decisions_*.jsonl` (manual rotation).
- Structural state persists across cycles in `state/structural_state.json`. Two sections:
  - `code_managed` — objective facts updated automatically each cycle (BOS/CHoCH, liquidity pools, POIs, distances, ATR, position metrics).
  - `bot_managed` — interpretive memory maintained by the agent (bias, pending setup, narrative).
- Economic events are disabled until a calendar source is configured (`updater.py` line `_update_economic_events`).
