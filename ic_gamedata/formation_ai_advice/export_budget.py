"""Character/byte budget for compact advice clipboard exports.

Counting rules (used everywhere — preview, counter, clipboard):
- ``count_chars`` = number of Unicode code points in the Python ``str``
  (``len(text)``). Newlines count as one character each (``\\n``).
- ``count_utf8_bytes`` = UTF-8 encoded byte length of the same string.
- The configured maximum applies to the **entire** clipboard string:
  instructions, headers, fences, and JSON.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_CHAR_BUDGET = 15_000
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
            f"{self.chars:,} tekens · {self.utf8_bytes:,} bytes · "
            f"max {self.max_chars:,} · {status}"
        ).replace(",", ".")


def budget_status(text: str, max_chars: int) -> BudgetStatus:
    """Evaluate ``text`` against ``max_chars`` (no silent truncation).

    Does not clamp the limit here — callers that read user prefs should use
    ``clamp_char_budget`` before passing the value (UI spinbox / settings).
    """
    chars = count_chars(text)
    try:
        limit = int(max_chars)
    except (TypeError, ValueError):
        limit = DEFAULT_CHAR_BUDGET
    if limit < 1:
        limit = 1
    over = max(0, chars - limit)
    return BudgetStatus(
        chars=chars,
        utf8_bytes=count_utf8_bytes(text),
        max_chars=limit,
        within_budget=chars <= limit,
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
