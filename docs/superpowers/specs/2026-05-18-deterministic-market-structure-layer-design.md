# Design: Deterministic Market Structure Layer

**Date:** 2026-05-18
**Status:** Approved
**Scope:** Rearchitecture of the AURUM trading bot to separate deterministic structural analysis (Python) from contextual judgment (LLM).

---

## Problem

The current architecture sends raw OHLC candles to the LLM and asks it to derive all SMC structure (swing points, BOS/CHoCH, liquidity pools, sweeps, FVGs, order blocks) AND make a trade decision in a single inference. This introduces non-deterministic noise: the same candles produce different structural readings across cycles, leading to hallucinated sweeps, inconsistent CHoCH identification, and arithmetic errors in R:R calculation.

---

## Solution: Two-Layer Architecture

```
MT4 (OHLC) → Layer 1: Python structural engine → structured_market_state (JSON)
                                                          ↓
                                              Layer 2: LLM judgment agent
                                                          ↓
                                              decision JSON → Python validation → MT4 / reject
```

**Layer 1** — deterministic, testable, no LLM. Computes all structural facts.
**Layer 2** — LLM receives pre-computed structure. Provides only contextual judgment: is the confluence convincing? Does the session support entry? Are there contradictory signals that argue for WAIT despite rules being met?

**Hard validation** — Python re-validates every LLM order before execution. If any check fails, the order is silently rejected and the cycle is logged as WAIT with the rejection reason.

---

## Timeframes and Lookbacks

| Timeframe | Candles | Coverage |
|---|---|---|
| H1 | 100 | ~4 days — structural bias |
| M15 | 64 | ~16 hours — setup context |
| M5 | 48 | ~4 hours — entry confirmation |

H4 is removed. H1 is now the highest timeframe. `config.py` will be updated: `CANDLES_H1 = 100`, `CANDLES_M15 = 64`, `CANDLES_M5 = 48`.

---

## Layer 1: Structural Engine (`src/analysis/market_structure.py`)

All functions are pure: same input → same output always. No network, no LLM, no side effects.

### 1. Swing Point Detection

**Algorithm (N-fractal):** A candle at index `i` is a swing high if `candles[i].high > candles[i-k].high` for all `k ∈ [1..N]` AND `candles[i].high > candles[i+k].high` for all `k ∈ [1..N]`. Default N=2. Configurable. Works identically for swing lows with `.low`.

Each swing point output:
```python
{ "price": float, "time": str, "candle_index": int, "label": "HH"|"HL"|"LH"|"LL"|None, "swept": bool }
```

`candle_index` is the position from the end of the array (0 = most recent). Required for reproducible tests without real timestamps.

Labels (HH/HL/LH/LL) are assigned by comparing each swing to the previous swing of the same direction using candle **closes**, not wicks. A swing high close > previous swing high close = HH; < = LH. Same for lows.

### 2. Market Structure

Per timeframe. Structure state derives from the last 4+ swing labels:
- `bullish` — most recent pattern is HH+HL sequence
- `bearish` — most recent pattern is LH+LL sequence
- `ranging` — alternating or ambiguous

Output per timeframe:
```python
{
    "state": "bullish"|"bearish"|"ranging",
    "swing_sequence": ["HL", "HH", "HL", "HH"],  # last N labels
    "swing_highs": [SwingPoint, ...],
    "swing_lows": [SwingPoint, ...],
    "last_bos": StructureBreak | None,
    "last_choch": StructureBreak | None,
}
```

### 3. BOS / CHoCH Detection

Defined on candle **closes**, not wicks.

- **BOS (Break of Structure):** Close above the most recent swing high when structure is bullish (continuation), or close below most recent swing low when bearish.
- **CHoCH (Change of Character):** First close above the most recent swing high when structure is bearish (counter-trend reversal), or first close below most recent swing low when bullish.

The label (BOS vs CHoCH) is determined by the prevailing structure state at the moment of the break.

