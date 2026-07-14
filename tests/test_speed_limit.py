"""Tests for speed-limiter display units."""

import pytest

from cove.speed_limit import speed_value_from_kbps, speed_value_to_kbps


@pytest.mark.parametrize(
    ("kbps", "unit", "display"),
    [
        (0, "KB/s", 0),
        (1536, "KB/s", 1536),
        (1536, "MB/s", 1.5),
    ],
)
def test_speed_value_from_kbps(kbps, unit, display):
    assert speed_value_from_kbps(kbps, unit) == display


@pytest.mark.parametrize(
    ("display", "unit", "kbps"),
    [
        (0, "KB/s", 0),
        (1536, "KB/s", 1536),
        (1.5, "MB/s", 1536),
        (2.25, "MB/s", 2304),
    ],
)
def test_speed_value_to_kbps(display, unit, kbps):
    assert speed_value_to_kbps(display, unit) == kbps
