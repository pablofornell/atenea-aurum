"""Tests for AurumAgent._trading_session() — session label logic with minute precision.

Covers the exact Kill Zone windows used by the EA indicator:
  London Kill Zone : 07:00–08:30 UTC
  NY Kill Zone     : 13:30–15:00 UTC
  London Active    : 08:30–13:30 UTC
  NY Active        : 15:00–22:00 UTC
  Asia             : 00:00–07:00 UTC
  Late NY          : 22:00–00:00 UTC
"""
import pytest
from src.agent.agent import AurumAgent


def ts(hh, mm, ss=0):
    """Build a fake server_time string for UTC time."""
    return f"2026.04.24 {hh:02d}:{mm:02d}:{ss:02d}"


# ---------------------------------------------------------------------------
# London Kill Zone  07:00–08:29 UTC
# ---------------------------------------------------------------------------

class TestLondonKillZone:

    def test_start_of_london_kz(self):
        assert AurumAgent._trading_session(ts(7, 0)) == "London Kill Zone"

    def test_middle_of_london_kz(self):
        assert AurumAgent._trading_session(ts(7, 45)) == "London Kill Zone"

    def test_just_before_london_kz_end(self):
        assert AurumAgent._trading_session(ts(8, 29)) == "London Kill Zone"

    def test_london_kz_boundary_8_30(self):
        # 08:30 is the first minute of London Active, NOT Kill Zone
        assert AurumAgent._trading_session(ts(8, 30)) == "London Active"


# ---------------------------------------------------------------------------
# NY Kill Zone  13:30–14:59 UTC
# ---------------------------------------------------------------------------

class TestNYKillZone:

    def test_start_of_ny_kz(self):
        assert AurumAgent._trading_session(ts(13, 30)) == "NY Kill Zone"

    def test_middle_of_ny_kz(self):
        assert AurumAgent._trading_session(ts(14, 0)) == "NY Kill Zone"

    def test_just_before_ny_kz_end(self):
        assert AurumAgent._trading_session(ts(14, 59)) == "NY Kill Zone"

    def test_just_before_ny_kz_start(self):
        # 13:29 is still London Active
        assert AurumAgent._trading_session(ts(13, 29)) == "London Active"

    def test_ny_kz_boundary_15_00(self):
        # 15:00 is the first minute of NY Active
        assert AurumAgent._trading_session(ts(15, 0)) == "NY Active"


# ---------------------------------------------------------------------------
# London Active  08:30–13:29 UTC
# ---------------------------------------------------------------------------

class TestLondonActive:

    def test_start_of_london_active(self):
        assert AurumAgent._trading_session(ts(8, 30)) == "London Active"

    def test_mid_london_active(self):
        assert AurumAgent._trading_session(ts(10, 0)) == "London Active"

    def test_end_of_london_active(self):
        assert AurumAgent._trading_session(ts(13, 29)) == "London Active"


# ---------------------------------------------------------------------------
# NY Active  15:00–21:59 UTC
# ---------------------------------------------------------------------------

class TestNYActive:

    def test_start_of_ny_active(self):
        assert AurumAgent._trading_session(ts(15, 0)) == "NY Active"

    def test_mid_ny_active(self):
        assert AurumAgent._trading_session(ts(18, 30)) == "NY Active"

    def test_end_of_ny_active(self):
        assert AurumAgent._trading_session(ts(21, 59)) == "NY Active"

    def test_ny_active_boundary_22_00(self):
        assert AurumAgent._trading_session(ts(22, 0)) == "Late NY"


# ---------------------------------------------------------------------------
# Asia  00:00–06:59 UTC
# ---------------------------------------------------------------------------

class TestAsia:

    def test_midnight(self):
        assert AurumAgent._trading_session(ts(0, 0)) == "Asia"

    def test_middle_of_asia(self):
        assert AurumAgent._trading_session(ts(3, 30)) == "Asia"

    def test_end_of_asia(self):
        assert AurumAgent._trading_session(ts(6, 59)) == "Asia"

    def test_asia_boundary_7_00(self):
        assert AurumAgent._trading_session(ts(7, 0)) == "London Kill Zone"


