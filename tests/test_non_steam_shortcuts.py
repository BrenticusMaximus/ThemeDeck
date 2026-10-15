"""Tests for the non-Steam shortcut helpers in main.py.

Run with: python3 -m unittest discover -s tests
"""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

# main.py imports the `decky` module that only exists inside Decky Loader.
sys.modules.setdefault("decky", types.ModuleType("decky"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main  # noqa: E402


def _string(key: str, value: str) -> bytes:
    return b"\x01" + key.encode() + b"\x00" + value.encode() + b"\x00"


def _int32(key: str, value: int) -> bytes:
    return b"\x02" + key.encode() + b"\x00" + value.to_bytes(4, "little", signed=True)


def _map(key: str, body: bytes) -> bytes:
    return b"\x00" + key.encode() + b"\x00" + body + b"\x08"


def _shortcut(index: int, app_id: int, name: str, key_case: str = "appid") -> bytes:
    body = (
        _int32(key_case, app_id)
        + _string("AppName", name)
        + _string("Exe", '"/usr/bin/true"')
        + _int32("IsHidden", 0)
        + _map("tags", _string("0", "favorite"))
    )
    return _map(str(index), body)


def _shortcuts_vdf(*entries: bytes) -> bytes:
    return _map("shortcuts", b"".join(entries)) + b"\x08"


class ExtractShortcutsTest(unittest.TestCase):
    def test_reads_names_and_unsigned_app_ids(self) -> None:
        data = _shortcuts_vdf(
            # 3934190733 stored as a signed int32
            _shortcut(0, 3934190733 - 2**32, "Battle.net"),
            _shortcut(1, -1234567890, "Diablo IV", key_case="appID"),
        )
        self.assertEqual(
            main.extract_non_steam_shortcuts(data),
            [
                {"appid": 3934190733, "name": "Battle.net"},
                {"appid": 3060399406, "name": "Diablo IV"},
            ],
        )

    def test_skips_entries_without_name_or_app_id(self) -> None:
        data = _shortcuts_vdf(
            _map("0", _string("AppName", "No ID")),
            _shortcut(1, -5, ""),
            _shortcut(2, -6, "Hades"),
        )
        self.assertEqual(
            main.extract_non_steam_shortcuts(data),
            [{"appid": 2**32 - 6, "name": "Hades"}],
        )

    def test_empty_file(self) -> None:
        self.assertEqual(main.extract_non_steam_shortcuts(_shortcuts_vdf()), [])

    def test_rejects_unknown_types(self) -> None:
        with self.assertRaises(ValueError):
            main.parse_binary_vdf(b"\x09bad\x00")


class CleanSearchNameTest(unittest.TestCase):
    def test_strips_tags_and_trademarks(self) -> None:
        cases = {
            "Super Mario World (USA)": "Super Mario World",
            "Chrono Trigger (USA) [!]": "Chrono Trigger",
            "The Witcher 3 [GOG]": "The Witcher 3",
            "Assassin's Creed® Valhalla™": "Assassin's Creed Valhalla",
            "  Hades  -  ": "Hades",
            "(Untitled)": "(Untitled)",
            "Batman: Arkham Knight": "Batman: Arkham Knight",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(main.clean_game_search_name(raw), expected)


class LauncherDetectionTest(unittest.TestCase):
    def test_launchers_are_detected(self) -> None:
        for name in (
            "Battle.net",
            "EA App",
            "Repair EA App",
            "Ubisoft Connect",
            "Rockstar Games Launcher",
            "Epic Games",
            "GOG Galaxy",
            "itch.io",
            "STOVE Client",
            "Some New Launcher",
            "Google Chrome",
            "Heroic Games Launcher",
            # Spaceless names written by shortcut tools (NonSteamLaunchers).
            "EAapp",
            "RockstarGamesLauncher",
            "UbisoftConnectx",
            "NonSteamLaunchers",
        ):
            with self.subTest(name=name):
                self.assertTrue(main.is_launcher_shortcut_name(name))

    def test_games_are_not_launchers(self) -> None:
        for name in (
            "Diablo IV",
            "Assassin's Creed Valhalla",
            "Red Dead Redemption 2",
            "Hollow Knight",
            "Cyberpunk 2077 (GOG)",
            "Anno117",
            "Anno 117 - Pax Romana",
            "Disney's Hercules",
            "Mafia Classic",
            "Metro Exodus Enhanced Edition",
            "Prehistorik 2",
            "Prince of Persia The Lost Crown",
            "Red Dead Redemption II",
            "Starcraft II",
            "Worms World Party Remastered",
            "Origins of Madness",
            "Battlefield 6",
            "EA Sports FC 26",
        ):
            with self.subTest(name=name):
                self.assertFalse(main.is_launcher_shortcut_name(name))


if __name__ == "__main__":
    unittest.main()