```python
StructureBreak = {
    "price": float,          # the broken swing level
    "time": str,             # close time of the breaking candle
    "direction": "bullish"|"bearish",
    "broken_swing_time": str # origin candle of the broken swing
}
```

### 4. Liquidity Pools

**BSL (Buy-Side Liquidity):** Unswept swing highs + equal highs.
**SSL (Sell-Side Liquidity):** Unswept swing lows + equal lows.

Equal highs/lows: two or more swing points within a configurable pip tolerance (default 0.5 USD for XAUUSD). These are treated as high-priority targets and carry `strength > 1`.

Session levels are separate (computed from `get_day_ohlc` and `get_week_hl`, not from fractal detection):
- `prev_day_high`, `prev_day_low`
- `prev_week_high`, `prev_week_low`
- `asia_high`, `asia_low` (00:00–07:00 UTC range high/low)
- `today_open`

Pool status persists across cycles: once swept, the pool stays in the state as `swept` with a timestamp. This prevents the structural engine from re-surfacing a swept level as a new target.

Each pool entry:
```python
{
    "id": str,           # e.g. "H1_BSL_0"
    "tf": "H1"|"M15"|"M5",
    "category": "swing_high"|"swing_low"|"equal_highs"|"equal_lows",
    "price": float,
    "strength": int,     # 1 = single swing, 2+ = equal highs/lows
    "status": "intact"|"swept",
    "swept_at": str | None,
    "origin_time": str
}
```

### 5. Sweep Detection

A sweep is confirmed when: a candle's wick crosses the pool level AND the candle closes back on the opposite side.

Unconfirmed sweep: wick reached the pool but the candle has not yet closed back (may appear at the current forming candle). `confirmed: false` entries are included in the output to alert the LLM of a developing situation.

```python
{
    "tf": str,
    "pool_id": str,           # links to bsl/ssl entry
    "pool_type": "BSL"|"SSL",
    "pool_price": float,
    "sweep_time": str,
    "wick_extreme": float,    # the farthest point of the wick
    "close_price": float,
    "confirmed": bool
}
```

### 6. Fair Value Gaps (FVG)

Three-candle pattern: gap between candle[i-2].high and candle[i].low (bullish FVG) or candle[i-2].low and candle[i].high (bearish FVG). Candle[i-1] is the imbalance candle.

Mitigation: tracked by how far price has retraced into the gap. `mitigation_pct`: 0 = untouched, 50 = price reached midpoint, 100 = gap fully filled.

```python
{
    "id": str,
    "direction": "bullish"|"bearish",
    "top": float,
    "bottom": float,
    "midpoint": float,
    "origin_time": str,    # timestamp of the middle candle
    "status": "intact"|"partial"|"filled",
    "mitigation_pct": float
}
```

### 7. Order Blocks

The last candle of the opposite color immediately before a displacement that breaks structure. Bullish OB = last bearish candle before a bullish impulse that creates a BOS/CHoCH. Bearish OB = last bullish candle before a bearish impulse.

```python
{
    "id": str,
    "direction": "bullish"|"bearish",
    "top": float,
    "bottom": float,
    "origin_time": str,       # the OB candle itself
    "displacement_time": str, # the candle that created the impulse
    "status": "intact"|"mitigated"
}
```

Mitigated = price has traded back into the OB range (any wick).

### 8. Dealing Range and Equilibrium

The most recent significant swing range on H1: from the last major swing low to the last major swing high (or vice versa, depending on structure direction).

```python
{
    "tf": "H1",
    "high": float, "high_time": str,
    "low": float,  "low_time": str,
    "equilibrium": float,     # (high + low) / 2
    "current_price": float,
    "current_zone": "premium"|"discount"|"equilibrium"  # equilibrium band = eq ± 5% of (high-low)
}
```

### 9. ATR

Simple ATR calculation from OHLC, period=14, per timeframe. Output in USD (raw price movement).

