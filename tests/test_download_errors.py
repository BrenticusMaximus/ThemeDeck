"""Tests for YouTube error handling: retries, messages and the auto-download guard.

Run with: python3 -m unittest discover -s tests
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

# main.py imports the `decky` module that only exists inside Decky Loader.
decky = sys.modules.setdefault("decky", types.ModuleType("decky"))
decky.logger = logging.getLogger("decky-test")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main  # noqa: E402


def completed(returncode: int, stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout="", stderr=stderr)


class ClassificationTest(unittest.TestCase):
    def test_retryable(self) -> None:
        for message in (
            "ERROR: unable to download video data: HTTP Error 403: Forbidden",
            "ERROR: HTTP Error 429: Too Many Requests",
            "Sign in to confirm you're not a bot",
            "Read timed out",
            "HTTP Error 503: Service Unavailable",
        ):
            with self.subTest(message=message):
                self.assertTrue(main.is_retryable_youtube_error(message))

    def test_not_retryable(self) -> None:
        for message in (
            "ERROR: [youtube] abc: Video unavailable",
            "ERROR: Postprocessing: ffprobe and ffmpeg not found",
            "Private video",
        ):
            with self.subTest(message=message):
                self.assertFalse(main.is_retryable_youtube_error(message))

    def test_descriptions(self) -> None:
        self.assertIn("rate limited", main.describe_youtube_error("HTTP Error 429: Too Many Requests"))
        self.assertIn("rate limited", main.describe_youtube_error("confirm you're not a bot"))
        self.assertIn("sudo pacman -S ffmpeg", main.describe_youtube_error("ffprobe and ffmpeg not found"))
        self.assertIn("can't be downloaded", main.describe_youtube_error("Video unavailable"))
        self.assertEqual(main.describe_youtube_error("something else"), "something else")


class RetryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.plugin = main.Plugin.__new__(main.Plugin)
        self.plugin._log_warning = lambda message: None
        self.plugin._trim_message = lambda value, limit: value[:limit]

    def run_with(self, results: list[subprocess.CompletedProcess[str]]):
        calls = []

        async def fake_run(command, timeout, env):
            calls.append(command)
            return results[len(calls) - 1]

        self.plugin._run_command = fake_run
        with mock.patch.object(main.asyncio, "sleep", new=mock.AsyncMock()):
            result = asyncio.run(
                self.plugin._run_with_retries(["yt-dlp"], timeout=1, env={}, label="t")
            )
        return result, len(calls)

    def test_temporary_error_is_retried_until_success(self) -> None:
        result, calls = self.run_with(
            [completed(1, "ERROR: HTTP Error 403: Forbidden"), completed(0)]
        )
        self.assertEqual((result.returncode, calls), (0, 2))

    def test_gives_up_after_the_last_retry(self) -> None:
        failure = completed(1, "ERROR: HTTP Error 403: Forbidden")
        result, calls = self.run_with([failure, failure, failure])
        self.assertEqual((result.returncode, calls), (1, 1 + len(main.YOUTUBE_RETRY_DELAYS_SECONDS)))

    def test_permanent_error_is_not_retried(self) -> None:
        result, calls = self.run_with([completed(1, "ERROR: Video unavailable")])
        self.assertEqual((result.returncode, calls), (1, 1))


class AutoDownloadGuardTest(unittest.TestCase):
    def test_auto_download_keeps_existing_track(self) -> None:
        plugin = main.Plugin.__new__(main.Plugin)
        plugin._tracks = {"2925064020": {"path": "/x/hand_picked.mp3"}}
        plugin._require_yt_dlp_invocation = mock.Mock(side_effect=AssertionError("should not run"))
        response = asyncio.run(
            plugin.download_youtube_audio(2925064020, "https://youtu.be/kIbvAMg8wwI", "auto")
        )
        self.assertEqual(response["skipped"], "has_track")
        self.assertEqual(plugin._tracks["2925064020"]["path"], "/x/hand_picked.mp3")


if __name__ == "__main__":
    unittest.main()
