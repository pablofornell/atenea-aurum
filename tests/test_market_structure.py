import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from analysis.market_structure import (
    compute_atr, detect_swing_points, detect_market_structure,
    detect_liquidity_pools, merge_pool_state, detect_sweeps,
    detect_fvgs, detect_order_blocks,
)

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

# ── Swing point tests ─────────────────────────────────────────────────────────

def test_swing_points_bullish():
    highs, lows = detect_swing_points(BULLISH, n=1)
    assert [h["price"] for h in highs] == [115, 125]
    assert [l["price"] for l in lows] == [90, 100]
    # candle_index counts from end: SH at idx3 → index from end = 8-3=5
    assert highs[0]["candle_index"] == 5
    assert highs[1]["candle_index"] == 1

def test_swing_points_bearish():
    highs, lows = detect_swing_points(BEARISH, n=1)
    assert [h["price"] for h in highs] == [115, 110]
    assert [l["price"] for l in lows] == [85, 75]

def test_swing_points_too_few():
    # Fewer than 2*n+1 candles → no swing points possible
    candles = [{"time": f"2024.01.01 0{i}:00", "open": 100, "high": 101, "low": 99, "close": 100} for i in range(2)]
    highs, lows = detect_swing_points(candles, n=1)
    assert highs == []
    assert lows == []

def test_swing_points_all_equal():
    # All same price → no swing points (not strictly greater/less)
    candles = [{"time": f"2024.01.01 0{i}:00", "open": 100, "high": 100, "low": 100, "close": 100} for i in range(5)]
    highs, lows = detect_swing_points(candles, n=1)
    assert highs == []
    assert lows == []


# ── Market structure tests ────────────────────────────────────────────────────

def test_market_structure_bullish():
    s = detect_market_structure(BULLISH, n=1)
    assert s["state"] == "bullish"
    assert s["swing_highs"][-1]["label"] == "HH"
    assert s["swing_lows"][-1]["label"] == "HL"
    assert "HH" in s["swing_sequence"]
    assert "HL" in s["swing_sequence"]

def test_market_structure_bearish():
    s = detect_market_structure(BEARISH, n=1)
    assert s["state"] == "bearish"
    assert s["swing_highs"][-1]["label"] == "LH"
    assert s["swing_lows"][-1]["label"] == "LL"

def test_market_structure_ranging_too_few_swings():
    # Only 5 candles with N=1 → at most 1 swing of each type → can't label → ranging
    candles = [
        {"time": "2024.01.01 00:00", "open": 100, "high": 105, "low": 95, "close": 103},
        {"time": "2024.01.01 01:00", "open": 103, "high": 106, "low": 90, "close": 92},
        {"time": "2024.01.01 02:00", "open":  92, "high": 110, "low": 91, "close": 108},
        {"time": "2024.01.01 03:00", "open": 108, "high": 115, "low": 107, "close": 112},
        {"time": "2024.01.01 04:00", "open": 112, "high": 113, "low": 104, "close": 106},
    ]
    s = detect_market_structure(candles, n=1)
    assert s["state"] == "ranging"

def test_market_structure_no_bos_choch_without_break():
    # BULLISH candles have no candle after the last SH that exceeds it
    s = detect_market_structure(BULLISH, n=1)
    assert s["last_bos"] is None
    assert s["last_choch"] is None

def test_market_structure_choch_bearish():
    s = detect_market_structure(CHOCH, n=1)
    assert s["last_choch"] is not None
    assert s["last_choch"]["direction"] == "bearish"
    assert s["last_choch"]["price"] == 100    # the broken swing low
    assert s["last_bos"] is None

def test_market_structure_bos_bullish():
    s = detect_market_structure(BOS_BULL, n=1)
    assert s["last_bos"] is not None
    assert s["last_bos"]["direction"] == "bullish"
    assert s["last_bos"]["price"] == 125     # the broken swing high
    assert s["last_choch"] is None


# ── Liquidity pool tests ───────────────────────────────────────────────────────

def test_liquidity_pools_from_bullish():
    s = detect_market_structure(BULLISH, n=1)
    pools = detect_liquidity_pools("H1", s["swing_highs"], s["swing_lows"])
    bsl = pools["bsl"]
    ssl = pools["ssl"]
    assert len(bsl) == 2   # SH at 115 and SH at 125
    assert len(ssl) == 2   # SL at 90 and SL at 100
    assert bsl[0]["price"] == 115
    assert bsl[1]["price"] == 125
    assert ssl[0]["price"] == 90
    assert ssl[1]["price"] == 100
    assert all(p["status"] == "intact" for p in bsl + ssl)
    assert all(p["tf"] == "H1" for p in bsl + ssl)

