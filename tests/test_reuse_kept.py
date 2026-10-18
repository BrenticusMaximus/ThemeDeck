"""Tests for reusing kept downloads before searching again.

Run with: python3 -m unittest discover -s tests
"""

from __future__ import annotations

import asyncio
import logging
import os
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

GAME = 3321460


class ReuseKeptTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        settings = Path(self.tmp.name) / "settings"
        settings.mkdir()
        plugin = main.Plugin.__new__(main.Plugin)
        plugin._settings_dir = settings
        plugin._downloads_dir = settings / "downloads"
        plugin._preview_dir = settings / "previews"
        plugin._global_track_key = "__global__"
        plugin._store_track_key = "__store__"
        plugin._tracks = {}
        plugin._save_tracks = lambda: None
        plugin._log_info = lambda message: None
        plugin._log_warning = lambda message: None
        self.plugin = plugin

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def download(self, name: str, source: str | None, age: int = 0) -> Path:
        path = self.plugin._downloads_dir / str(GAME) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
        stamp = 1_700_000_000 - age
        os.utime(path, (stamp, stamp))
        if source:
            self.plugin._record_download(
                path, app_id=GAME, youtube_id=name[-16:-5], source=source
            )
            index = self.plugin._read_downloads_index()
            index[self.plugin._index_key(path)]["downloaded_at"] = stamp
            self.plugin._write_downloads_index(index)
        return path

    def run_async(self, coro):
        return asyncio.run(coro)

    def test_reattach_prefers_hand_picked(self) -> None:
        self.download("Auto_Pick [aaaaaaaaaaa].mp3", "auto", age=0)
        manual = self.download("My_Pick [bbbbbbbbbbb].mp3", "manual", age=100)
        result = self.run_async(self.plugin.reattach_kept_track(GAME))
        self.assertEqual(result["path"], str(manual))
        self.assertEqual(result["source"], "manual")
        self.assertEqual(self.plugin._tracks[str(GAME)]["youtube_id"], "bbbbbbbbbbb")

    def test_reattach_newest_auto_pick(self) -> None:
        self.download("Old [aaaaaaaaaaa].mp3", "auto", age=500)
        newer = self.download("New [ccccccccccc].mp3", "auto", age=10)
        self.assertEqual(self.run_async(self.plugin.reattach_kept_track(GAME))["path"], str(newer))

    def test_legacy_files_without_index_are_reused(self) -> None:
        legacy = self.download("Legacy [ddddddddddd].mp3", None)
        result = self.run_async(self.plugin.reattach_kept_track(GAME))
        self.assertEqual(result["path"], str(legacy))
        self.assertEqual(result["source"], "auto")

    def test_nothing_kept_or_already_assigned(self) -> None:
        self.assertEqual(
            self.run_async(self.plugin.reattach_kept_track(GAME))["reason"], "none_kept"
        )
        path = self.download("Song [aaaaaaaaaaa].mp3", "auto")
        self.run_async(self.plugin.set_track(GAME, str(path), path.name))
        self.assertEqual(
            self.run_async(self.plugin.reattach_kept_track(GAME))["reason"], "has_track"
        )

    def test_removed_song_can_be_reattached(self) -> None:
        # A removed song whose file was kept is reused next time.
        path = self.download("Song [aaaaaaaaaaa].mp3", "manual")
        self.run_async(self.plugin.set_track(GAME, str(path), path.name))
        self.run_async(self.plugin.remove_track(GAME))
        self.assertEqual(self.run_async(self.plugin.reattach_kept_track(GAME))["path"], str(path))



if __name__ == "__main__":
    unittest.main()
