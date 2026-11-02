import asyncio
import importlib.util
import json
import logging
import stat
from pathlib import Path
import sys
import tempfile
import types
from unittest.mock import patch

sys.modules['decky'] = types.SimpleNamespace(logger=logging.getLogger('test'))
spec = importlib.util.spec_from_file_location('themedeck', Path(__file__).resolve().parents[1] / 'main.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

async def check():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        audio = root / 'track.mp3'
        audio.write_bytes(b'test')
        plugin = module.Plugin.__new__(module.Plugin)
        plugin._tracks_file = root / 'tracks.json'
        plugin._tracks = {'1': {'path': str(audio), 'volume': 0.5, 'loop': False}}
        with patch.object(module.time, 'time', return_value=100):
            await plugin.set_track(2, str(audio), audio.name)
        assert plugin._tracks['2']['assigned_at'] == 100
        assert 'assigned_at' not in plugin._tracks['1']
        with patch.object(module.time, 'time', return_value=200):
            await plugin.set_track(2, str(audio), audio.name)
        await plugin.set_volume(2, 0.3)
        assert plugin._tracks['2']['assigned_at'] == 200
        assert json.loads(plugin._tracks_file.read_text())['2']['assigned_at'] == 200
        await plugin.remove_track(2)
        assert '2' not in json.loads(plugin._tracks_file.read_text())
        plugin._downloads_dir = root / 'downloads'
        old = {
            '1': {'path': str(audio)},
            '2': {'path': str(audio), 'youtube_id': 'old'},
            '3': {'path': str(audio), 'youtube_id': 'known', 'assigned_at': 42},
            '4': {'path': str(audio), 'youtube_id': 'missing-date'},
            '5': {'path': str(plugin._downloads_dir / '5' / 'song.mp3')},
            '__global__': {'path': str(audio), 'youtube_id': 'global'},
        }
        plugin._tracks_file.write_text(json.dumps(old))
        with patch.object(plugin, '_file_creation_timestamp', side_effect=[123, None, 456]):
            plugin._load_tracks()
        recovered = json.loads(plugin._tracks_file.read_text())
        assert 'assigned_at' not in recovered['1']
        assert recovered['2']['assigned_at'] == 123
        assert recovered['2']['assigned_at_estimated'] is True
        assert recovered['2']['assigned_at_source'] == 'file_creation'
        assert recovered['3']['assigned_at'] == 42
        assert 'assigned_at' not in recovered['4']
        assert recovered['5']['assigned_at'] == 456
        assert 'assigned_at' not in recovered['__global__']
        with patch.object(module.time, 'time', return_value=789):
            await plugin.set_track(2, str(audio), audio.name)
        assert plugin._tracks['2']['assigned_at'] == 789
        assert 'assigned_at_estimated' not in plugin._tracks['2']
        # Linux birth-time lookup, unsupported birth time, and command failure.
        with patch.object(module.sys, 'platform', 'linux'), patch.object(Path, 'stat', return_value=types.SimpleNamespace(st_mode=stat.S_IFREG)):
            with patch.object(module.subprocess, 'run', return_value=types.SimpleNamespace(returncode=0, stdout='1234')) as run:
                assert plugin._file_creation_timestamp(audio) == 1234
                assert '--format=%W' in run.call_args.args[0]
            with patch.object(module.subprocess, 'run', return_value=types.SimpleNamespace(returncode=0, stdout='0')):
                assert plugin._file_creation_timestamp(audio) is None
            with patch.object(module.subprocess, 'run', side_effect=OSError('unavailable')):
                assert plugin._file_creation_timestamp(audio) is None
        assert plugin._file_creation_timestamp(root / 'missing.mp3') is None
        print('Assignment persistence and creation-date recovery checks passed')

asyncio.run(check())
