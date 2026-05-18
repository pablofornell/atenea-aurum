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


# ── Liquidity Pools ───────────────────────────────────────────────────────────

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


# ── Sweeps ────────────────────────────────────────────────────────────────────

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


# ── FVGs ──────────────────────────────────────────────────────────────────────

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
                "id": f"{tf}_FVG_bull_" + c1["time"].replace(".", "").replace(" ", "_").replace(":", ""),
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
                "id": f"{tf}_FVG_bear_" + c1["time"].replace(".", "").replace(" ", "_").replace(":", ""),
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


# ── Order Blocks ──────────────────────────────────────────────────────────────

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
    Bearish OB: last bullish candle (close > open) before a bearish structural break.
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


# ── Dealing Range ─────────────────────────────────────────────────────────────

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


# ── Asia Session Range ────────────────────────────────────────────────────────

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


# ── Market State Builder ──────────────────────────────────────────────────────

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
