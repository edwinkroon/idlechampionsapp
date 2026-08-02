"""Deprecated tkinter GUI entrypoint — use app_launcher.py instead."""

from __future__ import annotations

import sys


def main() -> int:
    print(
        "idle_champions_automation.py is deprecated.\n"
        "Start the app with: python app_launcher.py\n"
        "The old tkinter GUI is preserved in legacy/idle_champions_automation_tk.py",
        file=sys.stderr,
    )
    try:
        from app_launcher import main as launch
    except ImportError:
        return 1
    return launch()


if __name__ == "__main__":
    sys.exit(main())