---

## `structured_market_state` JSON Contract

This is the full output of Layer 1, input to Layer 2.

```json
{
  "meta": {
    "timestamp": "2024-01-15T12:00:00Z",
    "symbol": "XAUUSD",
    "session": "London",
    "price": { "bid": 2345.67, "ask": 2346.47, "spread": 0.80 }
  },
  "atr": {
    "H1": 8.50,
    "M15": 3.20,
    "M5": 1.80
  },
  "structure": {
    "H1": {
      "state": "bullish",
      "swing_sequence": ["HL", "HH", "HL", "HH"],
      "swing_highs": [
        { "price": 2360.50, "time": "2024-01-15T10:00:00Z",
          "candle_index": 5, "label": "HH", "swept": false }
      ],
      "swing_lows": [
        { "price": 2340.10, "time": "2024-01-15T06:00:00Z",
          "candle_index": 9, "label": "HL", "swept": false }
      ],
      "last_bos": {
        "price": 2352.30,
        "time": "2024-01-15T08:00:00Z",
        "direction": "bullish",
        "broken_swing_time": "2024-01-14T20:00:00Z"
      },
      "last_choch": null
    },
    "M15": { "...same shape..." },
    "M5":  { "...same shape..." }
  },
  "liquidity": {
    "bsl": [
      { "id": "H1_BSL_0", "tf": "H1", "category": "swing_high",
        "price": 2367.50, "strength": 1,
        "status": "intact", "swept_at": null, "origin_time": "2024-01-14T16:00:00Z" },
      { "id": "H1_BSL_eq_0", "tf": "H1", "category": "equal_highs",
        "price": 2352.00, "strength": 3,
        "status": "swept", "swept_at": "2024-01-15T09:30:00Z", "origin_time": "2024-01-14T10:00:00Z" }
    ],
    "ssl": [
      { "id": "H1_SSL_0", "tf": "H1", "category": "swing_low",
        "price": 2330.20, "strength": 1,
        "status": "intact", "swept_at": null, "origin_time": "2024-01-13T08:00:00Z" }
    ],
    "session_levels": {
      "prev_day_high":  { "price": 2370.00, "status": "intact", "swept_at": null },
      "prev_day_low":   { "price": 2330.50, "status": "intact", "swept_at": null },
      "prev_week_high": { "price": 2380.00, "status": "intact", "swept_at": null },
      "prev_week_low":  { "price": 2310.00, "status": "intact", "swept_at": null },
      "asia_high":      { "price": 2348.50, "status": "swept", "swept_at": "2024-01-15T08:30:00Z" },
      "asia_low":       { "price": 2338.20, "status": "intact", "swept_at": null },
      "today_open":     2340.00
    }
  },
  "sweeps": [
    {
      "tf": "M15",
      "pool_id": "H1_SSL_0",
      "pool_type": "SSL",
      "pool_price": 2340.10,
      "sweep_time": "2024-01-15T09:30:00Z",
      "wick_extreme": 2338.50,
      "close_price": 2343.20,
      "confirmed": true
    }
  ],
  "fvg": {
    "H1":  [],
    "M15": [
      { "id": "M15_FVG_0", "direction": "bullish",
        "top": 2347.80, "bottom": 2344.20, "midpoint": 2346.00,
        "origin_time": "2024-01-15T09:30:00Z",
        "status": "intact", "mitigation_pct": 0.0 }
    ],
    "M5":  []
  },
  "order_blocks": {
    "H1":  [],
    "M15": [
      { "id": "M15_OB_0", "direction": "bullish",
        "top": 2344.50, "bottom": 2342.80,
        "origin_time": "2024-01-15T09:15:00Z",
        "displacement_time": "2024-01-15T09:30:00Z",
        "status": "intact" }
    ],
    "M5":  []
  },
  "dealing_range": {
    "tf": "H1",
    "high": 2367.50, "high_time": "2024-01-14T16:00:00Z",
    "low":  2330.50, "low_time":  "2024-01-13T08:00:00Z",
    "equilibrium": 2349.00,
    "current_price": 2345.67,
    "current_zone": "discount"
  }
}
```

