# Deterministic Market Structure Layer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the LLM's ad-hoc structural analysis with a deterministic Python engine that computes swing points, BOS/CHoCH, liquidity pools, sweeps, FVGs, and order blocks — leaving the LLM only contextual judgment.

**Architecture:** New `src/analysis/market_structure.py` (Layer 1) computes `structured_market_state` from raw OHLC candles. New `src/risk/validator.py` enforces hard order constraints before execution. `aurum.py` wires Layer 1 between data collection and the agent call. `state/updater.py` persists pool sweep status across cycles. `agent/caller.py` and `system_prompt.md` updated to consume pre-computed state instead of raw candles.

**Tech Stack:** Python 3.13, pytest. No new dependencies.

---

## File Structure

| File | Action | Purpose |
|---|---|---|
| `src/analysis/__init__.py` | Create | Package marker |
| `src/analysis/market_structure.py` | Create | Layer 1: all structural analysis, pure functions |
| `tests/conftest.py` | Create | Add `src/` to sys.path for pytest |
| `tests/test_market_structure.py` | Create | Unit tests with synthetic candle fixtures |
| `src/config.py` | Modify | Remove `CANDLES_H4`, set `CANDLES_H1=100`, `CANDLES_M15=64`, `CANDLES_M5=48` |
| `src/data/processor.py` | Modify | Remove H4 fetch; rewrite `serialize_for_prompt` to use market state JSON |
| `src/state/schema.py` | Modify | Rename h4→h1/h1→m15 bias fields; add `market_state` default |
| `src/state/io.py` | Modify | Schema v3 migration: rename bias keys on load |
| `src/state/updater.py` | Modify | Call `build_market_state`, merge pool persistence |
| `src/risk/validator.py` | Create | Hard validation: R:R, SL beyond sweep, TP at intact pool, bias |
| `aurum.py` | Modify | Wire validator between agent call and `execute()`; structured logging |
| `src/agent/caller.py` | Modify | Update `_OUTPUT_INSTRUCTION` for new bias fields |
| `src/strategy/system_prompt.md` | Modify | Rewrite: LLM receives pre-computed state, no raw candles |
| `schema.json` | Create | JSON Schema (draft-07) for `structured_market_state` and LLM output |

---

## Task 1: Module skeleton, conftest, types, and compute_atr

**Files:**
- Create: `src/analysis/__init__.py`
- Create: `src/analysis/market_structure.py`
- Create: `tests/conftest.py`
- Create: `tests/test_market_structure.py`

- [ ] **Step 1: Create package and conftest**

```bash
touch src/analysis/__init__.py
```

`tests/conftest.py`:
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
```

- [ ] **Step 2: Write the failing test for compute_atr**

`tests/test_market_structure.py`:
```python
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
```

- [ ] **Step 3: Run test to confirm it fails (module not found)**

```bash
python -m pytest tests/test_market_structure.py::test_compute_atr_basic -v
```
Expected: `ModuleNotFoundError: No module named 'analysis'`

- [ ] **Step 4: Create `src/analysis/market_structure.py` with types and compute_atr**

```python
"""
Deterministic market structure analysis for XAUUSD.
All functions are pure: same input → same output, no side effects.
"""
from __future__ import annotations
from typing import TypedDict


# ── Types ─────────────────────────────────────────────────────────────────────

class Candle(TypedDict):
    time: str
    open: float
    high: float
    low: float
    close: float

class SwingPoint(TypedDict):
    price: float
    time: str
    candle_index: int   # distance from end of array, 0 = most recent
    label: str | None   # HH / HL / LH / LL — None for the first swing of each direction
    swept: bool

class StructureBreak(TypedDict):
    price: float
    time: str
    direction: str          # bullish | bearish
    broken_swing_time: str  # timestamp of the swing that was broken

class TimeframeStructure(TypedDict):
    state: str                      # bullish | bearish | ranging
    swing_sequence: list[str]       # last 8 labels, chronological
    swing_highs: list[SwingPoint]
    swing_lows: list[SwingPoint]
    last_bos: StructureBreak | None
    last_choch: StructureBreak | None

class LiquidityPool(TypedDict):
    id: str
    tf: str
    category: str           # swing_high | swing_low | equal_highs | equal_lows
    price: float
    strength: int           # 1 = single swing, 2+ = equal highs/lows grouped
    status: str             # intact | swept
    swept_at: str | None
    origin_time: str

class Sweep(TypedDict):
    tf: str
    pool_id: str
    pool_type: str          # BSL | SSL
    pool_price: float
    sweep_time: str
    wick_extreme: float     # farthest point of the wick that crossed the pool
    close_price: float
    confirmed: bool         # True = wick crossed AND candle closed back on opposite side

class FVG(TypedDict):
    id: str
    direction: str          # bullish | bearish
    top: float
    bottom: float
    midpoint: float
    origin_time: str        # timestamp of the middle (imbalance) candle
    status: str             # intact | partial | filled
    mitigation_pct: float   # 0-100

class OrderBlock(TypedDict):
    id: str
    direction: str          # bullish | bearish
    top: float
    bottom: float
    origin_time: str        # the OB candle itself
    displacement_time: str  # the candle that caused the structural break
    status: str             # intact | mitigated

class DealingRange(TypedDict):
    tf: str
    high: float
    high_time: str
    low: float
    low_time: str
    equilibrium: float
    current_price: float
    current_zone: str       # premium | discount | equilibrium


# ── ATR ───────────────────────────────────────────────────────────────────────

