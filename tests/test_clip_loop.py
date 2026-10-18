"""Tests for the per-game clip loop settings in main.py.

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


class ClipLengthTest(unittest.TestCase):
    def setUp(self) -> None:
        self.plugin = main.Plugin.__new__(main.Plugin)
        self.plugin._tracks = {"42": {"app_id": 42, "path": "/x.opus", "start_offset": 0}}
        self.plugin._save_tracks = lambda: None

    def run_async(self, coro):
        return asyncio.run(coro)

    def test_custom_length_is_stored(self) -> None:
        self.run_async(self.plugin.set_clip_length(42, 30))
        self.assertEqual(self.plugin._tracks["42"]["clip_length"], 30)

    def test_zero_means_full_song(self) -> None:
        self.run_async(self.plugin.set_clip_length(42, 0))
        self.assertEqual(self.plugin._tracks["42"]["clip_length"], 0)

    def test_none_follows_general_setting(self) -> None:
        self.run_async(self.plugin.set_clip_length(42, 30))
        self.run_async(self.plugin.set_clip_length(42, None))
        self.assertNotIn("clip_length", self.plugin._tracks["42"])

    def test_length_is_clamped(self) -> None:
        self.run_async(self.plugin.set_clip_length(42, 0.2))
        self.assertEqual(self.plugin._tracks["42"]["clip_length"], 1.0)
        self.run_async(self.plugin.set_clip_length(42, 10**9))
        self.assertEqual(self.plugin._tracks["42"]["clip_length"], main.GAME_TRACK_MAX_SECONDS)

    def test_unknown_game_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.run_async(self.plugin.set_clip_length(7, 30))

    def test_game_start_skip_can_exceed_thirty_seconds(self) -> None:
        self.run_async(self.plugin.set_start_offset(42, 95))
        self.assertEqual(self.plugin._tracks["42"]["start_offset"], 95)

    def test_new_track_keeps_clip_length(self) -> None:
        self.run_async(self.plugin.set_clip_length(42, 20))
        with tempfile.NamedTemporaryFile(suffix=".opus") as audio:
            self.run_async(self.plugin.set_track(42, audio.name, "song.opus"))
        self.assertEqual(self.plugin._tracks["42"]["clip_length"], 20)


if __name__ == "__main__":
    unittest.main()
