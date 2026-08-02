"""Tests for game install path discovery."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ic_gamedata.paths import (
    EPIC_APP_NAME,
    InstallSource,
    find_epic_install,
    find_game_install,
)


class EpicPathTests(unittest.TestCase):
    def test_find_epic_install_by_app_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            game_dir = Path(tmp) / "IdleChampions"
            game_dir.mkdir()
            (game_dir / "IdleChampions.exe").write_text("", encoding="utf-8")
            (game_dir / "IdleDragons_Data").mkdir()

            payload = {
                "InstallationList": [
                    {
                        "InstallLocation": str(game_dir),
                        "AppName": EPIC_APP_NAME,
                    }
                ]
            }
            launcher_dir = Path(tmp) / "Epic" / "UnrealEngineLauncher"
            launcher_dir.mkdir(parents=True)
            launcher_file = launcher_dir / "LauncherInstalled.dat"
            launcher_file.write_text(json.dumps(payload), encoding="utf-8")

            with patch.dict("os.environ", {"ProgramData": tmp}, clear=False):
                found = find_epic_install()
            self.assertEqual(found, game_dir.resolve())

    def test_find_epic_install_folder_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            game_dir = Path(tmp) / "games" / "IdleChampions"
            game_dir.mkdir(parents=True)
            (game_dir / "IdleChampions.exe").write_text("", encoding="utf-8")
            (game_dir / "IdleDragons_Data").mkdir()

            payload = {
                "InstallationList": [
                    {
                        "InstallLocation": str(game_dir),
                        "AppName": "other-app-id",
                    }
                ]
            }
            launcher_dir = Path(tmp) / "Epic" / "UnrealEngineLauncher"
            launcher_dir.mkdir(parents=True)
            (launcher_dir / "LauncherInstalled.dat").write_text(
                json.dumps(payload), encoding="utf-8"
            )

            with patch.dict("os.environ", {"ProgramData": tmp}, clear=False):
                found = find_epic_install()
            self.assertEqual(found, game_dir.resolve())

    def test_manual_override_wins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manual = Path(tmp) / "IdleChampions"
            manual.mkdir()
            (manual / "IdleChampions.exe").write_text("", encoding="utf-8")
            (manual / "IdleDragons_Data").mkdir()

            config_dir = Path(tmp) / "config"
            config_dir.mkdir()
            (config_dir / "gamedata.json").write_text(
                json.dumps({"install_path": str(manual)}),
                encoding="utf-8",
            )

            with patch("ic_gamedata.paths.GAMEDATA_CONFIG_PATH", config_dir / "gamedata.json"):
                info = find_game_install()
            self.assertIsNotNone(info)
            assert info is not None
            self.assertEqual(info.install_dir, manual.resolve())
            self.assertEqual(info.source, InstallSource.MANUAL)


if __name__ == "__main__":
    unittest.main()