def compute_atr(candles: list[Candle], period: int = 14) -> float:
    """Simple ATR: mean of the last `period` true ranges. Returns 0.0 if too few candles."""
    if len(candles) < period + 1:
        return 0.0
    trs = []
    for i in range(1, len(candles)):
        h, l, pc = candles[i]["high"], candles[i]["low"], candles[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return round(sum(trs[-period:]) / period, 2)
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
python -m pytest tests/test_market_structure.py::test_compute_atr_basic tests/test_market_structure.py::test_compute_atr_too_few_candles -v
```
Expected: `2 passed`

- [ ] **Step 6: Commit**

```bash
git add src/analysis/__init__.py src/analysis/market_structure.py tests/conftest.py tests/test_market_structure.py
git commit -m "feat: scaffold market_structure module with types and compute_atr"
```

---

## Task 2: Swing point detection

**Files:**
- Modify: `src/analysis/market_structure.py`
- Modify: `tests/test_market_structure.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_market_structure.py`:
```python
from analysis.market_structure import detect_swing_points

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
    candles = [C(f"2024.01.01 0{i}:00", 100, 101, 99, 100) for i in range(2)]
    highs, lows = detect_swing_points(candles, n=1)
    assert highs == []
    assert lows == []

def test_swing_points_all_equal():
    # All same price → no swing points (not strictly greater/less)
    candles = [C(f"2024.01.01 0{i}:00", 100, 100, 100, 100) for i in range(5)]
    highs, lows = detect_swing_points(candles, n=1)
    assert highs == []
    assert lows == []
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_market_structure.py -k "swing_points" -v
```
Expected: `ImportError` or `4 failed`

- [ ] **Step 3: Implement `detect_swing_points`**

Add to `src/analysis/market_structure.py`:
```python
def detect_swing_points(
    candles: list[Candle], n: int = 2
) -> tuple[list[SwingPoint], list[SwingPoint]]:
    """
    N-fractal swing detection (default N=2).
    A candle at index i is a swing high if:
        candles[i].high > candles[i±k].high  for all k in [1..n]
    Symmetrically for swing lows using .low.
    Returns (swing_highs, swing_lows) in chronological order (oldest first).
    candle_index is distance from the END of the array (0 = most recent).
    """
    highs: list[SwingPoint] = []
    lows: list[SwingPoint] = []
    length = len(candles)

    for i in range(n, length - n):
        c = candles[i]
        if all(c["high"] > candles[i - k]["high"] for k in range(1, n + 1)) and \
           all(c["high"] > candles[i + k]["high"] for k in range(1, n + 1)):
            highs.append({
                "price": c["high"],
                "time": c["time"],
                "candle_index": length - 1 - i,
                "label": None,
                "swept": False,
            })
        if all(c["low"] < candles[i - k]["low"] for k in range(1, n + 1)) and \
           all(c["low"] < candles[i + k]["low"] for k in range(1, n + 1)):
            lows.append({
                "price": c["low"],
                "time": c["time"],
                "candle_index": length - 1 - i,
                "label": None,
                "swept": False,
            })

    return highs, lows
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_market_structure.py -k "swing_points" -v
```
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add src/analysis/market_structure.py tests/test_market_structure.py
git commit -m "feat: add N-fractal swing point detection"
```

---

## Task 3: Swing labeling and market structure state

**Files:**
- Modify: `src/analysis/market_structure.py`
- Modify: `tests/test_market_structure.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_market_structure.py`:
```python
from analysis.market_structure import detect_market_structure

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
        C("2024.01.01 00:00", 100, 105, 95, 103),
        C("2024.01.01 01:00", 103, 106, 90, 92),   # SL=90
        C("2024.01.01 02:00",  92, 110, 91, 108),
        C("2024.01.01 03:00", 108, 115, 107, 112),  # SH=115
        C("2024.01.01 04:00", 112, 113, 104, 106),
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
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_market_structure.py -k "market_structure" -v
```
Expected: `ImportError` or `6 failed`

- [ ] **Step 3: Implement labeling and structure detection**

Add to `src/analysis/market_structure.py`:
```python
def _label_points(points: list[SwingPoint], is_high: bool) -> list[SwingPoint]:
    """
    Label swing highs as HH/LH, swing lows as HL/LL.
    First point gets label=None. Each subsequent compared to its predecessor by price.
    is_high=True for highs (price > prev → HH, else LH).
    is_high=False for lows  (price > prev → HL, else LL).
    """
    labeled = []
    for i, sp in enumerate(points):
        if i == 0:
            label = None
        elif is_high:
            label = "HH" if sp["price"] > points[i - 1]["price"] else "LH"
        else:
            label = "HL" if sp["price"] > points[i - 1]["price"] else "LL"
        labeled.append({**sp, "label": label})
    return labeled


def _classify_state(highs: list[SwingPoint], lows: list[SwingPoint]) -> str:
    if len(highs) < 2 or len(lows) < 2:
        return "ranging"
    last_h = highs[-1]["label"]
    last_l = lows[-1]["label"]
    if last_h == "HH" and last_l == "HL":
        return "bullish"
    if last_h == "LH" and last_l == "LL":
        return "bearish"
    return "ranging"


def _detect_structure_breaks(
    candles: list[Candle],
    highs: list[SwingPoint],
    lows: list[SwingPoint],
    state: str,
) -> tuple[StructureBreak | None, StructureBreak | None]:
    """
    Scan candles for closes that break the most recent swing high or low.
    Uses closes (not wicks) per SMC convention.
    Break of the last high when bullish → BOS; when bearish/ranging → CHoCH.
    Break of the last low when bearish  → BOS; when bullish/ranging → CHoCH.
    """
    if not highs or not lows:
        return None, None

    last_high = highs[-1]
    last_low = lows[-1]
    last_bos: StructureBreak | None = None
    last_choch: StructureBreak | None = None

    for c in candles:
        if c["time"] > last_high["time"] and c["close"] > last_high["price"]:
            br: StructureBreak = {
                "price": last_high["price"],
                "time": c["time"],
                "direction": "bullish",
                "broken_swing_time": last_high["time"],
            }
            if state in ("bullish", "ranging"):
                last_bos = br
            else:
                last_choch = br

        if c["time"] > last_low["time"] and c["close"] < last_low["price"]:
            br = {
                "price": last_low["price"],
                "time": c["time"],
                "direction": "bearish",
                "broken_swing_time": last_low["time"],
            }
            if state in ("bearish", "ranging"):
                last_bos = br
            else:
                last_choch = br

    return last_bos, last_choch


def detect_market_structure(candles: list[Candle], n: int = 2) -> TimeframeStructure:
    """Compute full market structure for a single timeframe."""
    raw_highs, raw_lows = detect_swing_points(candles, n)
    highs = _label_points(raw_highs, is_high=True)
    lows = _label_points(raw_lows, is_high=False)
    state = _classify_state(highs, lows)
    last_bos, last_choch = _detect_structure_breaks(candles, highs, lows, state)

    all_labeled = [(sp["time"], sp["label"]) for sp in highs + lows if sp["label"]]
    all_labeled.sort(key=lambda x: x[0])
    swing_sequence = [lbl for _, lbl in all_labeled[-8:]]

    return {
        "state": state,
        "swing_sequence": swing_sequence,
        "swing_highs": highs,
        "swing_lows": lows,
        "last_bos": last_bos,
        "last_choch": last_choch,
    }
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_market_structure.py -k "market_structure" -v
```
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add src/analysis/market_structure.py tests/test_market_structure.py
git commit -m "feat: add swing labeling, market structure state, and BOS/CHoCH detection"
```

---

## Task 4: Liquidity pools and pool state merge

**Files:**
- Modify: `src/analysis/market_structure.py`
- Modify: `tests/test_market_structure.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_market_structure.py`:
```python
from analysis.market_structure import detect_liquidity_pools, merge_pool_state

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
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_market_structure.py -k "liquidity or merge" -v
```
Expected: `ImportError` or `4 failed`

- [ ] **Step 3: Implement pool detection and merge**

Add to `src/analysis/market_structure.py`:
```python
def _pool_id(tf: str, pool_type: str, origin_time: str) -> str:
    sanitized = origin_time.replace(".", "").replace(" ", "_").replace(":", "")
    return f"{tf}_{pool_type}_{sanitized}"


def _build_pools(
    tf: str,
    points: list[SwingPoint],
    pool_type: str,
    single_cat: str,
    group_cat: str,
    tolerance: float,
) -> list[LiquidityPool]:
    if not points:
        return []
    groups: list[list[SwingPoint]] = []
    for sp in points:
        placed = False
        for g in groups:
            if abs(sp["price"] - g[0]["price"]) <= tolerance:
                g.append(sp)
                placed = True
                break
        if not placed:
            groups.append([sp])

    pools: list[LiquidityPool] = []
    for g in groups:
        avg = round(sum(s["price"] for s in g) / len(g), 2)
        pools.append({
            "id": _pool_id(tf, pool_type, g[0]["time"]),
            "tf": tf,
            "category": group_cat if len(g) > 1 else single_cat,
            "price": avg,
            "strength": len(g),
            "status": "intact",
            "swept_at": None,
            "origin_time": g[0]["time"],
        })
    return pools


def detect_liquidity_pools(
    tf: str,
    swing_highs: list[SwingPoint],
    swing_lows: list[SwingPoint],
    equal_tolerance: float = 0.5,
) -> dict[str, list[LiquidityPool]]:
    """Build BSL (from swing highs) and SSL (from swing lows) pools."""
    bsl = _build_pools(tf, swing_highs, "BSL", "swing_high", "equal_highs", equal_tolerance)
    ssl = _build_pools(tf, swing_lows,  "SSL", "swing_low",  "equal_lows",  equal_tolerance)
    return {"bsl": bsl, "ssl": ssl}


def merge_pool_state(
    new_pools: list[LiquidityPool],
    prev_pools: list[LiquidityPool],
) -> list[LiquidityPool]:
    """
    Persist swept status from the previous cycle.
    - New pool with same ID as a swept prev pool → stays swept.
    - New pool not in prev → add as intact.
    - Prev pool whose ID is absent from new → dropped (fell outside candle window).
    """
    prev_by_id = {p["id"]: p for p in prev_pools}
    merged = []
    for pool in new_pools:
        prev = prev_by_id.get(pool["id"])
        if prev and prev["status"] == "swept":
            merged.append({**pool, "status": "swept", "swept_at": prev["swept_at"]})
        else:
            merged.append(pool)
    return merged
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_market_structure.py -k "liquidity or merge" -v
```
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add src/analysis/market_structure.py tests/test_market_structure.py
git commit -m "feat: add liquidity pool detection and cross-cycle pool state merge"
```

---

## Task 5: Sweep detection

**Files:**
- Modify: `src/analysis/market_structure.py`
- Modify: `tests/test_market_structure.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_market_structure.py`:
```python
from analysis.market_structure import detect_sweeps

# BULLISH + candle that wicks below SSL@100 and closes above → confirmed sweep
SWEEP_SSL = BULLISH + [
    C("2024.01.01 09:00", 115, 118, 95, 112),  # low=95 < 100, close=112 > 100
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
        C("2024.01.01 09:00", 115, 118, 95, 98),  # close=98 < 100
    ]
    s = detect_market_structure(candles, n=1)
    pools = detect_liquidity_pools("H1", s["swing_highs"], s["swing_lows"])
    sweeps, swept_ids = detect_sweeps("H1", candles, pools["bsl"], pools["ssl"])
    ssl_sweeps = [sw for sw in sweeps if sw["pool_type"] == "SSL" and sw["pool_price"] == 100]
    assert len(ssl_sweeps) == 1
    assert ssl_sweeps[0]["confirmed"] is False
    pool_id = next(p["id"] for p in pools["ssl"] if p["price"] == 100)
    assert pool_id not in swept_ids
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_market_structure.py -k "sweep" -v
```
Expected: `ImportError` or `2 failed`

- [ ] **Step 3: Implement sweep detection**

Add to `src/analysis/market_structure.py`:
```python
def detect_sweeps(
    tf: str,
    candles: list[Candle],
    bsl: list[LiquidityPool],
    ssl: list[LiquidityPool],
) -> tuple[list[Sweep], set[str]]:
    """
    Scan candles for sweeps of BSL and SSL pools.
    BSL sweep: candle.high > pool.price AND candle.close < pool.price.
    SSL sweep: candle.low  < pool.price AND candle.close > pool.price.
    Returns (sweeps, swept_pool_ids). Only the first sweep per pool is recorded.
    """
    sweeps: list[Sweep] = []
    swept_ids: set[str] = set()

    for pool, pool_type, breach_key, return_check in [
        *[(p, "BSL", "high", lambda c, pr: c["close"] < pr) for p in bsl],
        *[(p, "SSL", "low",  lambda c, pr: c["close"] > pr) for p in ssl],
    ]:
        if pool["status"] == "swept":
            swept_ids.add(pool["id"])
            continue
        for c in candles:
            if c["time"] <= pool["origin_time"]:
                continue
            breached = (
                c["high"] > pool["price"] if pool_type == "BSL"
                else c["low"] < pool["price"]
            )
            if breached:
                confirmed = return_check(c, pool["price"])
                sweeps.append({
                    "tf": tf,
                    "pool_id": pool["id"],
                    "pool_type": pool_type,
                    "pool_price": pool["price"],
                    "sweep_time": c["time"],
                    "wick_extreme": c["high"] if pool_type == "BSL" else c["low"],
                    "close_price": c["close"],
                    "confirmed": confirmed,
                })
                if confirmed:
                    swept_ids.add(pool["id"])
                break  # one sweep per pool

    return sweeps, swept_ids
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_market_structure.py -k "sweep" -v
```
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add src/analysis/market_structure.py tests/test_market_structure.py
git commit -m "feat: add sweep detection with confirmed/unconfirmed status"
```

---

## Task 6: FVG detection

**Files:**
- Modify: `src/analysis/market_structure.py`
- Modify: `tests/test_market_structure.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_market_structure.py`:
```python
from analysis.market_structure import detect_fvgs

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
        C("2024.01.01 00:00", 130, 132, 120, 121),  # [0] low=120
        C("2024.01.01 01:00", 121, 121, 95,  97),   # [1] displacement
        C("2024.01.01 02:00", 97,  110, 94,  96),   # [2] high=110 < 120
    ]
    fvgs = detect_fvgs("M15", candles)
    f = next((f for f in fvgs if f["direction"] == "bearish"), None)
    assert f is not None
    assert f["top"] == 120
    assert f["bottom"] == 110

