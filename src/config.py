SYMBOL         = "XAUUSD"
MT4_HOST       = "127.0.0.1"
MT4_PORT       = 5555
MAGIC_NUMBER   = 20240101

# Risk — NEVER delegated to the agent
MAX_RISK_PCT    = 4   # % of balance per trade
MAX_OPEN_TRADES = 1     # max simultaneous positions

# Cycle
CYCLE_SECONDS  = 60     # seconds between cycles (synced to M15 candle close)
WEEKEND_SLEEP  = True   # sleep Fri 21:00 UTC → Sun 22:00 UTC

# Agent
CLAUDE_CLI     = "claude"
STRATEGY_DIR   = "./src/strategy"
MAX_TOKENS     = 1000

# Data per cycle
CANDLES_H4     = 20
CANDLES_H1     = 48
CANDLES_M15    = 32
CANDLES_M5     = 24
