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

def test_zero_balance_gives_zero():
    assert _progressive_lots(0.0, 100) == pytest.approx(0.00)
