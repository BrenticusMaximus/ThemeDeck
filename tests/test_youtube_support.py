from __future__ import annotations

import hashlib
import io
import subprocess
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, patch


if "decky" not in sys.modules:
    decky = types.ModuleType("decky")
    decky.DECKY_PLUGIN_SETTINGS_DIR = tempfile.gettempdir()
    decky.logger = types.SimpleNamespace(info=lambda *_: None, warning=lambda *_: None, error=lambda *_: None)
    sys.modules["decky"] = decky

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main


class YouTubeSupportTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        settings_dir = Path(self.temp_dir.name)
        self.plugin = main.Plugin()
        self.plugin._settings_dir = settings_dir
        self.plugin._youtube_support_settings_file = settings_dir / "youtube-support.json"
        self.plugin._bin_dir = settings_dir / "bin"
        self.plugin._yt_dlp_path = self.plugin._bin_dir / "yt-dlp"
        self.plugin._yt_venv_dir = settings_dir / "ytvenv"
        self.plugin._yt_venv_bin = self.plugin._yt_venv_dir / "bin"
        self.plugin._yt_venv_python = self.plugin._yt_venv_bin / "python"
        self.plugin._yt_venv_yt_dlp = self.plugin._yt_venv_bin / "yt-dlp"
        self.plugin._deno_dir = settings_dir / "deno"
        self.plugin._deno_path = self.plugin._deno_dir / "bin" / "deno"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_firefox_cookie_access_is_opt_in_and_uses_explicit_deno_path(self) -> None:
        self.plugin._deno_path.parent.mkdir(parents=True)
        self.plugin._deno_path.write_bytes(b"deno")
        self.plugin._deno_path.chmod(0o755)

        self.assertEqual(
            self.plugin._youtube_access_args(),
            ["--js-runtimes", f"deno:{self.plugin._deno_path}"],
        )

        self.plugin._use_firefox_cookies = True
        self.plugin._save_youtube_support_settings()
        self.assertEqual(
            self.plugin._youtube_access_args(),
            [
                "--cookies-from-browser",
                "firefox",
                "--js-runtimes",
                f"deno:{self.plugin._deno_path}",
            ],
        )

        self.plugin._use_firefox_cookies = False
        self.plugin._load_youtube_support_settings()
        self.assertTrue(self.plugin._use_firefox_cookies)

    async def test_firefox_cookie_setting_is_saved(self) -> None:
        expected_status = {"firefox_cookies_enabled": True}
        with patch.object(
            self.plugin,
            "get_yt_dlp_status",
            AsyncMock(return_value=expected_status),
        ):
            status = await self.plugin.set_youtube_firefox_cookies(True)

        self.assertEqual(status, expected_status)
        self.assertTrue(self.plugin._use_firefox_cookies)
        self.plugin._use_firefox_cookies = False
        self.plugin._load_youtube_support_settings()
        self.assertTrue(self.plugin._use_firefox_cookies)

    def test_youtube_errors_offer_specific_next_steps(self) -> None:
        for message, expected in [
            ("ERROR: Sign in to confirm you're not a bot", "Sign into YouTube in Firefox"),
            ("ERROR: HTTP Error 403: Forbidden", "Update YouTube support"),
            ("WARNING: Signature solving failed", "Update YouTube support"),
        ]:
            result = subprocess.CompletedProcess([], 1, "", message)
            self.assertIn(expected, self.plugin._command_error(result, "failed"))

    async def test_broken_deno_reports_unavailable(self) -> None:
        with patch.object(self.plugin, "_run_command", side_effect=FileNotFoundError()):
            self.assertIsNone(await self.plugin._get_deno_version(Path("/missing/deno")))

    async def test_cookie_save_failure_rolls_back(self) -> None:
        with patch.object(self.plugin, "_save_youtube_support_settings", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                await self.plugin.set_youtube_firefox_cookies(True)
        self.assertFalse(self.plugin._use_firefox_cookies)

    async def test_bad_deno_checksum_is_rejected(self) -> None:
        async def fake_download(url, target, **kwargs):
            target.write_bytes(b"broken archive" if not url.endswith(".sha256sum") else b"0" * 64)
        with patch.object(main.platform, "system", return_value="Linux"), patch.object(main.platform, "machine", return_value="x86_64"), patch.object(self.plugin, "_download_file", side_effect=fake_download):
            with self.assertRaisesRegex(RuntimeError, "checksum verification failed"):
                await self.plugin._install_deno()
        self.assertFalse(self.plugin._deno_path.exists())

    def test_deno_minimum_version(self) -> None:
        self.assertFalse(self.plugin._is_supported_deno_version(None))
        self.assertFalse(self.plugin._is_supported_deno_version("2.2.9"))
        self.assertTrue(self.plugin._is_supported_deno_version("2.3.0"))
        self.assertTrue(self.plugin._is_supported_deno_version("2.9.5"))

    async def test_user_pip_fallback_installs_default_extra(self) -> None:
        completed = subprocess.CompletedProcess([], 0, "", "")
        run_command = AsyncMock(return_value=completed)
        with patch.object(main.shutil, "which", return_value="/usr/bin/python3"):
            with patch.object(self.plugin, "_run_command", run_command):
                self.assertIsNone(await self.plugin._try_install_yt_dlp_with_pip())

        command = run_command.await_args.args[0]
        self.assertIn("yt-dlp[default]", command)

    async def test_venv_installs_default_extra(self) -> None:
        commands: list[list[str]] = []

        async def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            commands.append(command)
            self.plugin._yt_venv_bin.mkdir(parents=True, exist_ok=True)
            self.plugin._yt_venv_python.write_bytes(b"python")
            if "pip" in command:
                self.plugin._yt_venv_yt_dlp.write_bytes(b"yt-dlp")
            return subprocess.CompletedProcess(command, 0, "", "")

        with patch.object(main.shutil, "which", return_value="/usr/bin/python3"):
            with patch.object(self.plugin, "_run_command", side_effect=fake_run):
                self.assertIsNone(await self.plugin._install_yt_dlp_in_venv())

        pip_command = next(command for command in commands if "pip" in command)
        self.assertIn("yt-dlp[default]", pip_command)

    async def test_failed_venv_update_prefers_verified_local_fallback(self) -> None:
        self.plugin._yt_venv_bin.mkdir(parents=True, exist_ok=True)
        self.plugin._yt_venv_yt_dlp.write_bytes(b"old yt-dlp")
        self.plugin._yt_venv_yt_dlp.chmod(0o755)

        async def fake_download(target: Path) -> None:
            target.write_bytes(b"#!/usr/bin/env python3\n# replacement yt-dlp\n")

        async def fake_finish() -> dict[str, object]:
            invocation = self.plugin._resolve_yt_dlp_invocation()
            self.assertIsNotNone(invocation)
            return {
                "installed": True,
                "source": invocation["source"],
                "path": invocation["path"],
                "version": "2026.08.01",
                "deno_version": "2.9.5",
            }

        with patch.object(
            self.plugin,
            "_install_yt_dlp_in_venv",
            AsyncMock(return_value="venv pip install failed"),
        ):
            with patch.object(
                self.plugin,
                "_download_yt_dlp_binary",
                side_effect=fake_download,
            ):
                with patch.object(
                    self.plugin,
                    "_get_yt_dlp_version",
                    AsyncMock(return_value="2026.08.01"),
                ):
                    with patch.object(
                        self.plugin,
                        "_finish_youtube_support_setup",
                        side_effect=fake_finish,
                    ):
                        status = await self.plugin.update_yt_dlp()

        self.assertEqual(status["source"], "local")
        self.assertEqual(self.plugin._preferred_yt_dlp_source, "local")
        self.plugin._preferred_yt_dlp_source = "venv"
        self.plugin._load_youtube_support_settings()
        self.assertEqual(self.plugin._preferred_yt_dlp_source, "local")
        self.assertEqual(
            self.plugin._resolve_yt_dlp_invocation()["source"],
            "local",
        )

    async def test_managed_deno_install_verifies_and_extracts_release(self) -> None:
        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(archive_buffer, "w") as archive:
            archive.writestr("deno", b"test-deno-binary")
        archive_bytes = archive_buffer.getvalue()
        checksum = hashlib.sha256(archive_bytes).hexdigest()

        async def fake_download(url: str, target: Path, timeout: int = 220) -> None:
            del timeout
            if url.endswith(".sha256sum"):
                target.write_text(f"{checksum}  deno.zip\n", encoding="utf-8")
            else:
                target.write_bytes(archive_bytes)

        with patch.object(main.platform, "system", return_value="Linux"):
            with patch.object(main.platform, "machine", return_value="x86_64"):
                with patch.object(self.plugin, "_download_file", side_effect=fake_download):
                    await self.plugin._install_deno()

        self.assertEqual(self.plugin._deno_path.read_bytes(), b"test-deno-binary")


if __name__ == "__main__":
    unittest.main()
