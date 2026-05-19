# AURUM

Algorithmic trading bot for Gold/XAUUSD. Every 15 minutes it collects market data from MetaTrader 4, consults Claude as an AI agent using a pure price action strategy, and executes the decision through a risk manager.

```
MT4 Terminal ──TCP:5555──► Python bot ──subprocess──► Claude CLI
                                │
                          TUI (textual)
```

## Requirements

- Python 3.13+
- [Claude Code CLI](https://claude.ai/code) installed and authenticated (`claude` available in PATH)
- MetaTrader 4 terminal (any broker that offers XAUUSD)
- Windows (MT4 Expert Advisor uses Winsock DLLs)

## Installation

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd atenea-aurum
pip install textual rich
```

### 2. Configure Claude Code CLI

The bot invokes `claude` as a subprocess. Make sure it is installed and logged in:

```bash
claude --version   # verify it is available
claude             # log in if not already authenticated
```

### 3. Configure the bot

Edit `src/config.py` to match your setup:

```python
SYMBOL       = "XAUUSD"   # trading symbol
MT4_HOST     = "127.0.0.1"
MT4_PORT     = 5555        # must match AURUM_Bridge.mq4
MAGIC_NUMBER = 20240101    # identifies bot orders in MT4

BALANCE_LOT_STEP = 100     # dollars per 0.01 lot (progressive sizing)
MAX_OPEN_TRADES = 1        # max simultaneous positions
```

### 4. Set up the MT4 Expert Advisor

See the [MT4 setup section](#mt4-setup) below.

### 5. Start the bot

```bash
python aurum.py
```

To preview the TUI without MT4 or the agent:

```bash
python tests/tui_demo.py
```

---

## MT4 Setup

The bot communicates with MT4 via a TCP socket served by a custom Expert Advisor (`AURUM_Bridge.mq4`). Follow these steps:

### Step 1 — Copy the Expert Advisor file

Copy `src/bridge/AURUM_Bridge.mq4` into the MT4 `Experts` folder:

```
C:\Users\<you>\AppData\Roaming\MetaQuotes\Terminal\<instance-id>\MQL4\Experts\
```

You can find the exact path from inside MT4: **File → Open Data Folder → MQL4 → Experts**.

### Step 2 — Allow DLL imports

The EA uses `wsock32.dll` and `ws2_32.dll` (standard Windows Winsock). In MT4:

1. Go to **Tools → Options → Expert Advisors**.
2. Check **"Allow DLL imports"**.
3. Click OK.

### Step 3 — Compile the EA

1. Open **MetaEditor** (press F4 in MT4, or Tools → MetaQuotes Language Editor).
2. In the Navigator panel find `Experts/AURUM_Bridge.mq4`.
3. Press **F7** (or Build → Compile).
4. Verify there are 0 errors in the Errors tab.

### Step 4 — Attach the EA to a chart

1. Open any XAUUSD chart in MT4 (timeframe does not matter — the EA works on any).
2. Drag `AURUM_Bridge` from the Navigator panel onto the chart.
3. In the EA settings dialog:
   - **Common tab:** check **"Allow live trading"** and **"Allow DLL imports"**.
4. Click OK.
5. Confirm the EA is running: a smiley face icon appears in the top-right corner of the chart, and the Experts log shows `[AURUM] Server listening on 127.0.0.1:5555`.

### Step 5 — Enable AutoTrading

Click the **AutoTrading** button in the MT4 toolbar (it must be green/active). If it is disabled, the EA can serve data but cannot execute orders (error 4109).

### Step 6 — Verify connectivity

From a Python shell:

```python
import sys; sys.path.insert(0, "src")
from bridge.mt4_client import MT4Client
mt4 = MT4Client("127.0.0.1", 5555)
mt4.connect()
print(mt4.ping())          # True
print(mt4.get_price("XAUUSD"))
mt4.disconnect()
```

---

## How it works

Each cycle (~15 min, synchronized to M15 candle close):

1. **Data collection** — `data/processor.py` queries MT4 for candles (H4×20, H1×48, M15×32, M5×24), current price, account info, open positions, ATR, and weekly/daily OHLC levels.
2. **Agent decision** — `agent/caller.py` invokes `claude -p <prompt>` and parses the JSON response.
3. **Risk validation** — `risk/executor.py` validates the decision (confidence ≥ 0.60, valid SL, drawdown guard, max trades) and sizes the position using fixed-fractional risk (default 4% of balance).
4. **Execution** — sends BUY/SELL/CLOSE/MODIFY commands to MT4 via the TCP bridge.

The bot sleeps Fri 21:00 UTC → Sun 22:00 UTC (forex market closed).

### Agent decisions

| Decision | Meaning |
|---|---|
| `BUY` | Open a long position |
| `SELL` | Open a short position |
| `HOLD` | Keep current position, no action |
| `CLOSE` | Close a specific ticket (or all positions) |
| `WAIT` | No trade this cycle |

Confidence below 0.60 forces `WAIT` regardless of the decision.

### Customizing the strategy

Edit `src/strategy/system_prompt.md`. The default strategy uses pure price action: market structure (BOS/CHoCH), order blocks, fair value gaps, and liquidity zones. No indicators.

---

## Project structure

```
aurum.py                     # entry point
src/
  config.py                  # global constants
  scheduler.py               # 15-min cycle, weekend sleep, error backoff
  tui.py                     # Textual terminal UI
  logger.py                  # writes to logs/ and TUI simultaneously
  agent/caller.py            # invokes claude CLI, parses JSON response
  bridge/
    mt4_client.py            # TCP client for MT4
    AURUM_Bridge.mq4         # Expert Advisor (TCP server in MT4)
  data/processor.py          # builds market context for the prompt
  risk/executor.py           # validates decision, sizes lots, executes orders
  strategy/system_prompt.md  # agent system prompt — edit to change strategy
tests/                       # manual test scripts (no MT4 or agent required)
logs/                        # runtime logs (git-ignored)
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `MT4ConnectionError` on start | EA not running or wrong port | Attach `AURUM_Bridge` to a chart; verify port 5555 in Experts log |
| `agent_timeout` in logs | `claude` CLI slow or unresponsive | Check `claude` auth; timeout is 180 s |
| `claude_cli_not_found` | `claude` not in PATH | Install Claude Code CLI and ensure it is on PATH |
| Error 4109 — AutoTrading disabled | AutoTrading button is off in MT4 | Click the AutoTrading button (must be green) |
| Error 130 — SL/TP too close | Broker minimum stop distance | Agent will widen SL on next cycle automatically |
| Smiley face is unhappy (red X) | DLL imports not allowed | Tools → Options → Expert Advisors → Allow DLL imports |
