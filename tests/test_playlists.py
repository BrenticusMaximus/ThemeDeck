from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path

if "decky" not in sys.modules:
    decky = types.ModuleType("decky")
    decky.DECKY_PLUGIN_SETTINGS_DIR = tempfile.gettempdir()
    decky.logger = types.SimpleNamespace(info=lambda *_: None, warning=lambda *_: None, error=lambda *_: None)
    sys.modules["decky"] = decky
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import Plugin


class PlaylistTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.plugin = Plugin()
        self.plugin._tracks_file = self.root / "tracks.json"
        self.plugin._downloads_dir = self.root / "downloads"
        self.plugin._preview_dir = self.root / "previews"
        self.plugin._downloads_dir.mkdir()
        self.a = self.plugin._downloads_dir / "a.mp3"
        self.b = self.plugin._downloads_dir / "b.m4a"
        self.a.write_bytes(b"a")
        self.b.write_bytes(b"bb")

    def tearDown(self):
        self.temp.cleanup()

    async def test_append_all_scopes_and_duplicate_is_idempotent(self):
        for key, assign in [("42", lambda path: self.plugin.set_track(42, str(path), path.name)),
                            ("__global__", lambda path: self.plugin.set_global_track(str(path), path.name)),
                            ("__store__", lambda path: self.plugin.set_store_track(str(path), path.name))]:
            await assign(self.a)
            await assign(self.b)
            await assign(self.a)
            self.assertEqual([x["path"] for x in self.plugin._playlist_entries(self.plugin._tracks[key])], [str(self.a), str(self.b)])
        reloaded = Plugin()
        reloaded._tracks_file = self.plugin._tracks_file
        reloaded._load_tracks()
        self.assertEqual(reloaded._tracks, self.plugin._tracks)

    async def test_many_tracks_have_no_fixed_limit(self):
        for key, assign in [("42", lambda path: self.plugin.set_track(42, str(path), path.name)),
                            ("__global__", lambda path: self.plugin.set_global_track(str(path), path.name)),
                            ("__store__", lambda path: self.plugin.set_store_track(str(path), path.name))]:
            for i in range(100):
                path = self.root / f"song-{i}.mp3"
                path.touch()
                await assign(path)
            self.assertEqual(len(self.plugin._playlist_entries(self.plugin._tracks[key])), 100)

    async def test_legacy_assignment_and_remove_primary_preserve_preferences(self):
        self.plugin._tracks = {"42": {"app_id": 42, "path": str(self.a), "filename": "a.mp3", "volume": 0.4, "start_offset": 3, "loop": False}}
        await self.plugin.set_track(42, str(self.b), "b.m4a")
        await self.plugin.remove_playlist_track("42", str(self.a))
        track = self.plugin._tracks["42"]
        self.assertEqual(track["path"], str(self.b))
        self.assertEqual((track["volume"], track["start_offset"], track["loop"]), (0.4, 3, False))
        self.assertTrue(self.a.exists())
        await self.plugin.remove_playlist_track("42", str(self.b))
        self.assertNotIn("42", self.plugin._tracks)

    async def test_storage_protects_and_deletes_only_requested_member(self):
        await self.plugin.set_track(42, str(self.a), "a.mp3")
        await self.plugin.set_track(42, str(self.b), "b.m4a")
        self.assertEqual(self.plugin._storage_references(self.b), ["42"])
        storage = await self.plugin.get_song_storage()
        self.assertEqual(storage["unused_bytes"], 0)
        with self.assertRaises(ValueError):
            self.plugin._delete_storage_file("downloads/b.m4a", False)
        self.plugin._delete_storage_file("downloads/a.mp3", True)
        self.assertEqual(self.plugin._tracks["42"]["path"], str(self.b))
        self.assertTrue(self.b.exists())
        self.assertFalse(self.a.exists())

    async def test_missing_cleanup_preserves_valid_members(self):
        await self.plugin.set_track(42, str(self.a), "a.mp3")
        await self.plugin.set_track(42, str(self.b), "b.m4a")
        self.a.unlink()
        await self.plugin.clear_missing_song_assignments()
        self.assertEqual(self.plugin._tracks["42"]["path"], str(self.b))

    async def test_reorder_all_scopes_persists_and_preserves_settings(self):
        for key, assign in [("42", lambda p: self.plugin.set_track(42, str(p), p.name)),
                            ("__global__", lambda p: self.plugin.set_global_track(str(p), p.name)),
                            ("__store__", lambda p: self.plugin.set_store_track(str(p), p.name))]:
            await assign(self.a)
            await assign(self.b)
            self.plugin._tracks[key]["volume"] = 0.4
            await self.plugin.move_playlist_track(key, str(self.b), -1)
            self.assertEqual(self.plugin._tracks[key]["path"], str(self.b))
            self.assertEqual(self.plugin._tracks[key]["volume"], 0.4)
            await self.plugin.move_playlist_track(key, str(self.b), -1)
            self.assertEqual(self.plugin._tracks[key]["path"], str(self.b))
            await self.plugin.move_playlist_track(key, str(self.b), 1)
            self.assertEqual(self.plugin._tracks[key]["path"], str(self.a))
        self.plugin._load_tracks()
        self.assertEqual(self.plugin._tracks["42"]["path"], str(self.a))
        with self.assertRaises(ValueError):
            await self.plugin.move_playlist_track("42", str(self.a), 2)

    async def test_failed_save_restores_playlist(self):
        await self.plugin.set_track(42, str(self.a), "a.mp3")
        await self.plugin.set_track(42, str(self.b), "b.m4a")
        previous = self.plugin._tracks.copy()
        def fail():
            raise OSError("write failed")
        self.plugin._save_tracks = fail
        with self.assertRaises(OSError):
            await self.plugin.remove_playlist_track("42", str(self.a))
        self.assertEqual(self.plugin._tracks, previous)

if __name__ == "__main__":
    unittest.main()