def test_no_fvg_when_gap_absent():
    # Consecutive candles with no gap
    candles = [
        C("2024.01.01 00:00", 100, 110,  90, 105),
        C("2024.01.01 01:00", 105, 115, 100, 108),
        C("2024.01.01 02:00", 108, 112, 105, 110),  # low=105 ≤ high of [0]=110 → no bullish FVG
    ]
    fvgs = detect_fvgs("M15", candles)
    assert all(f["direction"] != "bullish" for f in fvgs)
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_market_structure.py -k "fvg" -v
```
Expected: `ImportError` or `5 failed`

- [ ] **Step 3: Implement FVG detection**

Add to `src/analysis/market_structure.py`:
```python
def detect_fvgs(tf: str, candles: list[Candle]) -> list[FVG]:
    """
    Three-candle FVG pattern:
      Bullish: candles[i-2].high < candles[i].low  → gap above candle[i-2]
      Bearish: candles[i-2].low  > candles[i].high → gap below candle[i-2]
    origin_time = timestamp of the middle (imbalance) candle.
    mitigation_pct tracks how far price has retraced into the gap after formation.
    """
    fvgs: list[FVG] = []
    n = len(candles)

    for i in range(2, n):
        c0, c1, c2 = candles[i - 2], candles[i - 1], candles[i]
        fvg: FVG | None = None

        if c0["high"] < c2["low"]:
            fvg = {
                "id": f"{tf}_FVG_bull_{i}",
                "direction": "bullish",
                "top": c2["low"],
                "bottom": c0["high"],
                "midpoint": round((c2["low"] + c0["high"]) / 2, 2),
                "origin_time": c1["time"],
                "status": "intact",
                "mitigation_pct": 0.0,
            }
        elif c0["low"] > c2["high"]:
            fvg = {
                "id": f"{tf}_FVG_bear_{i}",
                "direction": "bearish",
                "top": c0["low"],
                "bottom": c2["high"],
                "midpoint": round((c0["low"] + c2["high"]) / 2, 2),
                "origin_time": c1["time"],
                "status": "intact",
                "mitigation_pct": 0.0,
            }

        if fvg is None:
            continue

        gap = fvg["top"] - fvg["bottom"]
        if gap <= 0:
            continue

        subsequent = candles[i + 1:]
        if fvg["direction"] == "bullish":
            candidates = [c["low"] for c in subsequent if c["low"] < fvg["top"]]
            min_low = min(candidates) if candidates else fvg["top"]
            pct = round(min(100.0, max(0.0, (fvg["top"] - min_low) / gap * 100)), 1)
        else:
            candidates = [c["high"] for c in subsequent if c["high"] > fvg["bottom"]]
            max_high = max(candidates) if candidates else fvg["bottom"]
            pct = round(min(100.0, max(0.0, (max_high - fvg["bottom"]) / gap * 100)), 1)

        fvg["mitigation_pct"] = pct
        if pct >= 100:
            fvg["status"] = "filled"
        elif pct > 0:
            fvg["status"] = "partial"

        fvgs.append(fvg)

    return fvgs
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_market_structure.py -k "fvg" -v
```
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add src/analysis/market_structure.py tests/test_market_structure.py
git commit -m "feat: add FVG detection with mitigation tracking"
```

---

## Task 7: Order block detection

**Files:**
- Modify: `src/analysis/market_structure.py`
- Modify: `tests/test_market_structure.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_market_structure.py`:
```python
from analysis.market_structure import detect_order_blocks

def test_order_block_bullish_ob_after_bearish_choch():
    # CHoCH bearish (structure was bullish): last bullish candle before the break = bearish OB.
    # We supply structure directly to isolate OB detection from swing logic.
    candles = [
        C("2024.01.01 00:00", 100, 105,  95, 103),
        C("2024.01.01 01:00", 103, 110, 102, 108),  # bullish
        C("2024.01.01 02:00", 108, 109,  95,  97),  # bearish ← last bearish before CHoCH bullish
        C("2024.01.01 03:00",  97, 130,  96, 128),  # displacement: CHoCH bullish
        C("2024.01.01 04:00", 128, 129, 124, 126),
    ]
    structure: TimeframeStructure = {
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
    assert ob["top"] == 108      # max(open=108, close=97)
    assert ob["bottom"] == 97    # min(open=108, close=97)
    assert ob["origin_time"] == "2024.01.01 02:00"
    assert ob["displacement_time"] == "2024.01.01 03:00"
    assert ob["status"] == "intact"

def test_order_block_mitigated():
    # Same setup but add a candle that trades back into the OB range
    candles = [
        C("2024.01.01 00:00", 100, 105,  95, 103),
        C("2024.01.01 01:00", 103, 110, 102, 108),
        C("2024.01.01 02:00", 108, 109,  95,  97),  # OB: top=108, bottom=97
        C("2024.01.01 03:00",  97, 130,  96, 128),  # displacement
        C("2024.01.01 04:00", 128, 129, 105, 107),  # low=105 ≤ OB top=108 → mitigated
    ]
    structure: TimeframeStructure = {
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
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_market_structure.py -k "order_block" -v
```
Expected: `ImportError` or `2 failed`

- [ ] **Step 3: Implement order block detection**

Add to `src/analysis/market_structure.py`:
```python
def _ob_status(
    candles: list[Candle],
    ob_top: float,
    ob_bottom: float,
    displacement_time: str,
    direction: str,
) -> str:
    """Mitigated when price trades back into the OB body after the displacement."""
    for c in candles:
        if c["time"] <= displacement_time:
            continue
        if direction == "bullish" and c["low"] <= ob_top:
            return "mitigated"
        if direction == "bearish" and c["high"] >= ob_bottom:
            return "mitigated"
    return "intact"


def detect_order_blocks(
    tf: str,
    candles: list[Candle],
    structure: TimeframeStructure,
) -> list[OrderBlock]:
    """
    Find order blocks: last candle of opposite color before a displacement
    that created a BOS or CHoCH.
    Bullish OB: last bearish candle (close < open) before a bullish break.
    Bearish OB: last bullish candle (close > open) before a bearish break.
    """
    obs: list[OrderBlock] = []
    breaks: list[StructureBreak] = [
        b for b in [structure["last_bos"], structure["last_choch"]] if b is not None
    ]

    for br in breaks:
        pre_break = [c for c in candles if c["time"] < br["time"]]
        if not pre_break:
            continue

        if br["direction"] == "bullish":
            ob_candle = next((c for c in reversed(pre_break) if c["close"] < c["open"]), None)
            if ob_candle is None:
                continue
            top = ob_candle["open"]
            bottom = ob_candle["close"]
            direction = "bullish"
        else:
            ob_candle = next((c for c in reversed(pre_break) if c["close"] > c["open"]), None)
            if ob_candle is None:
                continue
            top = ob_candle["close"]
            bottom = ob_candle["open"]
            direction = "bearish"

        obs.append({
            "id": _pool_id(tf, f"OB_{direction}", ob_candle["time"]),
            "direction": direction,
            "top": top,
            "bottom": bottom,
            "origin_time": ob_candle["time"],
            "displacement_time": br["time"],
            "status": _ob_status(candles, top, bottom, br["time"], direction),
        })

    return obs
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_market_structure.py -k "order_block" -v
```
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add src/analysis/market_structure.py tests/test_market_structure.py
git commit -m "feat: add order block detection with mitigation status"
```

---

## Task 8: Dealing range and Asia session range

**Files:**
- Modify: `src/analysis/market_structure.py`
- Modify: `tests/test_market_structure.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_market_structure.py`:
```python
from analysis.market_structure import detect_dealing_range, compute_asia_range

def test_dealing_range_discount():
    s = detect_market_structure(BULLISH, n=1)
    # Range: SL=90 to SH=125, eq=(90+125)/2=107.5
    # current_price=95 < 107.5 - 5%*(125-90) = 107.5 - 1.75 = 105.75 → discount
    dr = detect_dealing_range("H1", BULLISH, s["swing_highs"], s["swing_lows"],
                               current_price=95, equil_band_pct=0.05)
    assert dr["high"] == 125
    assert dr["low"] == 90
    assert abs(dr["equilibrium"] - 107.5) < 0.01
    assert dr["current_zone"] == "discount"

def test_dealing_range_premium():
    s = detect_market_structure(BULLISH, n=1)
    # price=120 > 107.5 + 1.75 = 109.25 → premium
    dr = detect_dealing_range("H1", BULLISH, s["swing_highs"], s["swing_lows"],
                               current_price=120, equil_band_pct=0.05)
    assert dr["current_zone"] == "premium"

def test_dealing_range_equilibrium():
    s = detect_market_structure(BULLISH, n=1)
    # price=107 ≈ equilibrium (107.5 ± 1.75)
    dr = detect_dealing_range("H1", BULLISH, s["swing_highs"], s["swing_lows"],
                               current_price=107, equil_band_pct=0.05)
    assert dr["current_zone"] == "equilibrium"

def test_compute_asia_range():
    candles = [
        C("2024.01.15 00:00", 100, 105, 98, 103),   # today Asia
        C("2024.01.15 03:00", 103, 108, 102, 106),  # today Asia
        C("2024.01.15 06:00", 106, 110, 104, 108),  # today Asia
        C("2024.01.15 08:00", 108, 115, 107, 112),  # today London (hour>=7)
        C("2024.01.15 12:00", 112, 118, 110, 115),  # today NY
    ]
    asia = compute_asia_range(candles)
    assert asia["asia_high"] == 110
    assert asia["asia_low"] == 98

