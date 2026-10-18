"""Tests for removing music from all games and cleaning up downloads.

Run with: python3 -m unittest discover -s tests
"""

from __future__ import annotations

import asyncio
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


class ManageMusicTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.settings = root / "settings"
        self.user_music = root / "Music"
        self.user_music.mkdir()
        self.settings.mkdir()

        plugin = main.Plugin.__new__(main.Plugin)
        plugin._settings_dir = self.settings
        plugin._downloads_dir = self.settings / "downloads"
        plugin._preview_dir = self.settings / "previews"
        plugin._global_track_key = "__global__"
        plugin._store_track_key = "__store__"
        plugin._save_tracks = lambda: None
        plugin._log_info = lambda message: None
        plugin._log_warning = lambda message: None
        plugin._tracks = {}
        self.plugin = plugin

        # game_a: auto-picked, game_b: hand-picked, orphan: unused auto pick,
        # kept_manual: unused hand-picked file.
        self.game_a = self.download(367520, "Hollow_Knight [aaaaaaaaaaa].mp3", 1000, "auto")
        self.game_b = self.download(1245620, "Elden_Ring [bbbbbbbbbbb].mp3", 2000, "manual")
        self.orphan = self.download(42, "Old_Pick [ccccccccccc].mp3", 500, "auto")
        self.kept_manual = self.download(43, "My_Pick [ddddddddddd].mp3", 250, "manual")
        self.preview = plugin._preview_dir / "preview.mp3"
        self.preview.parent.mkdir(parents=True)
        self.preview.write_bytes(b"p" * 300)
        self.local_song = self.user_music / "my_song.mp3"
        self.local_song.write_bytes(b"l" * 700)
        self.global_song = self.user_music / "ambient.mp3"
        self.global_song.write_bytes(b"g" * 400)

        plugin._tracks = {
            "367520": {"path": str(self.game_a)},
            "1245620": {"path": str(self.game_b)},
            "999": {"path": str(self.local_song)},  # user's own file
            "__global__": {"path": str(self.global_song)},
        }

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def download(self, app_id: int, name: str, size: int, source: str | None) -> Path:
        path = self.settings / "downloads" / str(app_id) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * size)
        if source:
            self.plugin._record_download(path, app_id=app_id, youtube_id=name[-16:-5], source=source)
        return path

    def test_storage_summary(self) -> None:
        storage = self.plugin._music_storage()
        self.assertEqual(storage["game_tracks"], 3)
        self.assertEqual(storage["downloaded_files"], 4)
        self.assertEqual(storage["downloaded_bytes"], 3750)
        self.assertEqual(storage["downloaded_auto_bytes"], 1500)
        self.assertEqual(storage["downloaded_manual_bytes"], 2250)
        self.assertEqual(storage["unused_auto_files"], 1)
        self.assertEqual(storage["unused_manual_files"], 1)
        self.assertEqual(storage["unused_bytes"], 750)

    def test_files_without_index_entry_count_as_auto(self) -> None:
        legacy = self.download(44, "Legacy [eeeeeeeeeee].mp3", 100, None)
        storage = self.plugin._music_storage()
        self.assertEqual(storage["unused_auto_files"], 2)
        asyncio.run(self.plugin.delete_unused_downloads("auto"))
        self.assertFalse(legacy.exists())

    def test_remove_all_keeps_files_with_none(self) -> None:
        response = asyncio.run(self.plugin.remove_all_game_tracks("none"))
        self.assertEqual(response["result"]["removed"], 3)
        self.assertEqual(set(self.plugin._tracks), {"__global__"})
        for path in (self.game_a, self.game_b, self.orphan, self.kept_manual):
            self.assertTrue(path.exists())

    def test_remove_all_and_delete_auto_keeps_hand_picked(self) -> None:
        result = asyncio.run(self.plugin.remove_all_game_tracks("auto"))["result"]
        self.assertEqual(result["deleted_files"], 2)
        self.assertFalse(self.game_a.exists() or self.orphan.exists())
        self.assertTrue(self.game_b.exists() and self.kept_manual.exists())
        # Deleted files leave the index; kept ones stay.
        index = self.plugin._read_downloads_index()
        self.assertEqual(sorted(entry["app_id"] for entry in index.values()), [43, 1245620])

    def test_remove_all_and_delete_everything(self) -> None:
        result = asyncio.run(self.plugin.remove_all_game_tracks("all"))["result"]
        self.assertEqual(result["deleted_files"], 4)
        self.assertEqual(result["freed_bytes"], 3750 + 300)
        for path in (self.game_a, self.game_b, self.orphan, self.kept_manual, self.preview):
            self.assertFalse(path.exists())
        # Never the user's own files, and the global track is kept.
        self.assertTrue(self.local_song.exists())
        self.assertTrue(self.global_song.exists())
        self.assertIn("__global__", self.plugin._tracks)

    def test_delete_unused_auto_only(self) -> None:
        result = asyncio.run(self.plugin.delete_unused_downloads("auto"))
        self.assertEqual(result, {"deleted_files": 1, "freed_bytes": 500})
        self.assertFalse(self.orphan.exists())
        self.assertTrue(self.kept_manual.exists())
        self.assertTrue(self.game_a.exists() and self.game_b.exists())
        self.assertTrue(self.preview.exists())

    def test_delete_unused_all(self) -> None:
        result = asyncio.run(self.plugin.delete_unused_downloads("all"))
        self.assertEqual(result, {"deleted_files": 2, "freed_bytes": 750})
        self.assertTrue(self.game_a.exists() and self.game_b.exists())
        self.assertEqual(len(self.plugin._tracks), 4)

    def test_files_outside_downloads_folder_are_never_deleted(self) -> None:
        # A symlink inside downloads pointing at the user's music must not be followed.
        link = self.settings / "downloads" / "7" / "link.mp3"
        link.parent.mkdir(parents=True)
        link.symlink_to(self.local_song)
        self.plugin._tracks.pop("999")
        asyncio.run(self.plugin.remove_all_game_tracks("all"))
        self.assertTrue(self.local_song.exists())


if __name__ == "__main__":
    unittest.main()