def test_liquidity_pools_equal_highs():
    # Two swing highs within 0.5 tolerance → grouped as equal_highs
    highs = [
        {"price": 115.0, "time": "2024.01.01 01:00", "candle_index": 5, "label": None, "swept": False},
        {"price": 115.3, "time": "2024.01.01 03:00", "candle_index": 3, "label": "HH", "swept": False},
    ]
    lows = []
    pools = detect_liquidity_pools("H1", highs, lows, equal_tolerance=0.5)
    bsl = pools["bsl"]
    assert len(bsl) == 1
    assert bsl[0]["category"] == "equal_highs"
    assert bsl[0]["strength"] == 2

def test_merge_pool_state_preserves_swept():
    prev = [
        {"id": "H1_BSL_20240101_0100", "status": "swept", "swept_at": "2024.01.01 06:00",
         "tf": "H1", "category": "swing_high", "price": 115.0, "strength": 1,
         "origin_time": "2024.01.01 01:00"},
    ]
    new = [
        {"id": "H1_BSL_20240101_0100", "status": "intact", "swept_at": None,
         "tf": "H1", "category": "swing_high", "price": 115.0, "strength": 1,
         "origin_time": "2024.01.01 01:00"},
    ]
    merged = merge_pool_state(new, prev)
    assert merged[0]["status"] == "swept"
    assert merged[0]["swept_at"] == "2024.01.01 06:00"

def test_merge_pool_state_drops_old():
    # Pool ID in prev but not in new → dropped
    prev = [{"id": "H1_BSL_old", "status": "intact", "swept_at": None,
             "tf": "H1", "category": "swing_high", "price": 200.0, "strength": 1,
             "origin_time": "2023.01.01 00:00"}]
    new = [{"id": "H1_BSL_20240101_0100", "status": "intact", "swept_at": None,
            "tf": "H1", "category": "swing_high", "price": 115.0, "strength": 1,
            "origin_time": "2024.01.01 01:00"}]
    merged = merge_pool_state(new, prev)
    assert len(merged) == 1
    assert merged[0]["id"] == "H1_BSL_20240101_0100"


# ── Sweep tests ───────────────────────────────────────────────────────────────

# BULLISH + candle that wicks below SSL@100 and closes above → confirmed sweep
SWEEP_SSL = BULLISH + [
    {"time": "2024.01.01 09:00", "open": 115, "high": 118, "low": 95, "close": 112},
    # low=95 < 100, close=112 > 100
]

def test_sweep_ssl_confirmed():
    s = detect_market_structure(SWEEP_SSL, n=1)
    pools = detect_liquidity_pools("H1", s["swing_highs"], s["swing_lows"])
    sweeps, swept_ids = detect_sweeps("H1", SWEEP_SSL, pools["bsl"], pools["ssl"])
    ssl_sweeps = [sw for sw in sweeps if sw["pool_type"] == "SSL" and sw["pool_price"] == 100]
    assert len(ssl_sweeps) == 1
    sw = ssl_sweeps[0]
    assert sw["confirmed"] is True
    assert sw["wick_extreme"] == 95
    assert sw["close_price"] == 112
    pool_id = next(p["id"] for p in pools["ssl"] if p["price"] == 100)
    assert pool_id in swept_ids

def test_sweep_not_confirmed_when_close_stays_below():
    # Wick goes below SSL@100 but close stays below 100 → not confirmed
    candles = BULLISH + [
        {"time": "2024.01.01 09:00", "open": 115, "high": 118, "low": 95, "close": 98},
        # close=98 < 100
    ]
    s = detect_market_structure(candles, n=1)
    pools = detect_liquidity_pools("H1", s["swing_highs"], s["swing_lows"])
    sweeps, swept_ids = detect_sweeps("H1", candles, pools["bsl"], pools["ssl"])
    ssl_sweeps = [sw for sw in sweeps if sw["pool_type"] == "SSL" and sw["pool_price"] == 100]
    assert len(ssl_sweeps) == 1
    assert ssl_sweeps[0]["confirmed"] is False
    pool_id = next(p["id"] for p in pools["ssl"] if p["price"] == 100)
    assert pool_id not in swept_ids


# ── FVG tests ─────────────────────────────────────────────────────────────────

def test_fvg_bullish_intact():
    fvgs = detect_fvgs("M15", FVG_BULL)
    assert len(fvgs) == 1
    f = fvgs[0]
    assert f["direction"] == "bullish"
    assert f["bottom"] == 105
    assert f["top"] == 112
    assert abs(f["midpoint"] - 108.5) < 0.01
    assert f["status"] == "intact"
    assert f["mitigation_pct"] == 0.0