def test_compute_asia_range_no_candles():
    # Candles all in London/NY → no Asia range
    candles = [C("2024.01.15 08:00", 100, 105, 98, 103)]
    asia = compute_asia_range(candles)
    assert asia["asia_high"] is None
    assert asia["asia_low"] is None
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_market_structure.py -k "dealing_range or asia" -v
```
Expected: `ImportError` or `5 failed`

- [ ] **Step 3: Implement dealing range and Asia range**

Add to `src/analysis/market_structure.py`:
```python
def detect_dealing_range(
    tf: str,
    candles: list[Candle],
    swing_highs: list[SwingPoint],
    swing_lows: list[SwingPoint],
    current_price: float,
    equil_band_pct: float = 0.05,
) -> DealingRange:
    """
    Dealing range = span between the highest swing high and lowest swing low
    in the current candle window. equil_band_pct: fraction of range size on
    each side of equilibrium that classifies as the 'equilibrium' zone.
    """
    if swing_highs and swing_lows:
        top = max(swing_highs, key=lambda s: s["price"])
        bot = min(swing_lows,  key=lambda s: s["price"])
        h, h_time = top["price"], top["time"]
        l, l_time = bot["price"], bot["time"]
    else:
        h = max(c["high"] for c in candles)
        l = min(c["low"]  for c in candles)
        h_time = next(c["time"] for c in candles if c["high"] == h)
        l_time = next(c["time"] for c in candles if c["low"]  == l)

    eq = round((h + l) / 2, 2)
    band = (h - l) * equil_band_pct

    if current_price > eq + band:
        zone = "premium"
    elif current_price < eq - band:
        zone = "discount"
    else:
        zone = "equilibrium"

    return {
        "tf": tf,
        "high": h, "high_time": h_time,
        "low": l,  "low_time": l_time,
        "equilibrium": eq,
        "current_price": current_price,
        "current_zone": zone,
    }


def compute_asia_range(candles_h1: list[Candle]) -> dict[str, float | None]:
    """Extract Asian session range (00:00-06:00 UTC) from today's H1 candles."""
    if not candles_h1:
        return {"asia_high": None, "asia_low": None}
    today = candles_h1[-1]["time"].split(" ")[0]
    asia = [
        c for c in candles_h1
        if c["time"].startswith(today)
        and int(c["time"].split(" ")[1].split(":")[0]) < 7
    ]
    if not asia:
        return {"asia_high": None, "asia_low": None}
    return {
        "asia_high": max(c["high"] for c in asia),
        "asia_low":  min(c["low"]  for c in asia),
    }
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_market_structure.py -k "dealing_range or asia" -v
```
Expected: `5 passed`

- [ ] **Step 5: Run full test suite to check for regressions**

```bash
python -m pytest tests/test_market_structure.py -v
```
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add src/analysis/market_structure.py tests/test_market_structure.py
git commit -m "feat: add dealing range, equilibrium zone, and Asia session range"
```

---

## Task 9: build_market_state integration function

**Files:**
- Modify: `src/analysis/market_structure.py`
- Modify: `tests/test_market_structure.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_market_structure.py`:
```python
from analysis.market_structure import build_market_state

def test_build_market_state_structure():
    candles = {"H1": BULLISH, "M15": BULLISH[:7], "M5": BULLISH[:5]}
    price = {"bid": 105.0, "ask": 105.5, "spread": 0.5}
    day_ohlc = {"prev_high": 130.0, "prev_low": 85.0, "today_open": 90.0,
                "prev_open": 88.0, "prev_close": 128.0}
    week_hl = {"prev_high": 140.0, "prev_low": 80.0,
               "curr_high": 130.0, "curr_low": 88.0}

    state = build_market_state(
        candles=candles, price=price, session="London",
        symbol="XAUUSD", timestamp="2024.01.01 08:00",
        day_ohlc=day_ohlc, week_hl=week_hl,
    )

    assert state["meta"]["symbol"] == "XAUUSD"
    assert state["meta"]["session"] == "London"
    assert "H1" in state["structure"]
    assert "M15" in state["structure"]
    assert state["structure"]["H1"]["state"] == "bullish"
    assert "H1" in state["atr"]
    assert isinstance(state["liquidity"]["bsl"], list)
    assert isinstance(state["liquidity"]["ssl"], list)
    assert "prev_day_high" in state["liquidity"]["session_levels"]
    assert isinstance(state["sweeps"], list)
    assert "H1" in state["fvg"]
    assert "H1" in state["order_blocks"]
    assert state["dealing_range"]["tf"] == "H1"
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_market_structure.py::test_build_market_state_structure -v
```
Expected: `ImportError` or `FAILED`

- [ ] **Step 3: Implement build_market_state**

Add to `src/analysis/market_structure.py`:
```python
def build_market_state(
    candles: dict[str, list[Candle]],
    price: dict,
    session: str,
    symbol: str,
    timestamp: str,
    day_ohlc: dict,
    week_hl: dict,
    prev_market_state: dict | None = None,
    swing_n: int = 2,
    equal_tolerance: float = 0.5,
    equil_band_pct: float = 0.05,
) -> dict:
    """
    Build the complete structured_market_state from raw OHLC candles.
    candles: {"H1": [...], "M15": [...], "M5": [...]}
    prev_market_state: previous cycle's output for pool sweep persistence.
    """
    tfs = ["H1", "M15", "M5"]
    structure: dict[str, TimeframeStructure] = {}
    all_bsl: list[LiquidityPool] = []
    all_ssl: list[LiquidityPool] = []
    all_sweeps: list[Sweep] = []
    fvgs: dict[str, list[FVG]] = {}
    obs: dict[str, list[OrderBlock]] = {}
    atr: dict[str, float] = {}

    prev_liq = (prev_market_state or {}).get("liquidity", {})

    for tf in tfs:
        tf_candles = candles.get(tf, [])
        if not tf_candles:
            continue

        struct = detect_market_structure(tf_candles, swing_n)
        structure[tf] = struct
        atr[tf] = compute_atr(tf_candles)

        # Fresh pool detection, then merge with previous cycle's sweep state
        fresh = detect_liquidity_pools(tf, struct["swing_highs"], struct["swing_lows"], equal_tolerance)
        prev_bsl = [p for p in prev_liq.get("bsl", []) if p["tf"] == tf]
        prev_ssl = [p for p in prev_liq.get("ssl", []) if p["tf"] == tf]
        merged_bsl = merge_pool_state(fresh["bsl"], prev_bsl)
        merged_ssl = merge_pool_state(fresh["ssl"], prev_ssl)

        # Detect sweeps, then mark newly-swept pools
        sweeps, swept_ids = detect_sweeps(tf, tf_candles, merged_bsl, merged_ssl)
        for pool in merged_bsl + merged_ssl:
            if pool["id"] in swept_ids and pool["status"] != "swept":
                sw = next((s for s in sweeps if s["pool_id"] == pool["id"] and s["confirmed"]), None)
                if sw:
                    pool["status"] = "swept"
                    pool["swept_at"] = sw["sweep_time"]

        all_bsl.extend(merged_bsl)
        all_ssl.extend(merged_ssl)
        all_sweeps.extend(sweeps)
        fvgs[tf] = detect_fvgs(tf, tf_candles)
        obs[tf] = detect_order_blocks(tf, tf_candles, struct)

    # Session levels from bridge data + Asia from H1 candles
    h1_candles = candles.get("H1", [])
    asia = compute_asia_range(h1_candles)

    def _sl(price_val: float | None) -> dict:
        return {"price": price_val, "status": "intact", "swept_at": None}

    session_levels = {
        "prev_day_high":  _sl(day_ohlc.get("prev_high")),
        "prev_day_low":   _sl(day_ohlc.get("prev_low")),
        "prev_week_high": _sl(week_hl.get("prev_high")),
        "prev_week_low":  _sl(week_hl.get("prev_low")),
        "asia_high":      _sl(asia.get("asia_high")),
        "asia_low":       _sl(asia.get("asia_low")),
        "today_open":     day_ohlc.get("today_open"),
    }

    h1_struct = structure.get("H1")
    dealing_range = None
    if h1_struct:
        dealing_range = detect_dealing_range(
            "H1", h1_candles,
            h1_struct["swing_highs"], h1_struct["swing_lows"],
            price["bid"], equil_band_pct,
        )

    return {
        "meta": {"timestamp": timestamp, "symbol": symbol, "session": session, "price": price},
        "atr": atr,
        "structure": structure,
        "liquidity": {"bsl": all_bsl, "ssl": all_ssl, "session_levels": session_levels},
        "sweeps": all_sweeps,
        "fvg": fvgs,
        "order_blocks": obs,
        "dealing_range": dealing_range,
    }
```

- [ ] **Step 4: Run full test suite**

```bash
python -m pytest tests/test_market_structure.py -v
```
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add src/analysis/market_structure.py tests/test_market_structure.py
git commit -m "feat: add build_market_state integration function"
```

---

## Task 10: Update config.py and data/processor.py

**Files:**
- Modify: `src/config.py`
- Modify: `src/data/processor.py`

- [ ] **Step 1: Update config.py**

In `src/config.py`, replace the `# Data per cycle` block:
```python
# Data per cycle — H1 is the highest timeframe (H4 removed)
CANDLES_H1     = 100
CANDLES_M15    = 64
CANDLES_M5     = 48
```
Delete the `CANDLES_H4 = 20` line entirely.

- [ ] **Step 2: Update processor.py — remove H4 fetch**

In `src/data/processor.py`, replace the `candles` block in `build_context`:
```python
    candles = {
        "H1":  mt4.get_candles(config.SYMBOL, 60,  config.CANDLES_H1),
        "M15": mt4.get_candles(config.SYMBOL, 15,  config.CANDLES_M15),
        "M5":  mt4.get_candles(config.SYMBOL, 5,   config.CANDLES_M5),
    }
```

Remove `atr_h1 = mt4.get_atr(...)` — ATR is now computed in market_structure.py.

Update the return dict — remove `"atr_h1"` and keep everything else:
```python
    return {
        "timestamp": now.strftime("%Y-%m-%d %H:%M UTC"),
        "session":   session,
        "symbol":    config.SYMBOL,
        "price":     price,
        "day_ohlc":  day_ohlc,
        "week_hl":   week_hl,
        "candles":   candles,
        "positions": positions,
        "account":   account,
    }
```

