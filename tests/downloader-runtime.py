"""Regression checks for downloader runtimes invalidated by OS updates."""
import asyncio
import importlib.util
import logging
from pathlib import Path
import subprocess
import sys
import tempfile
import types
from unittest.mock import AsyncMock, patch

sys.modules['decky'] = types.SimpleNamespace(logger=logging.getLogger('test'))
spec = importlib.util.spec_from_file_location('themedeck', Path(__file__).resolve().parents[1] / 'main.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

async def check():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        module.decky.DECKY_PLUGIN_SETTINGS_DIR = str(root)
        plugin = module.Plugin()
        plugin._log_info = lambda message: None
        plugin._log_warning = lambda message: None
        plugin._log_error = lambda message: None
        plugin._yt_venv_bin.mkdir(parents=True)
        plugin._bin_dir.mkdir()
        # File is executable, but its interpreter was removed during an OS update.
        plugin._yt_venv_yt_dlp.write_text('#!/missing/python-before-os-update\n')
        plugin._yt_venv_yt_dlp.chmod(0o755)
        with patch.object(module.shutil, 'which', return_value=None), patch.object(module.Path, 'home', return_value=root):
            assert plugin._resolve_yt_dlp_invocation()['source'] == 'venv'
            assert (await plugin.get_yt_dlp_status())['installed'] is False
            # A broken preferred runtime must not hide a healthy fallback.
            plugin._yt_dlp_path.write_text('#!/bin/sh\necho 2026.01.01\n')
            plugin._yt_dlp_path.chmod(0o755)
            status = await plugin.get_yt_dlp_status()
            assert status['installed'] and status['source'] == 'local'
            assert status['version'] == '2026.01.01'
            with patch.object(plugin, 'update_yt_dlp', new_callable=AsyncMock) as update:
                assert (await plugin._require_yt_dlp_invocation())['source'] == 'local'
                update.assert_not_awaited()

        # Recreate an invalid venv rather than retaining obsolete site-packages.
        async def run(command, **kwargs):
            if '--version' in command:
                return subprocess.CompletedProcess(command, 1, '', 'ModuleNotFoundError')
            if 'venv' in command:
                assert '--clear' in command
                plugin._yt_venv_python.touch()
            return subprocess.CompletedProcess(command, 0, '', '')
        with patch.object(module.shutil, 'which', return_value='/usr/bin/python3'), patch.object(plugin, '_run_command', side_effect=run):
            assert await plugin._install_yt_dlp_in_venv() is None

        # Concurrent callers recheck after acquiring the lock and share a repair.
        healthy = False
        async def working():
            return {'source': 'venv'} if healthy else None
        async def repair():
            nonlocal healthy
            await asyncio.sleep(0)
            healthy = True
        with patch.object(plugin, '_working_yt_dlp_invocation', side_effect=working), patch.object(plugin, 'update_yt_dlp', side_effect=repair) as update:
            results = await asyncio.gather(*(plugin._require_yt_dlp_invocation() for _ in range(3)))
            assert all(result['source'] == 'venv' for result in results)
            assert update.await_count == 1
        # Failures after downloader selection must preserve the real exception and
        # record a full traceback, including file-loading/postprocessing failures.
        with patch.object(plugin, '_prepare_youtube_preview', side_effect=RuntimeError('ffmpeg not found')), patch.object(plugin, '_log_error') as log:
            try:
                await plugin.get_youtube_preview_stream('https://www.youtube.com/watch?v=test')
            except RuntimeError as error:
                assert str(error) == 'ffmpeg not found'
            else:
                raise AssertionError('preview error was swallowed')
            assert 'Traceback' in log.call_args.args[0]
            assert 'ffmpeg not found' in log.call_args.args[0]
        print('Downloader runtime health, fallback, venv rebuild, and concurrent repair checks passed')

asyncio.run(check())
