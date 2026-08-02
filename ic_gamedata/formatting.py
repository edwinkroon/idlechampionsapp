"""Display formatting helpers for game values."""

from __future__ import annotations


def format_gold(value) -> str:
    """Format gold using scientific e notation (e.g. 1.234e+20)."""
    if value is None:
        return "—"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return "—"
    if num == 0:
        return "0"
    return f"{num:.4e}"