- [ ] **Step 3: Rewrite serialize_for_prompt**

Replace the entire `serialize_for_prompt` and `_serialize_state` functions in `src/data/processor.py`:
```python
def serialize_for_prompt(
    ctx: dict,
    market_state: dict | None = None,
    last_result: str | None = None,
    bot_managed: dict | None = None,
) -> str:
    """Build the text prompt for the LLM agent."""
    import json
    p   = ctx["price"]
    acc = ctx["account"]
    pos = ctx["positions"]

    lines = [
        f"=== AURUM MARKET CONTEXT — {ctx['timestamp']} ({ctx['session']} session) ===",
        "",
        f"PRICE: Bid {p['bid']:.2f} | Ask {p['ask']:.2f} | Spread {p['spread']:.2f}",
        f"ACCOUNT: Balance {acc['balance']:.2f} {acc['currency']}"
        f" | Equity {acc['equity']:.2f} | Free margin {acc['free_margin']:.2f}",
        "",
    ]

    if pos:
        lines.append("OPEN POSITIONS:")
        for p_ in pos:
            lines.append(
                f"  ticket={p_['ticket']} {p_['type']} {p_['lots']} lots"
                f" open={p_['open']:.2f} sl={p_['sl']:.2f} tp={p_['tp']:.2f}"
                f" profit={p_['profit']:.2f}"
            )
    else:
        lines.append("OPEN POSITIONS: none")

    if last_result:
        lines.append("")
        lines.append(f"LAST CYCLE RESULT: {last_result}")

    if market_state:
        lines.append("")
        lines.append("STRUCTURAL_MARKET_STATE:")
        lines.append(json.dumps(market_state, indent=2))

    if bot_managed:
        lines.append("")
        lines.append("BOT_MEMORY:")
        lines.append(json.dumps(bot_managed, indent=2))

    return "\n".join(lines)
```

- [ ] **Step 4: Verify no import errors**

```bash
cd /path/to/repo && python -c "import sys; sys.path.insert(0, 'src'); import config; import data.processor; print('OK')"
```
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add src/config.py src/data/processor.py
git commit -m "feat: remove H4, update candle counts, rewrite serialize_for_prompt"
```

---

## Task 11: Update state/schema.py and state/io.py

**Files:**
- Modify: `src/state/schema.py`
- Modify: `src/state/io.py`

- [ ] **Step 1: Update schema.py — rename bias fields and bump version**

In `src/state/schema.py`, change `SCHEMA_VERSION = 2` to `SCHEMA_VERSION = 3`.

Replace `default_bot_managed`:
```python
def default_bot_managed() -> dict:
    return {
        "h1_bias": "unclear",
        "h1_bias_since": None,
        "h1_bias_justification": "",
        "m15_bias": "unclear",
        "m15_bias_justification": "",
        "pending_setup": default_pending_setup(),
        "narrative": "",
    }
```

Update `validate_bot_managed`:
```python
_VALID_BIASES = {"bullish", "bearish", "ranging", "unclear"}

def validate_bot_managed(bm: dict) -> tuple[bool, str]:
    if not isinstance(bm, dict):
        return False, "bot_managed must be a dict"
    required = [
        "h1_bias", "h1_bias_since", "h1_bias_justification",
        "m15_bias", "m15_bias_justification", "pending_setup", "narrative",
    ]
    for key in required:
        if key not in bm:
            return False, f"missing key: {key}"
    if bm.get("h1_bias") not in _VALID_BIASES:
        return False, f"invalid h1_bias: {bm.get('h1_bias')!r}"
    if bm.get("m15_bias") not in _VALID_BIASES:
        return False, f"invalid m15_bias: {bm.get('m15_bias')!r}"
    ps = bm.get("pending_setup")
    if not isinstance(ps, dict):
        return False, "pending_setup must be a dict"
    if "active" not in ps or not isinstance(ps.get("active"), bool):
        return False, "pending_setup.active must be bool"
    return True, ""
```

Remove the old `atr` dict from `default_state` `code_managed` block (ATR now lives in `market_state`). Add `market_state: None` placeholder:
```python
def default_state() -> dict:
    return {
        "last_updated": None,
        "schema_version": SCHEMA_VERSION,
        "code_managed": {
            "market_state": None,
            "open_position_metrics": {
                "ticket": None, "type": None, "entry_price": 0.0,
                "pnl_price": 0.0, "max_drawdown_price": 0.0,
                "max_profit_price": 0.0, "tp_completion_pct": 0.0,
                "opened_at": None, "minutes_open": 0,
            },
            "recent_decisions": [],
            "economic_events_today": [],
        },
        "bot_managed": default_bot_managed(),
    }
```

- [ ] **Step 2: Update io.py — add v3 migration**

In `src/state/io.py`, inside `load_state`, replace the migration block:
```python
    if data.get("schema_version") != SCHEMA_VERSION:
        new_state = default_state()
        old_bm = data.get("bot_managed", {})
        if isinstance(old_bm, dict):
            # v2→v3: rename h4_bias→h1_bias, h1_bias→m15_bias
            if "h4_bias" in old_bm:
                old_bm["h1_bias"] = old_bm.pop("h4_bias")
                old_bm["h1_bias_since"] = old_bm.pop("h4_bias_since", None)
                old_bm["h1_bias_justification"] = old_bm.pop("h4_bias_justification", "")
            if "h1_bias" in old_bm and "m15_bias" not in old_bm:
                old_bm["m15_bias"] = old_bm.pop("h1_bias", "unclear")
                old_bm["m15_bias_justification"] = old_bm.pop("h1_bias_justification", "")
            from state.schema import validate_bot_managed
            ok, _ = validate_bot_managed(old_bm)
            if ok:
                new_state["bot_managed"] = old_bm
        old_decisions = data.get("code_managed", {}).get("recent_decisions", [])
        if old_decisions:
            new_state["code_managed"]["recent_decisions"] = old_decisions[-5:]
        return new_state
```

- [ ] **Step 3: Verify import**

```bash
python -c "import sys; sys.path.insert(0, 'src'); from state.schema import default_state, validate_bot_managed; s = default_state(); print(s['bot_managed'].keys())"
```
Expected: `dict_keys(['h1_bias', 'h1_bias_since', 'h1_bias_justification', 'm15_bias', 'm15_bias_justification', 'pending_setup', 'narrative'])`

- [ ] **Step 4: Commit**

```bash
git add src/state/schema.py src/state/io.py
git commit -m "feat: schema v3 — rename h4/h1 bias to h1/m15, add market_state field"
```

---

## Task 12: Update state/updater.py

**Files:**
- Modify: `src/state/updater.py`

- [ ] **Step 1: Replace updater content**

Replace `src/state/updater.py` entirely with:

```python
"""
Code-managed state updater. Runs before the agent each cycle.
All functions modify state in-place.
"""
from datetime import datetime, timezone
from pathlib import Path
import json

from analysis.market_structure import build_market_state


def _now_str() -> str:
    return datetime.now(timezone.utc).isoformat()


def _minutes_since(t_str: str) -> float:
    for fmt in ("%Y.%m.%d %H:%M", "%Y-%m-%d %H:%M", "%Y.%m.%d %H:%M:%S"):
        try:
            dt = datetime.strptime(t_str, fmt).replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - dt).total_seconds() / 60
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(t_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 60
    except ValueError:
        return 9999.0


def _update_market_state(state: dict, context: dict) -> None:
    """Run Layer 1: build structured_market_state and store in code_managed."""
    prev = state["code_managed"].get("market_state")
    ms = build_market_state(
        candles=context["candles"],
        price=context["price"],
        session=context["session"],
        symbol=context["symbol"],
        timestamp=context["timestamp"],
        day_ohlc=context["day_ohlc"],
        week_hl=context["week_hl"],
        prev_market_state=prev,
    )
    state["code_managed"]["market_state"] = ms


def _update_position_metrics(state: dict, context: dict) -> None:
    cm = state["code_managed"]
    positions = context["positions"]
    bid = context["price"]["bid"]
    ask = context["price"]["ask"]

    if not positions:
        cm["open_position_metrics"] = {
            "ticket": None, "type": None, "entry_price": 0.0,
            "pnl_price": 0.0, "max_drawdown_price": 0.0,
            "max_profit_price": 0.0, "tp_completion_pct": 0.0,
            "opened_at": None, "minutes_open": 0,
        }
        return

    pos = positions[0]
    ticket = pos["ticket"]
    pos_type = str(pos["type"]).upper()
    entry = pos["open"]
    tp = pos["tp"]
    is_buy = pos_type in ("BUY", "0")

    if is_buy:
        pnl = round(bid - entry, 2)
        tp_dist = (tp - entry) if tp > entry else 0
        pnl_for_tp = bid - entry
    else:
        pnl = round(entry - ask, 2)
        tp_dist = (entry - tp) if tp < entry else 0
        pnl_for_tp = entry - ask

    tp_pct = round(max(0.0, min(1.0, pnl_for_tp / tp_dist)), 2) if tp_dist > 0 else 0.0
    prev = cm.get("open_position_metrics", {})
    now = _now_str()

    if prev.get("ticket") == ticket:
        opened_at = prev.get("opened_at") or now
        max_dd = min(prev.get("max_drawdown_price", 0.0), pnl)
        max_pr = max(prev.get("max_profit_price", 0.0), pnl)
    else:
        opened_at = now
        max_dd = min(0.0, pnl)
        max_pr = max(0.0, pnl)

    cm["open_position_metrics"] = {
        "ticket": ticket, "type": pos_type, "entry_price": entry,
        "pnl_price": pnl, "max_drawdown_price": max_dd,
        "max_profit_price": max_pr, "tp_completion_pct": tp_pct,
        "opened_at": opened_at,
        "minutes_open": round(_minutes_since(opened_at)) if opened_at else 0,
    }


def _append_decision(state: dict, decision: dict | None) -> None:
    if not decision:
        return
    cm = state["code_managed"]
    cm["recent_decisions"].append({
        "cycle_time": _now_str(),
        "decision": decision.get("decision", "WAIT"),
        "reason_summary": decision.get("reasoning", "")[:80],
        "confidence": round(float(decision.get("confidence", 0.0)), 2),
    })
    cm["recent_decisions"] = cm["recent_decisions"][-5:]


def update_code_managed_state(
    state: dict,
    context: dict,
    previous_decision: dict | None,
    cfg,
) -> dict:
    """
    Update all code-managed fields. Modifies state in-place.
    Returns dict of changes for structured logging.
    """
    state["last_updated"] = _now_str()
    _update_market_state(state, context)
    _update_position_metrics(state, context)
    _append_decision(state, previous_decision)
    return {}
```

- [ ] **Step 2: Verify import**

```bash
python -c "import sys; sys.path.insert(0, 'src'); from state.updater import update_code_managed_state; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/state/updater.py
git commit -m "feat: updater calls build_market_state each cycle, persists pool state"
```

---

## Task 13: Hard validation — src/risk/validator.py

**Files:**
- Create: `src/risk/validator.py`
- Modify: `tests/test_market_structure.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_market_structure.py`:
```python
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent / "src"))
from risk.validator import validate_order