# ---------------------------------------------------------------------------
# Late NY  22:00–23:59 UTC
# ---------------------------------------------------------------------------

class TestLateNY:

    def test_start_of_late_ny(self):
        assert AurumAgent._trading_session(ts(22, 0)) == "Late NY"

    def test_mid_late_ny(self):
        assert AurumAgent._trading_session(ts(23, 0)) == "Late NY"

    def test_end_of_late_ny(self):
        assert AurumAgent._trading_session(ts(23, 59)) == "Late NY"


# ---------------------------------------------------------------------------
# broker_gmt_offset — UTC+2 (common EET broker)
# ---------------------------------------------------------------------------

class TestBrokerGMTOffset:

    def test_broker_utc2_london_kz_at_server_09_00(self):
        # Server time 09:00 with GMT+2 offset → UTC 07:00 → London Kill Zone
        assert AurumAgent._trading_session(ts(9, 0), broker_gmt_offset=2) == "London Kill Zone"

    def test_broker_utc2_london_kz_at_server_10_29(self):
        # Server 10:29 with GMT+2 → UTC 08:29 → still London Kill Zone
        assert AurumAgent._trading_session(ts(10, 29), broker_gmt_offset=2) == "London Kill Zone"

    def test_broker_utc2_london_active_at_server_10_30(self):
        # Server 10:30 with GMT+2 → UTC 08:30 → London Active
        assert AurumAgent._trading_session(ts(10, 30), broker_gmt_offset=2) == "London Active"

    def test_broker_utc2_ny_kz_at_server_15_30(self):
        # Server 15:30 with GMT+2 → UTC 13:30 → NY Kill Zone
        assert AurumAgent._trading_session(ts(15, 30), broker_gmt_offset=2) == "NY Kill Zone"

    def test_broker_utc2_asia_at_server_02_00(self):
        # Server 02:00 with GMT+2 → UTC 00:00 → Asia
        assert AurumAgent._trading_session(ts(2, 0), broker_gmt_offset=2) == "Asia"


# ---------------------------------------------------------------------------
# Cycle interval logic
# ---------------------------------------------------------------------------

class TestSessionIntervalMapping:
    """Ensure Kill Zone labels drive 5-min cycles and Active labels drive 10-min cycles."""

    KILL_ZONE_LABELS = ["London Kill Zone", "NY Kill Zone"]
    ACTIVE_LABELS = ["London Active", "NY Active"]
    INACTIVE_LABELS = ["Asia", "Late NY"]

    def test_kill_zone_label_contains_kill_zone(self):
        for label in self.KILL_ZONE_LABELS:
            assert "Kill Zone" in label, f"'{label}' must contain 'Kill Zone'"

    def test_active_label_contains_active(self):
        for label in self.ACTIVE_LABELS:
            assert "Active" in label, f"'{label}' must contain 'Active'"

    def test_inactive_labels_contain_neither(self):
        for label in self.INACTIVE_LABELS:
            assert "Kill Zone" not in label
            assert "Active" not in label

    def test_all_hours_return_known_label(self):
        known = {"London Kill Zone", "NY Kill Zone", "London Active", "NY Active", "Asia", "Late NY"}
        for hour in range(24):
            for minute in (0, 15, 30, 45):
                label = AurumAgent._trading_session(ts(hour, minute))
                assert label in known, f"Unexpected label '{label}' at {hour:02d}:{minute:02d}"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_empty_string_returns_unknown(self):
        assert AurumAgent._trading_session("") == "Unknown"

    def test_none_returns_unknown(self):
        assert AurumAgent._trading_session(None) == "Unknown"

    def test_malformed_string_returns_unknown(self):
        assert AurumAgent._trading_session("not-a-time") == "Unknown"
