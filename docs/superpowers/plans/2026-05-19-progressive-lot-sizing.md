# Progressive Lot Sizing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace risk-based lot sizing (`MAX_RISK_PCT`) with a progressive system where every $100 of balance = 0.01 lot; `FIXED_LOTS` retains priority as manual override.

**Architecture:** Extract the balance→lots calculation into a private `_progressive_lots(balance, step)` helper in `executor.py` so it can be unit-tested without MT4. `config.py` gets `BALANCE_LOT_STEP = 100` and loses `MAX_RISK_PCT`. The existing `_snap_lots` call inside `_attempt_order` already clamps to broker min/max — no changes needed there.

**Tech Stack:** Python 3.13, pytest, `math.floor`

---

### Task 1: Write failing tests for progressive lot sizing

**Files:**
- Create: `tests/test_executor_lots.py`

- [ ] **Step 1: Create the test file**

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from risk.executor import _progressive_lots


def test_100_gives_001():
    assert _progressive_lots(100.0, 100) == pytest.approx(0.01)

def test_200_gives_002():
    assert _progressive_lots(200.0, 100) == pytest.approx(0.02)

def test_500_gives_005():
    assert _progressive_lots(500.0, 100) == pytest.approx(0.05)

def test_1000_gives_010():
    assert _progressive_lots(1000.0, 100) == pytest.approx(0.10)

def test_floor_on_partial_tranche():
    # $150 → floor(150/100) * 0.01 = 1 * 0.01 = 0.01
    assert _progressive_lots(150.0, 100) == pytest.approx(0.01)

def test_just_below_tranche():
    # $199 → floor(199/100) * 0.01 = 1 * 0.01 = 0.01
    assert _progressive_lots(199.0, 100) == pytest.approx(0.01)

def test_below_100_gives_zero():
    # Raw calculation; caller must clamp to broker min
    assert _progressive_lots(80.0, 100) == pytest.approx(0.00)

def test_custom_step():
    # With step=50: $150 → floor(150/50)*0.01 = 3*0.01 = 0.03
    assert _progressive_lots(150.0, 50) == pytest.approx(0.03)

def test_large_balance():
    assert _progressive_lots(5000.0, 100) == pytest.approx(0.50)
```

- [ ] **Step 2: Run tests to confirm they all fail**

```bash
cd /home/pablo/Documents/repos/atenea-aurum
python -m pytest tests/test_executor_lots.py -v
```

Expected: `ImportError` — `_progressive_lots` does not exist yet.

---

### Task 2: Add `_progressive_lots` helper to executor and update config

**Files:**
- Modify: `src/risk/executor.py`
- Modify: `src/config.py`

- [ ] **Step 1: Add `import math` and the helper to `executor.py`**

At the top of `src/risk/executor.py`, add `import math` after the existing imports:

```python
import math
import time

from bridge.mt4_client import MT4Client, MT4Error
```

Then add the helper after the `_DD_GUARD` constant (after line 9):

```python
def _progressive_lots(balance: float, step: int) -> float:
    """Return lots based on balance: every `step` dollars = 0.01 lot."""
    return math.floor(balance / step) * 0.01
```

- [ ] **Step 2: Replace the lot-sizing block inside `execute()`**

Find this block (around lines 187-192 of `src/risk/executor.py`):

```python
    # Lot sizing
    using_fixed_lots = getattr(cfg, "FIXED_LOTS", 0.0) > 0
    if using_fixed_lots:
        lots = cfg.FIXED_LOTS
    else:
        risk_amount = balance * (cfg.MAX_RISK_PCT / 100.0)
        lots = risk_amount / (sl_pips * _PIP_SIZE * 100)
```

Replace it with:

```python
    # Lot sizing
    using_fixed_lots = getattr(cfg, "FIXED_LOTS", 0.0) > 0
    if using_fixed_lots:
        lots = cfg.FIXED_LOTS
    else:
        step = getattr(cfg, "BALANCE_LOT_STEP", 100)
        lots = _progressive_lots(balance, step)
```

- [ ] **Step 3: Update `src/config.py`**

Remove:
```python
MAX_RISK_PCT          = 2    # % of balance per trade
```

Add in its place (under the `# Risk` comment block):
```python
BALANCE_LOT_STEP      = 100  # dollars per 0.01 lot (progressive sizing)
```

The `# Risk` block should look like:
```python
# Risk — NEVER delegated to the agent
BALANCE_LOT_STEP      = 100  # dollars per 0.01 lot (progressive sizing)
MAX_OPEN_TRADES       = 1    # max simultaneous positions
AUTO_CLOSE_PROFIT_PCT = 7.0  # close automatically when trade profit >= N% of balance (0 = disabled)
FIXED_LOTS            = 0.0  # if > 0, always use this lot size (overrides progressive sizing)
```

- [ ] **Step 4: Run tests — all should pass**

```bash
python -m pytest tests/test_executor_lots.py -v
```

Expected output:
```
tests/test_executor_lots.py::test_100_gives_001 PASSED
tests/test_executor_lots.py::test_200_gives_002 PASSED
tests/test_executor_lots.py::test_500_gives_005 PASSED
tests/test_executor_lots.py::test_1000_gives_010 PASSED
tests/test_executor_lots.py::test_floor_on_partial_tranche PASSED
tests/test_executor_lots.py::test_just_below_tranche PASSED
tests/test_executor_lots.py::test_below_100_gives_zero PASSED
tests/test_executor_lots.py::test_custom_step PASSED
tests/test_executor_lots.py::test_large_balance PASSED

9 passed
```

- [ ] **Step 5: Run the full test suite to check for regressions**

```bash
python -m pytest tests/ -v --ignore=tests/test_mt4_connection.py --ignore=tests/test_claude_binary.py
```

Expected: all existing tests pass (MT4 and Claude binary tests require live connections and are excluded).

- [ ] **Step 6: Commit**

```bash
git add tests/test_executor_lots.py src/risk/executor.py src/config.py
git commit -m "feat: replace risk-based lot sizing with progressive balance-based system

Every \$100 of balance = 0.01 lot (floor). FIXED_LOTS override preserved.
BALANCE_LOT_STEP=100 added to config; MAX_RISK_PCT removed."
```