_INTACT_BSL = {"id": "H1_BSL_x", "tf": "H1", "category": "swing_high",
               "price": 130.0, "strength": 1, "status": "intact",
               "swept_at": None, "origin_time": "2024.01.01 00:00"}
_SWEPT_SSL  = {"id": "H1_SSL_x", "pool_type": "SSL", "pool_price": 100.0,
               "sweep_time": "2024.01.01 05:00", "wick_extreme": 97.0,
               "close_price": 103.0, "confirmed": True, "tf": "H1"}

def _make_state(h1_state="bullish", last_choch=None):
    return {
        "structure": {"H1": {"state": h1_state, "last_choch": last_choch}},
        "sweeps": [_SWEPT_SSL],
        "liquidity": {"bsl": [_INTACT_BSL], "ssl": []},
    }

def test_validate_buy_passes():
    decision = {
        "decision": "BUY", "sl": 95.0, "tp": 130.0,
        "bot_managed_state": {"h1_bias": "bullish"},
    }
    result = validate_order(decision, _make_state(), positions=[], ask=103.5, bid=103.0)
    # R:R = (130 - 103.5) / (103.5 - 95) = 26.5 / 8.5 ≈ 3.12
    assert result["passed"] is True
    assert result["checks"]["rr"]["value"] > 1.3
    assert result["rejection_reason"] is None

def test_validate_fails_rr():
    decision = {
        "decision": "BUY", "sl": 102.0, "tp": 104.0,  # tiny TP
        "bot_managed_state": {"h1_bias": "bullish"},
    }
    result = validate_order(decision, _make_state(), positions=[], ask=103.5, bid=103.0)
    assert result["passed"] is False
    assert result["checks"]["rr"]["ok"] is False
    assert "R:R" in result["rejection_reason"]

def test_validate_fails_max_positions():
    decision = {
        "decision": "BUY", "sl": 95.0, "tp": 130.0,
        "bot_managed_state": {"h1_bias": "bullish"},
    }
    positions = [{"ticket": 1, "type": "BUY", "lots": 0.01, "open": 100.0,
                  "sl": 95.0, "tp": 130.0, "profit": 5.0, "symbol": "XAUUSD"}]
    result = validate_order(decision, _make_state(), positions=positions, ask=103.5, bid=103.0)
    assert result["passed"] is False
    assert result["checks"]["max_positions"]["ok"] is False

def test_validate_fails_direction_vs_bias():
    decision = {
        "decision": "BUY", "sl": 95.0, "tp": 130.0,
        "bot_managed_state": {"h1_bias": "bearish"},  # bias says bearish, want to BUY
    }
    result = validate_order(decision, _make_state(h1_state="bearish"), positions=[], ask=103.5, bid=103.0)
    assert result["passed"] is False
    assert result["checks"]["direction_vs_bias"]["ok"] is False

def test_validate_wait_skips_checks():
    decision = {"decision": "WAIT", "sl": 0.0, "tp": 0.0, "bot_managed_state": {}}
    result = validate_order(decision, _make_state(), positions=[], ask=103.5, bid=103.0)
    assert result["passed"] is True
    assert result["checks"] == {}
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_market_structure.py -k "validate" -v
```
Expected: `ImportError` or `5 failed`

- [ ] **Step 3: Implement validator**

Create `src/risk/validator.py`:
```python
"""
Hard validation checks applied to every LLM order before execution.
If any check fails, the order is rejected and the cycle is logged as WAIT.
"""
from __future__ import annotations


def validate_order(
    decision: dict,
    market_state: dict,
    positions: list[dict],
    ask: float,
    bid: float,
    min_rr: float = 1.3,
    tp_tolerance: float = 0.5,
) -> dict:
    """
    Run all hard checks on a BUY or SELL decision.
    Returns {"passed": bool, "checks": dict, "rejection_reason": str | None}.
    WAIT/HOLD/CLOSE decisions pass immediately with empty checks.
    """
    action = decision.get("decision", "WAIT").upper()
    if action not in ("BUY", "SELL"):
        return {"passed": True, "checks": {}, "rejection_reason": None}

    sl = float(decision.get("sl") or 0)
    tp = float(decision.get("tp") or 0)
    entry = ask if action == "BUY" else bid
    checks: dict = {}
    reasons: list[str] = []

    # R:R ≥ 1.3
    sl_dist = abs(entry - sl)
    tp_dist = abs(tp - entry)
    rr = round(tp_dist / sl_dist, 2) if sl_dist > 0 else 0.0
    rr_ok = rr >= min_rr
    checks["rr"] = {"ok": rr_ok, "value": rr}
    if not rr_ok:
        reasons.append(f"R:R {rr:.2f} < {min_rr}")

    # Max 1 simultaneous position
    max_pos_ok = len(positions) == 0
    checks["max_positions"] = {"ok": max_pos_ok}
    if not max_pos_ok:
        reasons.append("position already open")

    # Direction consistent with H1 bias (allow entry if CHoCH H1 confirmed)
    bm = decision.get("bot_managed_state") or {}
    h1_bias = bm.get("h1_bias", "unclear")
    h1_struct = market_state.get("structure", {}).get("H1", {})
    choch = h1_struct.get("last_choch")
    if action == "BUY":
        bias_ok = h1_bias == "bullish" or (choch and choch.get("direction") == "bullish")
    else:
        bias_ok = h1_bias == "bearish" or (choch and choch.get("direction") == "bearish")
    checks["direction_vs_bias"] = {"ok": bias_ok}
    if not bias_ok:
        reasons.append(f"{action} conflicts with h1_bias={h1_bias!r}")

    # SL beyond the most recent confirmed sweep wick
    confirmed_sweeps = [s for s in market_state.get("sweeps", []) if s.get("confirmed")]
    sl_ok = True
    if confirmed_sweeps:
        if action == "BUY":
            ssl_sweeps = [s for s in confirmed_sweeps if s.get("pool_type") == "SSL"]
            if ssl_sweeps:
                latest = max(ssl_sweeps, key=lambda s: s["sweep_time"])
                sl_ok = sl < latest["wick_extreme"]
        else:
            bsl_sweeps = [s for s in confirmed_sweeps if s.get("pool_type") == "BSL"]
            if bsl_sweeps:
                latest = max(bsl_sweeps, key=lambda s: s["sweep_time"])
                sl_ok = sl > latest["wick_extreme"]
    checks["sl_beyond_sweep"] = {"ok": sl_ok}
    if not sl_ok:
        reasons.append("SL not beyond swept extreme")

    # TP within tolerance of an intact liquidity pool
    liq = market_state.get("liquidity", {})
    all_pools = liq.get("bsl", []) + liq.get("ssl", [])
    intact = [p for p in all_pools if p.get("status") == "intact"]
    tp_ok = any(abs(p["price"] - tp) <= tp_tolerance for p in intact)
    checks["tp_at_intact_liquidity"] = {"ok": tp_ok}
    if not tp_ok:
        reasons.append(f"TP {tp:.2f} not within {tp_tolerance} of any intact pool")

    passed = all(v["ok"] for v in checks.values())
    return {
        "passed": passed,
        "checks": checks,
        "rejection_reason": "; ".join(reasons) if reasons else None,
    }
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_market_structure.py -k "validate" -v
```
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add src/risk/validator.py tests/test_market_structure.py
git commit -m "feat: add hard order validation (R:R, SL sweep, TP liquidity, bias)"
```

---

## Task 14: Wire everything into aurum.py

**Files:**
- Modify: `aurum.py`

- [ ] **Step 1: Add imports at the top of aurum.py**

After `from risk.executor import execute`, add:
```python
from risk.validator import validate_order
```

- [ ] **Step 2: Replace Phase 2 in the cycle() function**

The current Phase 2 calls `update_code_managed_state(state, context, last_decision[0], config)`.
The new `updater.py` no longer needs `cfg` (config) for ATR — it's handled inside `build_market_state`. Signature is the same, so no change needed to the call. But we now want to extract the market_state after the update for use in validation:

```python
        # Phase 2 — state update
        tui.set_state("Updating state...", f"Cycle {n}  ·  Step 2/4")
        state = load_state(config.STATE_FILE)
        changes = update_code_managed_state(state, context, last_decision[0], config)
        logger.log_state_changes(changes)
        market_state = state["code_managed"].get("market_state") or {}
```

- [ ] **Step 3: Replace Phase 3 prompt building**

Find and replace the `market_text = serialize_for_prompt(...)` call:
```python
        market_text = serialize_for_prompt(
            context,
            market_state=market_state,
            last_result=last_result[0],
            bot_managed=state.get("bot_managed"),
        )
```

