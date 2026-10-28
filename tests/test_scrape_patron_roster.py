"""Patron roster scrape code/label mapping (emmotes Oct 2026 shape)."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

_SCRIPT = (
    Path(__file__).resolve().parent.parent / "scripts" / "scrape_patron_roster.py"
)
_SPEC = importlib.util.spec_from_file_location("scrape_patron_roster", _SCRIPT)
assert _SPEC and _SPEC.loader
_SCRAPE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_SCRAPE)
_availability = _SCRAPE._availability
availability_from_label = _SCRAPE.availability_from_label
scrape = _SCRAPE.scrape


class ScrapePatronRosterTests(unittest.TestCase):
    def test_code_fallbacks_match_live_emmotes(self) -> None:
        self.assertEqual(_availability(0), "unavailable")
        self.assertEqual(_availability(339), "available")
        self.assertEqual(_availability(340), "always")
        self.assertEqual(_availability(337), "feat")
        self.assertEqual(_availability(338), "ability")
        self.assertEqual(_availability(336), "ability_feat")
        self.assertEqual(_availability(1), "sometimes")
        # 331 used to mean feat; on the live page it is an Until-date code.
        self.assertEqual(_availability(331), "timed")

    def test_labels_override_codes(self) -> None:
        self.assertEqual(
            availability_from_label("Until 2029-08-04", 321), "timed"
        )
        self.assertEqual(availability_from_label("w/ Feats", 337), "feat")
        self.assertEqual(availability_from_label("Always", 340), "always")
        self.assertEqual(availability_from_label("Ability", 338), "ability")
        self.assertEqual(
            availability_from_label("Ability w/ Fts", 336), "ability_feat"
        )
        # Empty checkmark with available code.
        self.assertEqual(availability_from_label("", 339), "available")
        self.assertEqual(availability_from_label("", 0), "unavailable")

    def test_scrape_jim_elminster_timed_from_fixture_html(self) -> None:
        # Minimal 17-span Jim row matching live layout.
        sort = "47,69,85,0,0,339,337,321"
        cells = [
            ("patronRosterBorderLeft", ""),
            ("patronRosterRight", "48"),
            ("", "&nbsp;"),
            ("patronRosterLeft", "Jim"),
            ("", "&nbsp;"),
            ("patronRosterRight", "7"),
            ("", "&nbsp;"),
            ("patronRosterLeft", ""),  # mirt
            ("", "&nbsp;"),
            ("patronRosterLeft", ""),  # vajra
            ("", "&nbsp;"),
            ("patronRosterLeft", ""),  # strahd checkmark
            ("", "&nbsp;"),
            ("patronRosterLeft", "w/ Feats"),  # zariel
            ("", "&nbsp;"),
            ("patronRosterLeft", "Until 2029-08-04"),  # elminster
            ("patronRosterBorderRight", ""),
        ]
        parts = []
        for cls, text in cells:
            class_attr = f"patronRosterItem {cls}".strip()
            parts.append(
                f'<span class="{class_attr}" data-sort="{sort}">{text}</span>'
            )
        html = "\n".join(parts)
        data = scrape(html)
        jim = next(h for h in data["heroes"] if h["hero_id"] == 48)
        self.assertEqual(
            jim["patrons"],
            {
                "mirt": "unavailable",
                "vajra": "unavailable",
                "strahd": "available",
                "zariel": "feat",
                "elminster": "timed",
            },
        )


if __name__ == "__main__":
    unittest.main()
