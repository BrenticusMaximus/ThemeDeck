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
            for scope, key, folder in [(-1, '__global__', 'global'), (-2, '__store__', 'store')]:
                first = await plugin.download_youtube_audio(scope, 'https://www.youtube.com/watch?v=z2xxQXcmOeE')
                assert Path(first['path']).parent.name == folder
                assert plugin._tracks[key]['youtube_id'] == 'z2xxQXcmOeE'
                extra = Path(directory) / f'extra-{folder}.m4a'
                extra.write_bytes(b'extra')
                if scope == -1:
                    await plugin.set_global_volume(.4)
                    await plugin.set_global_start_offset(7)
                    await plugin.set_global_loop(False)
                    await plugin.set_global_track(str(extra), extra.name)
                else:
                    await plugin.set_store_volume(.4)
                    await plugin.set_store_start_offset(7)
                    await plugin.set_store_loop(False)
                    await plugin.set_store_track(str(extra), extra.name)
                await plugin.download_youtube_audio(scope, 'https://www.youtube.com/watch?v=z2xxQXcmOeE')
                root = plugin._tracks[key]
                assert len(root['additional_tracks']) == 1
                assert root['volume'] == .4 and root['start_offset'] == 7 and root['loop'] is False
                assert str(scope) not in plugin._tracks
            for invalid in [0, -3]:
                try:
                    await plugin.download_youtube_audio(invalid, 'https://www.youtube.com/watch?v=z2xxQXcmOeE')
                except ValueError:
                    pass
                else:
                    raise AssertionError('Invalid target accepted')

        print('Preview, cached preview, and download assignment pass without ffmpeg/ffprobe')

asyncio.run(check())