- [ ] **Step 4: Add validation between agent call and execution**

After the `save_state` call and before `# Phase 4 — execution`, insert:

```python
        # Hard validation — reject orders that violate structural constraints
        validation = validate_order(
            decision,
            market_state,
            context["positions"],
            ask=context["price"]["ask"],
            bid=context["price"]["bid"],
        )
```

- [ ] **Step 5: Conditionally skip execute() on validation failure**

Replace the Phase 4 block:
```python
        # Phase 4 — execution
        tui.set_state("Executing...", f"Cycle {n}  ·  Step 4/4")
        if not validation["passed"]:
            result = f"WAIT: validator rejected — {validation['rejection_reason']}"
            logger.warn(f"Order rejected by validator: {validation['rejection_reason']}")
        else:
            result = execute(decision, context, mt4, config)
        last_result[0] = result
        last_decision[0] = decision
```

- [ ] **Step 6: Add structured cycle log entry**

Replace `logger.log_cycle(context, decision, result)` with:
```python
        import json as _json
        logger.log_cycle(context, decision, result)
        logger.info(
            "CYCLE_LOG: " + _json.dumps({
                "cycle_time": context["timestamp"],
                "final_decision": decision.get("decision"),
                "validation": validation,
                "rejection_reason": validation.get("rejection_reason"),
            })
        )
```

- [ ] **Step 7: Verify aurum.py imports cleanly**

```bash
python -c "import sys; sys.path.insert(0, 'src'); import ast; ast.parse(open('aurum.py').read()); print('syntax OK')"
```
Expected: `syntax OK`

- [ ] **Step 8: Commit**

```bash
git add aurum.py
git commit -m "feat: wire Layer 1 market state and hard validator into cycle"
```

---

## Task 15: Update agent/caller.py

**Files:**
- Modify: `src/agent/caller.py`

- [ ] **Step 1: Update _WAIT_RESPONSE and _OUTPUT_INSTRUCTION**

In `src/agent/caller.py`, update `_WAIT_RESPONSE` (only field name changes):
No changes needed — `_bot_managed_state` key stays the same internally.

Replace `_OUTPUT_INSTRUCTION` with:
```python
_OUTPUT_INSTRUCTION = """

---
Respond ONLY with a single valid JSON object. No markdown fences, no text outside the JSON.
Required structure:
{
  "decision": "BUY|SELL|CLOSE|HOLD|WAIT",
  "reasoning": "...",
  "entry_notes": "...",
  "sl": 0.00,
  "tp": 0.00,
  "confidence": 0.0,
  "ticket_to_close": null,
  "next_check_minutes": null,
  "bot_managed_state": {
    "h1_bias": "bullish|bearish|ranging|unclear",
    "h1_bias_since": "ISO-8601 or null",
    "h1_bias_justification": "string",
    "m15_bias": "bullish|bearish|ranging|unclear",
    "m15_bias_justification": "string",
    "pending_setup": {
      "active": false,
      "type": null,
      "context": "",
      "target_poi_id": null,
      "target_liquidity_id": null,
      "expected_direction": null,
      "since": null,
      "invalidate_above": null,
      "invalidate_below": null,
      "invalidate_after": null
    },
    "narrative": "string"
  }
}
"""
```

- [ ] **Step 2: Verify import**

```bash
python -c "import sys; sys.path.insert(0, 'src'); from agent.caller import call_agent; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/agent/caller.py
git commit -m "feat: update agent output schema to h1_bias/m15_bias"
```

---

## Task 16: Rewrite system_prompt.md

**Files:**
- Modify: `src/strategy/system_prompt.md`

- [ ] **Step 1: Replace system_prompt.md with new version**

Write `src/strategy/system_prompt.md`:

```markdown
# AURUM — System Prompt

## Role
You are AURUM, an institutional price action analyst for XAUUSD (gold). You operate like a smart money trader. You receive a pre-computed `STRUCTURAL_MARKET_STATE` JSON — all structural analysis (swing points, BOS/CHoCH, liquidity pools, sweeps, FVGs, order blocks, dealing range, ATR) has been calculated deterministically by the system. Your job is **contextual judgment**: does the computed confluence justify a trade? Is it convincing or marginal? Does the session support it?

You do NOT calculate structure. You do NOT identify swing points, BOS/CHoCH, or liquidity levels from raw candles — none are provided. You read what the system has computed and decide whether to act.

---

## Core Trading Philosophy

**The market is driven by liquidity.** Your job is to read the pre-computed state and identify when the full institutional sequence is present:
1. A liquidity pool was swept (`status: swept` in `liquidity.bsl` or `liquidity.ssl`).
2. A structural shift confirmed the new direction (`last_choch` or `last_bos` on M15/M5).
3. A POI (FVG or OB in the new direction, `status: intact`) offers a refined entry.
4. H1 bias and session align.

If this sequence is not fully present in the pre-computed state, decide WAIT.

---

## Reading the STRUCTURAL_MARKET_STATE

The JSON you receive has these sections:

- **`meta`** — timestamp, symbol, session, current price.
- **`atr`** — ATR in USD for H1, M15, M5. Use for context on volatility.
- **`structure.{H1,M15,M5}`** — `state` (bullish/bearish/ranging), `last_bos`, `last_choch`, labeled swing highs/lows.
- **`liquidity.bsl`** / **`liquidity.ssl`** — buy-side and sell-side liquidity pools with `status` (intact/swept).
- **`liquidity.session_levels`** — prev day high/low, prev week high/low, Asia high/low.
- **`sweeps`** — confirmed and unconfirmed sweeps with `pool_id`, `wick_extreme`, `confirmed`.
- **`fvg.{H1,M15,M5}`** — fair value gaps with `status` (intact/partial/filled) and `mitigation_pct`.
- **`order_blocks.{H1,M15,M5}`** — order blocks with `status` (intact/mitigated).
- **`dealing_range`** — H1 range, equilibrium, and `current_zone` (premium/discount/equilibrium).

---

## Decision Framework (apply in order)

1. **H1 structure and bias** — What is `structure.H1.state`? Is there a recent `last_choch` on H1? Maintain `h1_bias` in your memory. Only change it when `structure.H1.last_choch` shows a confirmed change.

2. **Liquidity context** — Are there intact pools (`status: intact`) on the side the market is heading? Has the relevant pool been swept (`status: swept`) in `sweeps` (look for `confirmed: true`)?

3. **M15/M5 confirmation** — After a sweep, is there a `last_choch` on M15 or M5 in the new direction? Is there an intact FVG or OB in that direction within the swept zone?

4. **POI entry** — Reference the FVG or OB by its `id` in your reasoning and in `pending_setup.target_poi_id`. Is it still `intact`?

5. **Session filter** — `meta.session`: prioritize London (07:00–10:00 UTC) and NY (12:00–16:00 UTC). During Asia, default to WAIT unless a strong H1 POI is actively being mitigated.

6. **Your judgment** — Even if the rules are mechanically met, decide WAIT if:
   - The sweep was marginal (small wick, `wick_extreme` barely past the pool).
   - Confirmation is weak (no clean displacement candle, `last_choch` far in time).
   - The session is wrong.
   - Contradictory signals in multiple timeframes.

---

## Absolute Rules

- **NEVER specify lot size** — the system calculates it.
- SL must be beyond the `wick_extreme` of the relevant confirmed sweep. The system validates this; if your SL is wrong, the order is rejected.
- TP must target the next intact pool (`status: intact`). Reference its `id` in `entry_notes`. The system validates this.
- R:R minimum 1.3 — the system recalculates and enforces this. If your geometry is off, the order is rejected, so set SL and TP correctly.
- Confidence ≥ 0.60 required to trade. Below that, decide WAIT regardless.
- If a position is open: evaluate HOLD or CLOSE based on `open_position_metrics.tp_completion_pct` and whether `structure.M15.last_choch` has shifted against you.
- Maximum 1 position — system-enforced.

---

## Adaptive Polling

Include `next_check_minutes` (1–15) only when a specific event is imminent: a sweep developing, price approaching a POI, or a position near TP/SL. Omit otherwise.

---

## Memory (BOT_MEMORY)

You receive `BOT_MEMORY` with your state from the previous cycle. You MUST return an updated `bot_managed_state`.

**`h1_bias`**: Only change when `structure.H1.last_choch` shows a new direction. Update `h1_bias_since` and `h1_bias_justification`. If unsure, set to `unclear`.

**`m15_bias`**: Reflects M15 context. Can shift more often based on `structure.M15.last_choch`.

**`pending_setup`**: Activate when you see a developing sequence. Reference pool and POI by their IDs from `STRUCTURAL_MARKET_STATE`. Define `invalidate_above`/`invalidate_below` price levels. Clear the setup when it triggers, invalidates, or the structure changes.

**`narrative`**: ≤400 chars. The current story: what happened, what you expect next. Reference pool and POI IDs.

---

## Output Format

Respond ONLY with valid JSON. No text before or after.

```json
{
  "decision": "BUY|SELL|CLOSE|HOLD|WAIT",
  "reasoning": "≤200 words: what the computed state shows, why this justifies the decision",
  "entry_notes": "e.g. SSL H1_SSL_20240115_0900 swept (wick=2338.50), M15 CHoCH bullish at 2343.20, entering on M15_FVG_bull_4 fill, TP at H1_BSL_20240114_1600 (2367.50)",
  "sl": 0.00,
  "tp": 0.00,
  "confidence": 0.0,
  "ticket_to_close": null,
  "next_check_minutes": null,
  "bot_managed_state": {
    "h1_bias": "bullish|bearish|ranging|unclear",
    "h1_bias_since": "ISO-8601 or null",
    "h1_bias_justification": "≤200 chars",
    "m15_bias": "bullish|bearish|ranging|unclear",
    "m15_bias_justification": "≤200 chars",
    "pending_setup": {
      "active": false,
      "type": "waiting_for_sweep|waiting_for_choch|waiting_for_fvg_fill|waiting_for_retest|null",
      "context": "≤300 chars",
      "target_poi_id": "M15_FVG_bull_4 or null",
      "target_liquidity_id": "H1_BSL_20240114_1600 or null",
      "expected_direction": "BUY|SELL|null",
      "since": "ISO-8601 or null",
      "invalidate_above": null,
      "invalidate_below": null,
      "invalidate_after": "ISO-8601 or null"
    },
    "narrative": "≤400 chars"
  }
}
```
```

