"""Tests for the new-game detection used by "Download music for new games".

Run with: python3 -m unittest discover -s tests
"""

from __future__ import annotations

import logging
import sys
import tempfile
import types
import unittest
from pathlib import Path

# main.py imports the `decky` module that only exists inside Decky Loader.
decky = sys.modules.setdefault("decky", types.ModuleType("decky"))
decky.logger = logging.getLogger("decky-test")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main  # noqa: E402


class CheckNewGamesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.plugin = main.Plugin.__new__(main.Plugin)
        self.plugin._settings_dir = Path(self.tmp.name)
        self.plugin._log_info = lambda message: None
        self.plugin._log_warning = lambda message: None
        self.library: dict[int, str] = {}
        self.shortcuts: list[dict] = []
        self.plugin._read_steam_library_games = lambda: (
            [{"appid": app_id, "name": name} for app_id, name in self.library.items()],
            set(self.library),
        )
        self.plugin._read_non_steam_shortcuts = lambda: list(self.shortcuts)

    def shortcut(self, app_id: int, name: str, launcher: bool = False) -> dict:
        return {"appid": app_id, "name": name, "search_name": name, "launcher": launcher}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_first_run_only_records_library(self) -> None:
        self.library = {367520: "Hollow Knight", 1245620: "ELDEN RING"}
        result = self.plugin._check_new_games()
        self.assertTrue(result["first_run"])
        self.assertEqual(result["games"], [])
        self.assertEqual(self.plugin._check_new_games()["games"], [])

    def test_newly_installed_game_is_reported_once(self) -> None:
        self.library = {367520: "Hollow Knight"}
        self.plugin._check_new_games()
        self.library[3321460] = "Crimson Desert Enhanced"
        self.assertEqual(
            self.plugin._check_new_games()["games"],
            [{"appid": 3321460, "name": "Crimson Desert Enhanced"}],
        )
        self.assertEqual(self.plugin._check_new_games()["games"], [])

    def test_installing_an_owned_game_and_reinstalling_count_as_new(self) -> None:
        self.library = {367520: "Hollow Knight"}
        self.plugin._check_new_games()
        # An owned game gets installed.
        self.library[1245620] = "ELDEN RING"
        self.assertEqual(
            self.plugin._check_new_games()["games"],
            [{"appid": 1245620, "name": "ELDEN RING"}],
        )
        # Uninstalled, then installed again later.
        del self.library[1245620]
        self.assertEqual(self.plugin._check_new_games()["games"], [])
        self.library[1245620] = "ELDEN RING"
        self.assertEqual(
            self.plugin._check_new_games()["games"],
            [{"appid": 1245620, "name": "ELDEN RING"}],
        )

    def test_tools_and_runtimes_are_ignored(self) -> None:
        self.library = {367520: "Hollow Knight"}
        self.plugin._check_new_games()
        self.library.update(
            {
                2805730: "Proton 9.0",
                1493710: "Proton Experimental",
                1628350: "Steam Linux Runtime 3.0 (sniper)",
                228980: "Steamworks Common Redistributables",
                4242: "App 4242",
            }
        )
        self.assertEqual(self.plugin._check_new_games()["games"], [])

    def test_games_that_look_like_tools_are_kept(self) -> None:
        self.assertFalse(main.is_library_tool(1, "Prototype 2"))
        self.assertFalse(main.is_library_tool(1, "Protonmail Simulator"))
        self.assertTrue(main.is_library_tool(1, "Proton Hotfix"))

    def test_new_non_steam_shortcut_is_reported(self) -> None:
        self.shortcuts = [self.shortcut(2925064020, "Anno 117 - Pax Romana")]
        self.plugin._check_new_games()
        self.shortcuts.append(self.shortcut(3918230752, "Diablo IV"))
        self.shortcuts.append(self.shortcut(3934190733, "Battle.net", launcher=True))
        self.assertEqual(
            self.plugin._check_new_games()["games"],
            [{"appid": 3918230752, "name": "Diablo IV"}],
        )

    def test_upgrade_from_steam_only_file_records_shortcuts_first(self) -> None:
        # known-games.json written by the first version: a plain list of Steam IDs.
        (Path(self.tmp.name) / "known-games.json").write_text("[367520]")
        self.library = {367520: "Hollow Knight", 1245620: "ELDEN RING"}
        self.shortcuts = [self.shortcut(2925064020, "Anno 117 - Pax Romana")]
        result = self.plugin._check_new_games()
        self.assertFalse(result["first_run"])
        # The new Steam game is reported; existing shortcuts are only recorded.
        self.assertEqual(result["games"], [{"appid": 1245620, "name": "ELDEN RING"}])
        self.assertEqual(self.plugin._check_new_games()["games"], [])

    def test_exclusions_round_trip(self) -> None:
        import asyncio

        self.assertEqual(asyncio.run(self.plugin.get_auto_download_excluded()), [])
        asyncio.run(self.plugin.set_auto_download_excluded(42, True))
        asyncio.run(self.plugin.set_auto_download_excluded(7, True))
        self.assertEqual(asyncio.run(self.plugin.get_auto_download_excluded()), [7, 42])
        asyncio.run(self.plugin.set_auto_download_excluded(42, False))
        self.assertEqual(asyncio.run(self.plugin.get_auto_download_excluded()), [7])

    def test_corrupt_known_file_starts_fresh(self) -> None:
        (Path(self.tmp.name) / "known-games.json").write_text("not json")
        self.library = {367520: "Hollow Knight"}
        self.assertTrue(self.plugin._check_new_games()["first_run"])


if __name__ == "__main__":
    unittest.main()
