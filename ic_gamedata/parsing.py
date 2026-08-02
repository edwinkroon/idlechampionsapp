"""Shared parsing helpers for game JSON and CSV values."""

from __future__ import annotations

from typing import Any


def parse_number(value: Any) -> float | None:
    """Parse a numeric value from game data; rejects bool and empty strings."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def parse_int(value: Any) -> int | None:
    """Parse an integer from game data; rejects bool and empty strings."""
    num = parse_number(value)
    if num is None:
        return None
    return int(num)