- [ ] **Step 2: Commit**

```bash
git add src/strategy/system_prompt.md
git commit -m "feat: rewrite system prompt — LLM reads pre-computed state, no raw candles"
```

---

## Task 17: schema.json

**Files:**
- Create: `schema.json`

- [ ] **Step 1: Create schema.json**

Create `schema.json` at the repo root:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "AURUM Schemas",
  "definitions": {
    "SwingPoint": {
      "type": "object",
      "required": ["price", "time", "candle_index", "label", "swept"],
      "properties": {
        "price": {"type": "number"},
        "time": {"type": "string"},
        "candle_index": {"type": "integer"},
        "label": {"type": ["string", "null"], "enum": ["HH", "HL", "LH", "LL", null]},
        "swept": {"type": "boolean"}
      }
    },
    "StructureBreak": {
      "type": "object",
      "required": ["price", "time", "direction", "broken_swing_time"],
      "properties": {
        "price": {"type": "number"},
        "time": {"type": "string"},
        "direction": {"type": "string", "enum": ["bullish", "bearish"]},
        "broken_swing_time": {"type": "string"}
      }
    },
    "LiquidityPool": {
      "type": "object",
      "required": ["id", "tf", "category", "price", "strength", "status", "swept_at", "origin_time"],
      "properties": {
        "id": {"type": "string"},
        "tf": {"type": "string", "enum": ["H1", "M15", "M5"]},
        "category": {"type": "string", "enum": ["swing_high", "swing_low", "equal_highs", "equal_lows"]},
        "price": {"type": "number"},
        "strength": {"type": "integer", "minimum": 1},
        "status": {"type": "string", "enum": ["intact", "swept"]},
        "swept_at": {"type": ["string", "null"]},
        "origin_time": {"type": "string"}
      }
    },
    "Sweep": {
      "type": "object",
      "required": ["tf", "pool_id", "pool_type", "pool_price", "sweep_time", "wick_extreme", "close_price", "confirmed"],
      "properties": {
        "tf": {"type": "string"},
        "pool_id": {"type": "string"},
        "pool_type": {"type": "string", "enum": ["BSL", "SSL"]},
        "pool_price": {"type": "number"},
        "sweep_time": {"type": "string"},
        "wick_extreme": {"type": "number"},
        "close_price": {"type": "number"},
        "confirmed": {"type": "boolean"}
      }
    },
    "FVG": {
      "type": "object",
      "required": ["id", "direction", "top", "bottom", "midpoint", "origin_time", "status", "mitigation_pct"],
      "properties": {
        "id": {"type": "string"},
        "direction": {"type": "string", "enum": ["bullish", "bearish"]},
        "top": {"type": "number"},
        "bottom": {"type": "number"},
        "midpoint": {"type": "number"},
        "origin_time": {"type": "string"},
        "status": {"type": "string", "enum": ["intact", "partial", "filled"]},
        "mitigation_pct": {"type": "number", "minimum": 0, "maximum": 100}
      }
    },
    "OrderBlock": {
      "type": "object",
      "required": ["id", "direction", "top", "bottom", "origin_time", "displacement_time", "status"],
      "properties": {
        "id": {"type": "string"},
        "direction": {"type": "string", "enum": ["bullish", "bearish"]},
        "top": {"type": "number"},
        "bottom": {"type": "number"},
        "origin_time": {"type": "string"},
        "displacement_time": {"type": "string"},
        "status": {"type": "string", "enum": ["intact", "mitigated"]}
      }
    },
    "structured_market_state": {
      "type": "object",
      "required": ["meta", "atr", "structure", "liquidity", "sweeps", "fvg", "order_blocks"],
      "properties": {
        "meta": {
          "type": "object",
          "properties": {
            "timestamp": {"type": "string"},
            "symbol": {"type": "string"},
            "session": {"type": "string"},
            "price": {
              "type": "object",
              "properties": {
                "bid": {"type": "number"}, "ask": {"type": "number"}, "spread": {"type": "number"}
              }
            }
          }
        },
        "atr": {
          "type": "object",
          "properties": {
            "H1": {"type": "number"}, "M15": {"type": "number"}, "M5": {"type": "number"}
          }
        },
        "structure": {
          "type": "object",
          "additionalProperties": {
            "type": "object",
            "properties": {
              "state": {"type": "string", "enum": ["bullish", "bearish", "ranging"]},
              "swing_sequence": {"type": "array", "items": {"type": "string"}},
              "swing_highs": {"type": "array", "items": {"$ref": "#/definitions/SwingPoint"}},
              "swing_lows":  {"type": "array", "items": {"$ref": "#/definitions/SwingPoint"}},
              "last_bos":   {"oneOf": [{"$ref": "#/definitions/StructureBreak"}, {"type": "null"}]},
              "last_choch": {"oneOf": [{"$ref": "#/definitions/StructureBreak"}, {"type": "null"}]}
            }
          }
        },
        "liquidity": {
          "type": "object",
          "properties": {
            "bsl": {"type": "array", "items": {"$ref": "#/definitions/LiquidityPool"}},
            "ssl": {"type": "array", "items": {"$ref": "#/definitions/LiquidityPool"}},
            "session_levels": {"type": "object"}
          }
        },
        "sweeps": {"type": "array", "items": {"$ref": "#/definitions/Sweep"}},
        "fvg": {
          "type": "object",
          "additionalProperties": {"type": "array", "items": {"$ref": "#/definitions/FVG"}}
        },
        "order_blocks": {
          "type": "object",
          "additionalProperties": {"type": "array", "items": {"$ref": "#/definitions/OrderBlock"}}
        },
        "dealing_range": {
          "type": ["object", "null"],
          "properties": {
            "tf": {"type": "string"}, "high": {"type": "number"}, "high_time": {"type": "string"},
            "low": {"type": "number"}, "low_time": {"type": "string"},
            "equilibrium": {"type": "number"}, "current_price": {"type": "number"},
            "current_zone": {"type": "string", "enum": ["premium", "discount", "equilibrium"]}
          }
        }
      }
    },
    "llm_output": {
      "type": "object",
      "required": ["decision", "reasoning", "sl", "tp", "confidence", "bot_managed_state"],
      "properties": {
        "decision": {"type": "string", "enum": ["BUY", "SELL", "CLOSE", "HOLD", "WAIT"]},
        "reasoning": {"type": "string"},
        "entry_notes": {"type": "string"},
        "sl": {"type": "number"},
        "tp": {"type": "number"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "ticket_to_close": {"type": ["integer", "null"]},
        "next_check_minutes": {"type": ["integer", "null"], "minimum": 1, "maximum": 15},
        "bot_managed_state": {
          "type": "object",
          "properties": {
            "h1_bias":  {"type": "string", "enum": ["bullish", "bearish", "ranging", "unclear"]},
            "h1_bias_since": {"type": ["string", "null"]},
            "h1_bias_justification": {"type": "string"},
            "m15_bias": {"type": "string", "enum": ["bullish", "bearish", "ranging", "unclear"]},
            "m15_bias_justification": {"type": "string"},
            "pending_setup": {
              "type": "object",
              "properties": {
                "active": {"type": "boolean"},
                "type": {"type": ["string", "null"]},
                "context": {"type": "string"},
                "target_poi_id": {"type": ["string", "null"]},
                "target_liquidity_id": {"type": ["string", "null"]},
                "expected_direction": {"type": ["string", "null"]},
                "since": {"type": ["string", "null"]},
                "invalidate_above": {"type": ["number", "null"]},
                "invalidate_below": {"type": ["number", "null"]},
                "invalidate_after": {"type": ["string", "null"]}
              }
            },
            "narrative": {"type": "string"}
          }
        }
      }
    }
  }
}
```

- [ ] **Step 2: Validate it parses**

```bash
python -c "import json; json.load(open('schema.json')); print('valid JSON')"
```
Expected: `valid JSON`

- [ ] **Step 3: Run full test suite one final time**

```bash
python -m pytest tests/test_market_structure.py -v
```
Expected: All pass.

- [ ] **Step 4: Final commit**

```bash
git add schema.json
git commit -m "feat: add JSON Schema for structured_market_state and LLM output"
```

---

## Self-Review

### Spec coverage check

| Spec requirement | Task |
|---|---|
| Swing points with N-fractal, candle_index | Task 2 |
| HH/HL/LH/LL labels using closes | Task 3 |
| BOS/CHoCH via close-based breaks | Task 3 |
| BSL/SSL pools + equal highs/lows | Task 4 |
| Pool persistence across cycles | Task 4 |
| Session levels (prev day/week, Asia) | Task 8, 9 |
| Sweep detection confirmed/unconfirmed | Task 5 |
| FVG with mitigation % | Task 6 |
| Order blocks with mitigation | Task 7 |
| Dealing range + equilibrium + zone | Task 8 |
| ATR per timeframe | Task 1 |
| `build_market_state` integration | Task 9 |
| Config update (remove H4) | Task 10 |
| `serialize_for_prompt` rewrite | Task 10 |
| Schema v3 migration (bias rename) | Task 11 |
| `updater.py` calls Layer 1 | Task 12 |
| Hard validation (R:R, SL, TP, bias) | Task 13 |
| Validator wired into cycle | Task 14 |
| Structured cycle logging | Task 14 |
| `caller.py` output schema update | Task 15 |
| New system prompt | Task 16 |
| `schema.json` | Task 17 |
| Unit tests for all functions | Tasks 1–9, 13 |

All spec requirements covered.
