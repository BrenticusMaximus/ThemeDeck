"""Destructive storage operations run only on temporary fixture directories."""
import asyncio
import importlib.util
import json
import logging
from pathlib import Path
import sys
import tempfile
import types
from unittest.mock import patch

sys.modules['decky'] = types.SimpleNamespace(logger=logging.getLogger('test'))
spec = importlib.util.spec_from_file_location('themedeck', Path(__file__).resolve().parents[1] / 'main.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

async def must_fail(awaitable):
    try:
        await awaitable
    except (ValueError, RuntimeError, OSError):
        return
    raise AssertionError('Unsafe operation unexpectedly succeeded')

async def check():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        module.decky.DECKY_PLUGIN_SETTINGS_DIR = str(root / 'settings')
        plugin = module.Plugin()
        plugin._settings_dir.mkdir()
        plugin._downloads_dir.mkdir()
        plugin._preview_dir.mkdir()
        def file(relative, data=b'1234'):
            path = plugin._settings_dir / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            return path
        song = file('downloads/1/song.m4a', b'12345678')
        unused = file('downloads/2/unused.mp3')
        preview = file('previews/test/preview.m4a')
        partial = file('downloads/2/failed.m4a.part')
        local = root / 'my-music.mp3'; local.write_bytes(b'private music')
        # One managed download shared between a game and global ambient.
        plugin._tracks = {'1': {'path': str(song)}, '__global__': {'path': str(song)}, '2': {'path': str(local)}}
        plugin._save_tracks()
        state = await plugin.get_song_storage()
        assert state['total_bytes'] == 20
        assert state['preview_bytes'] == 4 and state['unused_bytes'] == 12
        assert state['files'][0]['assignments'] == ['1', '__global__']
        # Reject assigned-file deletion without explicit confirmation.
        await must_fail(plugin.delete_song_storage('downloads/1/song.m4a'))
        assert song.exists() and '1' in plugin._tracks
        # An old confirmation cannot silently remove newly added assignments.
        await must_fail(plugin.delete_song_storage('downloads/1/song.m4a', True, ['1']))
        assert song.exists() and '__global__' in plugin._tracks
        # Cleanup frees real disk space and keeps all shared/assigned files.
        result = await plugin.clean_song_storage('previews')
        assert result['freed_bytes'] == 4 and not preview.exists() and unused.exists()
        result = await plugin.clean_song_storage('unused')
        assert result['freed_bytes'] == 8 and not unused.exists() and not partial.exists()
        assert song.exists() and local.exists()
        # Traversal, absolute paths, directories, unknown categories, symlinks.
        for invalid in ('../my-music.mp3', str(local), 'tracks.json', 'downloads/../../my-music.mp3', 'downloads/1'):
            await must_fail(plugin.delete_song_storage(invalid, True))
        (plugin._downloads_dir / 'link.mp3').symlink_to(local)
        (plugin._downloads_dir / 'link-dir').symlink_to(root, target_is_directory=True)
        await must_fail(plugin.delete_song_storage('downloads/link.mp3', True))
        await must_fail(plugin.delete_song_storage('downloads/link-dir/my-music.mp3', True))
        assert len((await plugin.get_song_storage())['files']) == 1
        assert local.exists()
        # Prevent deleting an active download (including bulk cleanup).
        async with plugin._storage_lock:
            await must_fail(plugin.delete_song_storage('downloads/1/song.m4a', True))
            await must_fail(plugin.clean_song_storage('unused'))
        # Save failure must not delete the file or lose assignments in memory.
        with patch.object(plugin, '_save_tracks', side_effect=OSError('disk full')):
            await must_fail(plugin.delete_song_storage('downloads/1/song.m4a', True))
        assert song.exists() and '1' in plugin._tracks and '__global__' in plugin._tracks
        # Delete failure restores persisted assignments too.
        with patch.object(module.Path, 'unlink', side_effect=PermissionError('read only')):
            await must_fail(plugin.delete_song_storage('downloads/1/song.m4a', True))
        assert song.exists() and '1' in json.loads(plugin._tracks_file.read_text())
        result = await plugin.delete_song_storage('downloads/1/song.m4a', True)
        assert result['freed_bytes'] == 8 and not song.exists()
        assert set(plugin._tracks) == {'2'} and set(json.loads(plugin._tracks_file.read_text())) == {'2'}
        assert local.exists()
        # Missing references can be repaired without deleting any user files.
        plugin._tracks['3'] = {'path': str(root / 'missing.mp3')}
        assert (await plugin.get_song_storage())['missing_assignments'] == ['3']
        await plugin.clear_missing_song_assignments()
        assert set(plugin._tracks) == {'2'} and local.exists()
        # Ordinary unassign is deliberately non-destructive.
        kept = file('downloads/4/keep.mp3')
        plugin._tracks['4'] = {'path': str(kept)}
        await plugin.remove_track(4)
        assert kept.exists()
        # Assigned previews are never removed by bulk cleanup.
        assigned_preview = file('previews/assigned/preview.m4a')
        plugin._tracks['__store__'] = {'path': str(assigned_preview)}
        await plugin.clean_song_storage('previews')
        assert assigned_preview.exists() and '__store__' in plugin._tracks
        # A real persistence failure leaves the old JSON intact and no temp debris.
        plugin._save_tracks()
        saved = plugin._tracks_file.read_bytes()
        with patch.object(module.os, 'replace', side_effect=OSError('disk full')):
            await must_fail(plugin.delete_song_storage('previews/assigned/preview.m4a', True))
        assert assigned_preview.exists() and plugin._tracks_file.read_bytes() == saved
        assert not list(plugin._settings_dir.glob('tracks-*.tmp'))
        # The actual preview wrapper holds the deletion lock during network work.
        started, finish = asyncio.Event(), asyncio.Event()
        async def pending_preview(url):
            started.set()
            await finish.wait()
            return {'data': 'audio'}
        with patch.object(plugin, '_prepare_youtube_preview', side_effect=pending_preview):
            task = asyncio.create_task(plugin.get_youtube_preview_stream('https://www.youtube.com/watch?v=test'))
            await started.wait()
            await must_fail(plugin.delete_song_storage('previews/assigned/preview.m4a', True))
            finish.set()
            await task
        print('Storage size, cleanup, shared references, path protection, transfer locks, rollback, and missing-file checks passed')

asyncio.run(check())
