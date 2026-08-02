from __future__ import annotations

import os
import sys


def main() -> int:
    # Some Windows setups already lock DPI context before Qt starts.
    os.environ.setdefault("QT_QPA_PLATFORM", "windows:dpiawareness=1")
    try:
        from ic_ui.pyside_app import run_pyside_app
    except ImportError as exc:
        print(
            "PySide6 kon niet worden geladen.\n"
            "Installeer dependencies met: pip install -r requirements.txt",
            file=sys.stderr,
        )
        print(f"Details: {exc}", file=sys.stderr)
        return 1
    try:
        return run_pyside_app()
    except Exception as exc:
        print(f"De app kon niet starten: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