def test_fvg_bullish_partial():
    # low=108 < top=112 but > bottom=105 → partial
    fvgs = detect_fvgs("M15", FVG_BULL_PARTIAL)
    f = next(f for f in fvgs if f["direction"] == "bullish")
    assert f["status"] == "partial"
    # pct = (112 - 108) / (112 - 105) * 100 = 4/7*100 ≈ 57.1
    assert 55 < f["mitigation_pct"] < 60

def test_fvg_bullish_filled():
    # low=103 < bottom=105 → filled (100%)
    fvgs = detect_fvgs("M15", FVG_BULL_FILLED)
    f = next(f for f in fvgs if f["direction"] == "bullish")
    assert f["status"] == "filled"
    assert f["mitigation_pct"] == 100.0

def test_fvg_bearish():
    candles = [
        {"time": "2024.01.01 00:00", "open": 130, "high": 132, "low": 120, "close": 121},  # [0] low=120
        {"time": "2024.01.01 01:00", "open": 121, "high": 121, "low":  95, "close":  97},  # [1] displacement
        {"time": "2024.01.01 02:00", "open":  97, "high": 110, "low":  94, "close":  96},  # [2] high=110 < 120
    ]
    fvgs = detect_fvgs("M15", candles)
    f = next((f for f in fvgs if f["direction"] == "bearish"), None)
    assert f is not None
    assert f["top"] == 120
    assert f["bottom"] == 110

def test_no_fvg_when_gap_absent():
    # Consecutive candles with no gap
    candles = [
        {"time": "2024.01.01 00:00", "open": 100, "high": 110, "low":  90, "close": 105},
        {"time": "2024.01.01 01:00", "open": 105, "high": 115, "low": 100, "close": 108},
        {"time": "2024.01.01 02:00", "open": 108, "high": 112, "low": 105, "close": 110},  # low=105 ≤ high of [0]=110 → no bullish FVG
    ]
    fvgs = detect_fvgs("M15", candles)
    assert all(f["direction"] != "bullish" for f in fvgs)


# ── Order block tests ─────────────────────────────────────────────────────────

def test_order_block_bullish_ob_after_bearish_choch():
    # CHoCH bearish (structure was bullish): last bullish candle before the break = bearish OB.
    candles = [
        {"time": "2024.01.01 00:00", "open": 100, "high": 105, "low":  95, "close": 103},
        {"time": "2024.01.01 01:00", "open": 103, "high": 110, "low": 102, "close": 108},  # bullish
        {"time": "2024.01.01 02:00", "open": 108, "high": 109, "low":  95, "close":  97},  # bearish ← last bearish before CHoCH bullish
        {"time": "2024.01.01 03:00", "open":  97, "high": 130, "low":  96, "close": 128},  # displacement: CHoCH bullish
        {"time": "2024.01.01 04:00", "open": 128, "high": 129, "low": 124, "close": 126},
    ]
    structure = {
        "state": "bearish",
        "swing_sequence": [],
        "swing_highs": [],
        "swing_lows": [],
        "last_bos": None,
        "last_choch": {
            "price": 108.0,
            "time": "2024.01.01 03:00",
            "direction": "bullish",
            "broken_swing_time": "2024.01.01 01:00",
        },
    }
    obs = detect_order_blocks("H1", candles, structure)
    assert len(obs) == 1
    ob = obs[0]
    assert ob["direction"] == "bullish"
    assert ob["top"] == 108      # open of the last bearish candle (open=108 > close=97)
    assert ob["bottom"] == 97    # close of the last bearish candle
    assert ob["origin_time"] == "2024.01.01 02:00"
    assert ob["displacement_time"] == "2024.01.01 03:00"
    assert ob["status"] == "intact"

def test_order_block_mitigated():
    # Same setup but add a candle that trades back into the OB range
    candles = [
        {"time": "2024.01.01 00:00", "open": 100, "high": 105, "low":  95, "close": 103},
        {"time": "2024.01.01 01:00", "open": 103, "high": 110, "low": 102, "close": 108},
        {"time": "2024.01.01 02:00", "open": 108, "high": 109, "low":  95, "close":  97},  # OB: top=108, bottom=97
        {"time": "2024.01.01 03:00", "open":  97, "high": 130, "low":  96, "close": 128},  # displacement
        {"time": "2024.01.01 04:00", "open": 128, "high": 129, "low": 105, "close": 107},  # low=105 ≤ OB top=108 → mitigated
    ]
    structure = {
        "state": "bearish",
        "swing_sequence": [],
        "swing_highs": [],
        "swing_lows": [],
        "last_bos": None,
        "last_choch": {
            "price": 108.0,
            "time": "2024.01.01 03:00",
            "direction": "bullish",
            "broken_swing_time": "2024.01.01 01:00",
        },
    }
    obs = detect_order_blocks("H1", candles, structure)
    assert obs[0]["status"] == "mitigated"