---

## Layer 2: LLM Agent

The LLM receives:
1. `structured_market_state` (full Layer 1 output)
2. Open position data and metrics (from `code_managed.open_position_metrics`)
3. `bot_managed` memory from the previous cycle
4. `recent_decisions` (last 5 cycles)
5. `last_cycle_result` (execution result or rejection reason from previous cycle)

The LLM does NOT:
- Calculate swing points, BOS/CHoCH, FVGs, order blocks, or liquidity levels
- Recalculate R:R geometry (it sees pre-computed levels and proposes SL/TP; Python validates)
- Decide if structural prerequisites are present (Python enforces that)

The LLM DOES:
- Evaluate whether the calculated confluence justifies a trade (sweep + CHoCH + POI alignment + session)
- Decide BUY / SELL / CLOSE / HOLD / WAIT
- Explain its reasoning in terms of the pre-computed IDs (e.g., "SSL at H1_SSL_0 swept, M15 CHoCH confirmed, entering on M15_FVG_0 fill")
- Return updated `bot_managed_state`
- Optionally request an earlier poll via `next_check_minutes`

### LLM Output JSON Schema

```json
{
  "decision": "BUY|SELL|CLOSE|HOLD|WAIT",
  "reasoning": "string ≤200 words",
  "entry_notes": "string",
  "sl": 0.00,
  "tp": 0.00,
  "confidence": 0.0,
  "ticket_to_close": null,
  "next_check_minutes": null,
  "bot_managed_state": {
    "h1_bias": "bullish|bearish|ranging|unclear",
    "h1_bias_since": "ISO-8601 or null",
    "h1_bias_justification": "string ≤200 chars",
    "m15_bias": "bullish|bearish|ranging|unclear",
    "m15_bias_justification": "string ≤200 chars",
    "pending_setup": {
      "active": false,
      "type": "waiting_for_sweep|waiting_for_choch|waiting_for_fvg_fill|waiting_for_retest|null",
      "context": "string ≤300 chars",
      "target_poi_id": "M15_FVG_0 or null",
      "target_liquidity_id": "H1_BSL_0 or null",
      "expected_direction": "BUY|SELL|null",
      "since": "ISO-8601 or null",
      "invalidate_above": null,
      "invalidate_below": null,
      "invalidate_after": "ISO-8601 or null"
    },
    "narrative": "string ≤400 chars"
  }
}
```

**Changes from current schema:**
- `h4_bias` / `h4_bias_since` → `h1_bias` / `h1_bias_since`
- `h1_bias` → `m15_bias` (no `_since` — shifts faster, less weight)
- `target_liquidity_price` (float) → `target_liquidity_id` (string ID from Layer 1)

---

## Python Hard Validation (non-negotiable)

Before executing any BUY/SELL order from the LLM, Python checks:

| Check | Logic |
|---|---|
| R:R ≥ 1.3 | `abs(tp - entry) / abs(sl - entry) >= 1.3`, using real ask/bid at execution |
| SL beyond swept extreme | SL must be beyond `wick_extreme` of the most recent confirmed sweep in the relevant direction |
| TP at intact liquidity | `tp` price must be within 0.5 USD of a pool with `status == "intact"` in `bsl` or `ssl` |
| Max 1 position | `len(positions) == 0` before opening |
| Direction vs H1 bias | BUY requires `h1_bias == "bullish"` OR a confirmed `last_choch` in H1 with `direction == "bullish"` |

Failure → log rejection with reason, treat cycle as WAIT, pass rejection to LLM in `last_cycle_result` next cycle.

---

## File Map (changes to existing codebase)

