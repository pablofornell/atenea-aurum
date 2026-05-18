import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from analysis.market_structure import compute_atr

# ── Shared candle factory ─────────────────────────────────────────────────────

def C(time, o, h, l, c):
    return {"time": time, "open": o, "high": h, "low": l, "close": c}

# ── Fixtures ──────────────────────────────────────────────────────────────────

# 9 candles producing bullish structure (N=1 fractal):
#   swing_lows:  idx1 price=90 (label=None), idx5 price=100 (label=HL)
#   swing_highs: idx3 price=115 (label=None), idx7 price=125 (label=HH)
#   state: bullish
BULLISH = [
    C("2024.01.01 00:00", 100, 105,  95, 104),  # 0
    C("2024.01.01 01:00", 104, 106,  90,  92),  # 1  SL=90
    C("2024.01.01 02:00",  92, 110,  91, 108),  # 2
    C("2024.01.01 03:00", 108, 115, 107, 112),  # 3  SH=115
    C("2024.01.01 04:00", 112, 113, 104, 106),  # 4
    C("2024.01.01 05:00", 106, 108, 100, 103),  # 5  SL=100
    C("2024.01.01 06:00", 103, 120, 102, 118),  # 6
    C("2024.01.01 07:00", 118, 125, 117, 122),  # 7  SH=125
    C("2024.01.01 08:00", 122, 123, 118, 120),  # 8
]

# 9 candles producing bearish structure (N=1 fractal):
#   swing_highs: idx1 price=115 (label=None), idx5 price=110 (label=LH)
#   swing_lows:  idx3 price=85  (label=None), idx7 price=75  (label=LL)
#   state: bearish
BEARISH = [
    C("2024.01.01 00:00", 110, 112, 105, 108),  # 0
    C("2024.01.01 01:00", 108, 115, 107, 110),  # 1  SH=115
    C("2024.01.01 02:00", 110, 111,  89,  91),  # 2
    C("2024.01.01 03:00",  91,  92,  85,  87),  # 3  SL=85
    C("2024.01.01 04:00",  87, 105,  86, 103),  # 4
    C("2024.01.01 05:00", 103, 110, 102, 107),  # 5  SH=110
    C("2024.01.01 06:00", 107, 108,  78,  80),  # 6
    C("2024.01.01 07:00",  80,  81,  75,  77),  # 7  SL=75
    C("2024.01.01 08:00",  77,  82,  76,  80),  # 8
]

# BULLISH + candle that closes below SL=100 → CHoCH bearish
CHOCH = BULLISH + [
    C("2024.01.01 09:00", 120, 121, 115, 117),  # 9
    C("2024.01.01 10:00", 117, 118,  95,  97),  # 10  close=97 < 100 → CHoCH bearish
]

# BULLISH + candle that closes above SH=125 → BOS bullish
BOS_BULL = BULLISH + [
    C("2024.01.01 09:00", 122, 132, 120, 130),  # 9  close=130 > 125 → BOS bullish
]

# 3 candles with a bullish FVG: candles[0].high=105 < candles[2].low=112
FVG_BULL = [
    C("2024.01.01 00:00", 100, 105,  98, 104),
    C("2024.01.01 01:00", 104, 130, 104, 128),  # displacement
    C("2024.01.01 02:00", 128, 135, 112, 130),
]

# FVG_BULL + retracement that partially fills the gap (low=108 < top=112)
FVG_BULL_PARTIAL = FVG_BULL + [
    C("2024.01.01 03:00", 130, 131, 108, 110),
]

# FVG_BULL + retracement that fully fills the gap (low=103 < bottom=105)
FVG_BULL_FILLED = FVG_BULL + [
    C("2024.01.01 03:00", 130, 131, 103, 106),
]

# ── ATR tests ─────────────────────────────────────────────────────────────────

def test_compute_atr_basic():
    # 15 flat candles, each with H=101, L=99, prev_close=100 → TR=2 every bar
    candles = [C(f"2024.01.01 {i:02d}:00", 100, 101, 99, 100) for i in range(16)]
    atr = compute_atr(candles, period=14)
    assert abs(atr - 2.0) < 0.01

def test_compute_atr_too_few_candles():
    candles = [C(f"2024.01.01 {i:02d}:00", 100, 101, 99, 100) for i in range(5)]
    assert compute_atr(candles, period=14) == 0.0
