"""Preview and assignment must work without ffmpeg/ffprobe."""
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
        module.decky.DECKY_PLUGIN_SETTINGS_DIR = directory
        plugin = module.Plugin()
        plugin._debug_log_file = Path(directory) / 'debug.log'
        invocation = {'command': ['yt-dlp'], 'env': None, 'source': 'test', 'path': 'yt-dlp'}
        commands = []
        plugin._deno_path.parent.mkdir(parents=True)
        plugin._deno_path.write_text('#!/bin/sh\necho deno 2.9.8\n')
        plugin._deno_path.chmod(0o755)
        plugin._use_firefox_cookies = True
        async def run(command, **kwargs):
            commands.append(command)
            assert '--extract-audio' not in command
            assert '--audio-format' not in command
            assert command[command.index('--format') + 1] == 'bestaudio[ext=m4a]'
            assert command[command.index('--fixup') + 1] == 'never'
            assert '--ignore-config' in command
            assert command[command.index('--cookies-from-browser') + 1] == 'firefox'
            assert command[command.index('--js-runtimes') + 1] == f'deno:{plugin._deno_path}'
            output = Path(command[command.index('--paths') + 1]) / 'audio.m4a'
            output.write_bytes(b'native audio payload')
            return subprocess.CompletedProcess(command, 0, str(output) + '\n', '')
        with patch.object(plugin, '_require_yt_dlp_invocation', new=AsyncMock(return_value=invocation)), patch.object(plugin, '_run_command', side_effect=run), patch.object(module.shutil, 'which', return_value=None):
            preview = await plugin.get_youtube_preview_stream('https://www.youtube.com/watch?v=z2xxQXcmOeE')
            assert preview['mime'] == 'audio/mp4'
            assert Path(preview['path']).suffix == '.m4a'
            assert preview['data']
            cached = await plugin.get_youtube_preview_stream('https://www.youtube.com/watch?v=z2xxQXcmOeE')
            assert Path(cached['path']).resolve() == Path(preview['path']).resolve()
            assert len(commands) == 1
            download = await plugin.download_youtube_audio(123, 'https://www.youtube.com/watch?v=z2xxQXcmOeE')
            assert download['filename'] == 'audio.m4a'
            assert plugin._tracks['123']['path'] == download['path']
            assert plugin._tracks_file.exists()
            assert len(commands) == 2
        print('Preview, cached preview, and download assignment pass without ffmpeg/ffprobe')

asyncio.run(check())
