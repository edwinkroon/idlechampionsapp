"""Single-instance: new start closes other companion processes."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from ic_ui.single_instance import (
    close_other_instances,
    is_companion_process,
    iter_other_companion_pids,
)


class SingleInstanceTests(unittest.TestCase):
    def test_detects_frozen_exe_name(self) -> None:
        self.assertTrue(
            is_companion_process(
                {"pid": 1, "name": "IdleChampionsApp.exe", "cmdline": []},
            )
        )
        self.assertFalse(
            is_companion_process(
                {"pid": 1, "name": "python.exe", "cmdline": ["python", "other.py"]},
            )
        )
        # Starting from python still recognizes a leftover frozen exe.
        self.assertTrue(
            is_companion_process(
                {"pid": 1, "name": "IdleChampionsApp.exe", "cmdline": None},
                frozen=False,
            )
        )

    def test_detects_dev_app_launcher_cmdline(self) -> None:
        self.assertTrue(
            is_companion_process(
                {
                    "pid": 2,
                    "name": "pythonw.exe",
                    "cmdline": [
                        r"C:\Python\pythonw.exe",
                        r"C:\CursorFiles\Idle champions\app_launcher.py",
                    ],
                },
                frozen=False,
            )
        )
        self.assertFalse(
            is_companion_process(
                {
                    "pid": 3,
                    "name": "python.exe",
                    "cmdline": ["python", "scripts/scrape_patron_roster.py"],
                },
                frozen=False,
            )
        )

    def test_iter_skips_self(self) -> None:
        peers = [
            MagicMock(
                as_dict=MagicMock(
                    return_value={
                        "pid": 10,
                        "name": "pythonw.exe",
                        "cmdline": ["pythonw", "app_launcher.py"],
                    }
                )
            ),
            MagicMock(
                as_dict=MagicMock(
                    return_value={
                        "pid": 99,
                        "name": "pythonw.exe",
                        "cmdline": ["pythonw", "app_launcher.py"],
                    }
                )
            ),
        ]
        pids = iter_other_companion_pids(
            current_pid=99, process_iter=lambda _attrs: peers
        )
        self.assertEqual(pids, [10])

    def test_close_other_instances_terminates_peers_not_self(self) -> None:
        peer = MagicMock()
        # terminate path: alive once, then gone (extra calls stay False).
        peer.is_running.side_effect = [True, False, False, False]
        peer.terminate = MagicMock()
        peer.kill = MagicMock()

        def factory(pid: int):
            self.assertEqual(pid, 10)
            return peer

        peers = [
            MagicMock(
                as_dict=MagicMock(
                    return_value={
                        "pid": 10,
                        "name": "IdleChampionsApp.exe",
                        "cmdline": [],
                    }
                )
            ),
            MagicMock(
                as_dict=MagicMock(
                    return_value={
                        "pid": 99,
                        "name": "IdleChampionsApp.exe",
                        "cmdline": [],
                    }
                )
            ),
        ]
        # Force frozen matching via name; process_iter path uses is_companion
        # with sys.frozen — patch via cmdline for frozen=False instead:
        peers[0].as_dict.return_value = {
            "pid": 10,
            "name": "pythonw.exe",
            "cmdline": ["pythonw", "app_launcher.py"],
        }
        peers[1].as_dict.return_value = {
            "pid": 99,
            "name": "pythonw.exe",
            "cmdline": ["pythonw", "app_launcher.py"],
        }

        closed = close_other_instances(
            current_pid=99,
            wait_s=0.2,
            process_iter=lambda _attrs: peers,
            process_factory=factory,
        )
        self.assertEqual(closed, [10])
        peer.terminate.assert_called_once()
        peer.kill.assert_not_called()


if __name__ == "__main__":
    unittest.main()
