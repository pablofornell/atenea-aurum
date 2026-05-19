import os

# Mode: "demo" → XAUUSD (testing)  |  "prod" → XAUUSD.mm (real money)
# Set via CLI: python aurum.py --mode prod
_PROFILES = {
    "demo": "XAUUSD",
    "prod": "XAUUSD.mm",
}
MODE = os.environ.get("AURUM_MODE", "demo").lower()
if MODE not in _PROFILES:
    raise ValueError(f"Unknown AURUM_MODE '{MODE}'. Use 'demo' or 'prod'.")

SYMBOL         = _PROFILES[MODE]
MT4_HOST       = "127.0.0.1"
MT4_PORT       = 5555
MAGIC_NUMBER   = 20240101

# Risk — NEVER delegated to the agent
BALANCE_LOT_STEP      = 100  # dollars per 0.01 lot (progressive sizing)
MAX_OPEN_TRADES       = 1    # max simultaneous positions
AUTO_CLOSE_PROFIT_PCT = 7.0  # close automatically when trade profit >= N% of balance (0 = disabled)
FIXED_LOTS            = 0.0  # if > 0, always use this lot size (overrides progressive sizing)

# Cycle
CYCLE_SECONDS  = 60     # seconds between cycles (fallback only)
WEEKEND_SLEEP  = True   # sleep Fri 21:00 UTC → Sun 22:00 UTC

# Adaptive polling intervals (seconds) — code decides base, agent can only accelerate
INTERVAL_NO_POSITION   = 300   # 5 min — killzone active, no open trade
INTERVAL_WITH_POSITION = 300   # 5 min  — position open
INTERVAL_NEAR_TARGET   = 120   # 2 min  — position at ≥80% TP progress or near SL

# Killzones — Eastern Time (ET) [start, end) hour pairs when the bot is allowed to open trades.
# Anchored to ET (America/New_York) so DST transitions are handled automatically.
# Set to [] to disable filtering and trade 24/5.
KILLZONES_ET = [
    (2, 5),    # London open  (02:00–05:00 ET)
    (7, 10),   # NY open      (07:00–10:00 ET)
]
KILLZONE_FRI_CUTOFF = 19  # no new trades on Friday at or after this UTC hour
KILLZONE_MON_START  = 2   # no new trades on Monday before this UTC hour

# Agent
CLAUDE_CLI     = r"C:\Users\hefesto-w10x64\AppData\Local\Microsoft\WinGet\Packages\Anthropic.ClaudeCode_Microsoft.Winget.Source_8wekyb3d8bbwe\claude.exe"
STRATEGY_DIR   = "./src/strategy"
MAX_TOKENS     = 1000

# Persistent state (per-mode so demo and prod don't share structural state)
STATE_DIR      = "./state"
STATE_FILE     = f"./state/structural_state_{MODE}.json"

# Data per cycle — H1 is the highest timeframe (H4 removed)
CANDLES_H1     = 100
CANDLES_M15    = 64
CANDLES_M5     = 48
