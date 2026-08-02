"""Tests for champion portrait resolution."""

from __future__ import annotations

import unittest
from pathlib import Path

from ic_gamedata.champion_portraits import (
    _resolve_graphic_png,
    champion_portrait_path,
)


class ChampionPortraitTests(unittest.TestCase):
    def test_resolve_graphic_png_prefers_exact_version(self) -> None:
        from tempfile import TemporaryDirectory

        graphic = {"graphic": "Portraits/Portrait_Bruenor", "fs": 0, "v": 7}
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            exact = root / "Portrait_Bruenor_0_7.png"
            exact.write_bytes(b"png")
            (root / "Portrait_Bruenor_0_5.png").write_bytes(b"png")
            self.assertEqual(_resolve_graphic_png(root, graphic), exact)

    def test_resolve_graphic_png_falls_back_to_other_version(self) -> None:
        from tempfile import TemporaryDirectory

        graphic = {"graphic": "Icons/Champions/Console/Portrait_Champion_Azaka", "fs": 0, "v": 6}
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            fallback = root / "Portrait_Champion_Azaka_0_5.png"
            fallback.write_bytes(b"png")
            self.assertEqual(_resolve_graphic_png(root, graphic), fallback)

    def test_champion_portrait_path_for_known_hero(self) -> None:
        from ic_gamedata.paths import find_game_install

        if find_game_install() is None:
            self.skipTest("game install not found")
        path = champion_portrait_path(1)
        if path is None:
            self.skipTest("portrait assets unavailable")
        self.assertTrue(path.is_file())
        self.assertTrue(path.name.lower().endswith(".png"))


if __name__ == "__main__":
    unittest.main()
