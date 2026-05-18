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


# ── Swing Points ───────────────────────────────────────────────────────────────

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


# ── Market Structure ──────────────────────────────────────────────────────────

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
