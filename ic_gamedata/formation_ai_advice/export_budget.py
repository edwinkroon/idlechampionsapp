"""Character/byte budget for compact advice clipboard exports.

Counting rules (used everywhere — preview, counter, clipboard):
- ``count_chars`` = number of Unicode code points in the Python ``str``
  (``len(text)``). Newlines count as one character each (``\\n``).
- ``count_utf8_bytes`` = UTF-8 encoded byte length of the same string.
- ``MAX_EXPORT_BYTES`` is the hard UTF-8 byte limit on the **entire**
  clipboard string: instructions, headers, fences, and JSON.
- ``DEFAULT_CHAR_BUDGET`` is an alias of ``MAX_EXPORT_BYTES`` (historical name
  kept for call sites that still pass ``max_chars``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Hard ceiling for the full ADVICE_REQUEST clipboard payload (UTF-8 bytes).
MAX_EXPORT_BYTES = 17_000
# Soft target with reserve under the hard ceiling.
TARGET_EXPORT_BYTES = 16_000
# Historical alias — same hard gate as MAX_EXPORT_BYTES.
DEFAULT_CHAR_BUDGET = MAX_EXPORT_BYTES
MIN_CHAR_BUDGET = 2_000
MAX_CHAR_BUDGET = 500_000


def count_chars(text: str) -> int:
    """Unicode code-point count (same as Python ``len`` on ``str``)."""
    return len(text)


def count_utf8_bytes(text: str) -> int:
    """UTF-8 byte length of ``text``."""
    return len(text.encode("utf-8"))


def clamp_char_budget(value: int | float | None) -> int:
    try:
        n = int(value) if value is not None else DEFAULT_CHAR_BUDGET
    except (TypeError, ValueError):
        n = DEFAULT_CHAR_BUDGET
    return max(MIN_CHAR_BUDGET, min(MAX_CHAR_BUDGET, n))


@dataclass(frozen=True)
class BudgetStatus:
    chars: int
    utf8_bytes: int
    max_chars: int
    within_budget: bool
    over_by: int

    @property
    def label(self) -> str:
        status = "binnen budget" if self.within_budget else "boven budget"
        return (
            f"{self.chars:,} tekens · {self.utf8_bytes:,} UTF-8-bytes · "
            f"max {self.max_chars:,} bytes · {status}"
        ).replace(",", ".")


def budget_status(text: str, max_chars: int) -> BudgetStatus:
    """Evaluate ``text`` against the UTF-8 byte limit (no silent truncation).

    ``max_chars`` is the historical parameter name; the hard gate is
    ``utf8_bytes <= max_chars``. Callers that read user prefs should use
    ``clamp_char_budget`` before passing the value (UI spinbox / settings).
    """
    chars = count_chars(text)
    utf8 = count_utf8_bytes(text)
    try:
        limit = int(max_chars)
    except (TypeError, ValueError):
        limit = DEFAULT_CHAR_BUDGET
    if limit < 1:
        limit = 1
    over = max(0, utf8 - limit)
    return BudgetStatus(
        chars=chars,
        utf8_bytes=utf8,
        max_chars=limit,
        within_budget=utf8 <= limit,
        over_by=over,
    )


def section_sizes(sections: dict[str, str]) -> list[dict[str, Any]]:
    """Largest-first breakdown of named text sections."""
    rows: list[dict[str, Any]] = []
    for name, body in sections.items():
        if not isinstance(body, str):
            continue
        rows.append(
            {
                "name": name,
                "chars": count_chars(body),
                "utf8_bytes": count_utf8_bytes(body),
            }
        )
    rows.sort(key=lambda r: r["chars"], reverse=True)
    return rows
