SYMBOL         = "XAUUSD"
MT4_HOST       = "127.0.0.1"
MT4_PORT       = 5555
MAGIC_NUMBER   = 20240101

# Risk — NEVER delegated to the agent
MAX_RISK_PCT    = 4   # % of balance per trade
MAX_OPEN_TRADES = 1     # max simultaneous positions

# Cycle
CYCLE_SECONDS  = 60     # seconds between cycles (fallback only)
WEEKEND_SLEEP  = True   # sleep Fri 21:00 UTC → Sun 22:00 UTC

# Adaptive polling intervals (seconds) — code decides base, agent can only accelerate
INTERVAL_NO_POSITION   = 600   # 10 min — killzone active, no open trade
INTERVAL_WITH_POSITION = 300   # 5 min  — position open
INTERVAL_NEAR_TARGET   = 120   # 2 min  — position at ≥80% TP progress or near SL

# Killzones — UTC [start, end) hour pairs when the bot is allowed to open trades.
# Set to [] to disable filtering and trade 24/5.
KILLZONES = [
    (7, 10),   # London open
    (12, 15),  # NY open / London-NY overlap
]
KILLZONE_FRI_CUTOFF = 19  # no new trades on Friday at or after this UTC hour
KILLZONE_MON_START  = 2   # no new trades on Monday before this UTC hour

# Agent
CLAUDE_CLI     = "claude"
STRATEGY_DIR   = "./src/strategy"
MAX_TOKENS     = 1000

# Persistent state
STATE_DIR      = "./state"
STATE_FILE     = "./state/structural_state.json"

# Data per cycle
CANDLES_H4     = 20
CANDLES_H1     = 48
CANDLES_M15    = 32
CANDLES_M5     = 24
