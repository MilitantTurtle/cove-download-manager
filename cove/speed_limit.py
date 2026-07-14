"""Speed-limiter display units and conversion helpers."""

from __future__ import annotations

from PySide6.QtWidgets import QDoubleSpinBox

KB_PER_MB = 1024
SPEED_LIMIT_UNITS = ("KB/s", "MB/s")


def normalize_speed_unit(unit: str) -> str:
    return unit if unit in SPEED_LIMIT_UNITS else SPEED_LIMIT_UNITS[0]


def speed_value_from_kbps(kbps: int, unit: str) -> float:
    value = max(0, int(kbps))
    return value / KB_PER_MB if normalize_speed_unit(unit) == "MB/s" else float(value)


def speed_value_to_kbps(value: float, unit: str) -> int:
    multiplier = KB_PER_MB if normalize_speed_unit(unit) == "MB/s" else 1
    return max(0, round(float(value) * multiplier))


def configure_speed_spin(spin: QDoubleSpinBox, unit: str, kbps: int) -> None:
    """Configure a speed spin box without emitting a synthetic value change."""
    previous = spin.blockSignals(True)
    try:
        if normalize_speed_unit(unit) == "MB/s":
            spin.setDecimals(2)
            spin.setRange(0, 1000)
            spin.setSingleStep(0.25)
        else:
            spin.setDecimals(0)
            spin.setRange(0, 1_000_000)
            spin.setSingleStep(1)
        spin.setSpecialValueText("Unlimited")
        spin.setValue(speed_value_from_kbps(kbps, unit))
    finally:
        spin.blockSignals(previous)
