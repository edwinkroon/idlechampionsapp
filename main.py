#!/usr/bin/env python3
"""
CLI for read-only Idle Champions memory state (current area).

Examples:
  python main.py --watch-area
  python main.py --watch-area --interval 1 --debug
  python main.py --once --ui-hint 3
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from ic_reader.logging_utils import setup_logging
from ic_reader.resolver import create_resolver


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Read-only Idle Champions area reader (memory pointers)."
    )
    p.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to game_offsets.json (default: config/game_offsets.json)",
    )
    p.add_argument(
        "--watch-area",
        action="store_true",
        help="Poll current_area every --interval seconds; log only on change",
    )
    p.add_argument(
        "--once",
        action="store_true",
        help="Read current_area once and exit",
    )
    p.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Poll interval in seconds (default: 1)",
    )
    p.add_argument(
        "--ui-hint",
        type=int,
        default=None,
        help="Optional UI area number for candidate scoring (validation aid)",
    )
    p.add_argument(
        "--debug",
        action="store_true",
        help="Verbose logging: pointer steps and rejection reasons",
    )
    p.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="Log file path (default: logs/area_reader.log)",
    )
    return p.parse_args()


def format_area_result(resolved) -> str:
    if resolved.value is None:
        return "current_area: (unresolved — configure offsets in config/game_offsets.json)"
    return (
        f"current_area={resolved.value} "
        f"(candidate={resolved.candidate_id}, confidence={resolved.confidence:.1f})"
    )


def run_once(resolver, *, ui_hint: int | None) -> int:
    resolved = resolver.resolve_current_area(ui_hint_area=ui_hint)
    line = format_area_result(resolved)
    print(line)
    return 0 if resolved.value is not None else 2


def watch_area(resolver, *, interval: float, ui_hint: int | None, logger) -> int:
    logger.info("Watching current_area every %.1fs (Ctrl+C to stop)", interval)
    last_value = object()
    try:
        while True:
            resolved = resolver.resolve_current_area(ui_hint_area=ui_hint)
            value = resolved.value
            if value != last_value:
                line = format_area_result(resolved)
                print(line, flush=True)
                logger.info("CHANGE: %s", line)
                last_value = value
            time.sleep(interval)
    except KeyboardInterrupt:
        logger.info("Stopped by user")
        return 0


def main() -> int:
    args = parse_args()
    if not args.watch_area and not args.once:
        print("Specify --watch-area or --once", file=sys.stderr)
        return 1

    logger = setup_logging(log_path=args.log_file, debug=args.debug)
    try:
        resolver = create_resolver(args.config, debug=args.debug)
        with resolver:
            if args.once:
                return run_once(resolver, ui_hint=args.ui_hint)
            return watch_area(
                resolver,
                interval=args.interval,
                ui_hint=args.ui_hint,
                logger=logger,
            )
    except Exception as exc:
        logger.exception("Fatal: %s", exc)
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