| File | Action | Notes |
|---|---|---|
| `src/analysis/market_structure.py` | **New** | Layer 1 engine. Pure functions. |
| `src/analysis/__init__.py` | **New** | Empty. |
| `tests/test_market_structure.py` | **New** | Unit tests with synthetic candle fixtures. |
| `src/state/schema.py` | **Modify** | Rename h4_bias → h1_bias, h1_bias → m15_bias; add `structured_market_state` default. |
| `src/state/updater.py` | **Modify** | Call `market_structure.py` and merge output into `code_managed`. |
| `src/data/processor.py` | **Modify** | Update candle counts (H1=100, M15=64, M5=48), remove H4. |
| `src/strategy/system_prompt.md` | **Modify** | Rewrite: LLM receives pre-computed state, does not derive structure. |
| `src/agent/caller.py` | **Modify** | Update `_OUTPUT_INSTRUCTION` and `bot_managed` field names. |
| `src/config.py` | **Modify** | `CANDLES_H1=100`, `CANDLES_M15=64`, `CANDLES_M5=48`, remove `CANDLES_H4`. |
| `aurum.py` | **Modify** | Integrate hard validation step between agent call and execution. |
| `schema.json` | **New** | JSON Schema (draft-07) for `structured_market_state` and LLM output. |

---

## Liquidity Pool State Persistence

`structured_market_state` is stored in `code_managed.market_state` in `state/structural_state_{mode}.json`. It replaces the current flat `code_managed.atr` fields (ATR is now at `market_state.atr`).

Pool `swept` status must persist across cycles. The sweep detection re-runs each cycle on fresh candles, but the `swept` flag and timestamp must survive the state file. Merge strategy in `state/updater.py`:
- Pool present in new candle data but marked `swept` in previous cycle → keep as swept. Match by `id`.
- New pool (new `id`) → add as `intact`.
- Pool whose `id` no longer appears (fell outside the candle window) → drop it.

**State file migration:** Existing files have `h4_bias`/`h1_bias` in `bot_managed` (`schema_version=2`). On load, `state/io.py` detects `schema_version < 3` and renames: `h4_bias` → `h1_bias`, `h4_bias_since` → `h1_bias_since`, `h4_bias_justification` → `h1_bias_justification`, `h1_bias` → `m15_bias`, `h1_bias_justification` → `m15_bias_justification`. Bump `schema_version` to 3 on save.

---

## Logging Requirements

Every cycle must log to `logs/aurum_decisions_*.jsonl`:

```json
{
  "cycle_time": "ISO-8601",
  "structured_market_state": { "...full Layer 1 output..." },
  "prompt_sent": "...full prompt string...",
  "llm_response_raw": "...raw JSON string...",
  "validation_result": {
    "passed": true,
    "checks": {
      "rr": { "ok": true, "value": 1.85 },
      "sl_beyond_sweep": { "ok": true },
      "tp_at_intact_liquidity": { "ok": true },
      "max_positions": { "ok": true },
      "direction_vs_bias": { "ok": true }
    }
  },
  "final_decision": "BUY|SELL|CLOSE|HOLD|WAIT",
  "rejection_reason": null
}
```

---

## Testing Strategy

Unit tests in `tests/test_market_structure.py` with **synthetic candle fixtures** (no MT4, no LLM):

- Fixture with known swing highs/lows → assert exact prices and labels
- Fixture with a clear CHoCH → assert `last_choch` is populated, `last_bos` is correct
- Fixture with equal highs within tolerance → assert `equal_highs` pool with `strength=2`
- Fixture with a confirmed sweep → assert `confirmed: true` and pool marked `swept`
- Fixture with a bullish FVG → assert `top`, `bottom`, `midpoint` are correct
- Fixture with a bullish OB before a displacement → assert OB range matches the last bearish candle
- Edge case: fewer candles than N for fractal → assert empty output, no crash
- Edge case: all candles same price (ranging) → assert `state == "ranging"`
