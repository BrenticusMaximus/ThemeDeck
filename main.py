from __future__ import annotations

import asyncio
import base64
import hashlib
import html as html_lib
import json
import math
import os
import platform
import re
import shutil
import ssl
import sys
import subprocess
import tempfile
import threading
import traceback
import unicodedata
import urllib.parse
import urllib.request
import urllib.error
import time
import zipfile
from pathlib import Path
from typing import Any

import decky

SUPPORTED_AUDIO_EXTENSIONS = {"mp3", "aac", "flac", "ogg", "wav", "m4a"}
YTDLP_RELEASE_URLS = (
    "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp",
    "https://yt-dlp.org/downloads/latest/yt-dlp",
    "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_linux",
)
DENO_MINIMUM_VERSION = (2, 3, 0)
DENO_RELEASE_BASE_URL = "https://github.com/denoland/deno/releases/latest/download"
DENO_RELEASE_ASSETS = {
    ("linux", "x86_64"): "deno-x86_64-unknown-linux-gnu.zip",
    ("linux", "amd64"): "deno-x86_64-unknown-linux-gnu.zip",
    ("linux", "aarch64"): "deno-aarch64-unknown-linux-gnu.zip",
    ("linux", "arm64"): "deno-aarch64-unknown-linux-gnu.zip",
}


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def clamp_seconds(value: float, minimum: float = 0.0, maximum: float = 30.0) -> float:
    return max(minimum, min(maximum, value))


class Plugin:
    def __init__(self) -> None:
        self._storage_lock = asyncio.Lock()
        self._yt_dlp_repair_lock = asyncio.Lock()
        self._tracks: dict[str, dict[str, Any]] = {}
        self._global_track_key = "__global__"
        self._store_track_key = "__store__"
        self._settings_dir = Path(decky.DECKY_PLUGIN_SETTINGS_DIR)
        self._tracks_file = self._settings_dir / "tracks.json"
        self._youtube_support_settings_file = (
            self._settings_dir / "youtube-support.json"
        )
        self._bin_dir = self._settings_dir / "bin"
        self._yt_dlp_path = self._bin_dir / "yt-dlp"
        self._yt_venv_dir = self._settings_dir / "ytvenv"
        self._yt_venv_bin = self._yt_venv_dir / "bin"
        self._yt_venv_python = self._yt_venv_bin / "python"
        self._yt_venv_yt_dlp = self._yt_venv_bin / "yt-dlp"
        self._deno_dir = self._settings_dir / "deno"
        self._deno_path = self._deno_dir / "bin" / "deno"
        self._downloads_dir = self._settings_dir / "downloads"
        self._preview_dir = self._settings_dir / "previews"
        self._debug_log_file = Path.home() / "ThemeDeck" / "themedeck-debug.log"
        self._playback_process: subprocess.Popen[bytes] | None = None
        self._playback_player: str | None = None
        self._playback_started_at: float = 0.0
        self._playback_start_offset: float = 0.0
        self._playback_log_file = self._settings_dir / "backend-player.log"
        self._use_firefox_cookies = False
        self._preferred_yt_dlp_source = "venv"

    async def _main(self) -> None:
        self._settings_dir.mkdir(parents=True, exist_ok=True)
        self._bin_dir.mkdir(parents=True, exist_ok=True)
        self._downloads_dir.mkdir(parents=True, exist_ok=True)
        self._preview_dir.mkdir(parents=True, exist_ok=True)
        self._load_tracks()
        self._load_youtube_support_settings()
        self._log_info("ThemeDeck backend ready")

    async def _unload(self) -> None:
        self._stop_playback_process()
        self._log_info("ThemeDeck backend unloaded")

    async def _migration(self) -> None:
        self._settings_dir.mkdir(parents=True, exist_ok=True)
        self._bin_dir.mkdir(parents=True, exist_ok=True)
        self._downloads_dir.mkdir(parents=True, exist_ok=True)
        self._preview_dir.mkdir(parents=True, exist_ok=True)

    async def get_tracks(self) -> dict[str, dict[str, Any]]:
        return self._tracks

    async def play_track_backend(
        self,
        path: str,
        volume: float = 1.0,
        loop: bool = True,
        start_offset: float = 0.0,
    ) -> dict[str, Any]:
        resolved = Path(path).expanduser().resolve()
        if not resolved.exists() or not resolved.is_file():
            raise FileNotFoundError(f"Audio file not found: {resolved}")
        try:
            resolved.open("rb").close()
        except PermissionError as error:
            raise PermissionError(f"Permission denied: {resolved}") from error

        player = self._resolve_audio_player()
        if not player:
            raise RuntimeError("No supported backend player found")

        volume_pct = int(round(clamp(volume) * 100))
        offset_seconds = clamp_seconds(start_offset)
        self._stop_playback_process()

        ffplay_path = self._find_command_path("ffplay")
        if player == "mpv":
            command = [
                "mpv",
                "--no-video",
                "--quiet",
                "--audio-display=no",
                f"--volume={volume_pct}",
                f"--start={offset_seconds}",
                "--loop-file=inf" if loop else "--loop-file=no",
                str(resolved),
            ]
        elif player == "mpg123":
            scale = max(1, int(round(clamp(volume) * 32768)))
            command = [
                "mpg123",
                "-q",
                "-f",
                str(scale),
            ]
            if loop:
                command.extend(["--loop", "-1"])
            # mpg123 accepts frame-based skip, not second-based seek; keep behavior
            # stable by always starting from beginning for backend fallback.
            command.append(str(resolved))
        elif player == "ffmpeg":
            command = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
            ]
            if loop:
                command.extend(["-stream_loop", "-1"])
            command.extend(
                [
                    "-ss",
                    str(offset_seconds),
                    "-i",
                    str(resolved),
                    "-vn",
                    "-af",
                    f"volume={clamp(volume)}",
                    "-f",
                    "pulse",
                    "default",
                ]
            )
        elif player == "ffplay":
            ffplay_exec = ffplay_path or "ffplay"
            command = [
                ffplay_exec,
                "-nodisp",
                "-loglevel",
                "error",
                "-ss",
                str(offset_seconds),
                "-af",
                f"volume={clamp(volume)}",
            ]
            if loop:
                # ffplay on Steam Deck does not support -stream_loop; use -loop 0.
                command.extend(["-loop", "0"])
            else:
                command.append("-autoexit")
            command.append(str(resolved))
        else:
            raise RuntimeError(f"Unsupported backend player selection: {player}")

        decky.logger.info(
            "play_track_backend start "
            f"player={player} path={resolved} "
            f"ffplay={ffplay_path} ffmpeg={self._find_command_path('ffmpeg')} "
            f"mpv={self._find_command_path('mpv')} mpg123={self._find_command_path('mpg123')}"
        )
        self._settings_dir.mkdir(parents=True, exist_ok=True)
        log_handle = self._playback_log_file.open("ab")
        log_handle.write(
            f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] start player={player} path={resolved}\n".encode(
                "utf-8", errors="ignore"
            )
        )
        log_handle.flush()
        process = subprocess.Popen(
            command,
            stdout=log_handle,
            stderr=log_handle,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            env=self._build_backend_audio_env(),
        )
        self._playback_process = process
        self._playback_player = player
        self._playback_started_at = time.time()
        self._playback_start_offset = offset_seconds
        threading.Thread(
            target=self._monitor_playback_process,
            args=(process, player, str(resolved), log_handle),
            daemon=True,
        ).start()
        return {
            "ok": True,
            "pid": process.pid,
            "player": player,
            "path": str(resolved),
            "loop": bool(loop),
            "volume": clamp(volume),
            "start_offset": offset_seconds,
        }

    async def stop_backend_playback(self) -> dict[str, Any]:
        stopped = self._stop_playback_process()
        return {"ok": True, "stopped": stopped}

    async def get_backend_playback_state(self) -> dict[str, Any]:
        process = self._playback_process
        running = bool(process and process.poll() is None)
        elapsed = 0.0
        if running:
            elapsed = max(0.0, time.time() - self._playback_started_at)
        return {
            "running": running,
            "player": self._playback_player,
            "pid": process.pid if process else None,
            "elapsed": elapsed,
            "start_offset": self._playback_start_offset,
        }

    async def log_client_event(
        self, level: str, message: str, payload: dict[str, Any] | None = None
    ) -> bool:
        level_name = str(level or "info").strip().lower()
        normalized_message = self._trim_message(str(message or "").strip() or "event", 240)
        payload_suffix = ""
        if payload is not None:
            try:
                payload_text = json.dumps(payload, ensure_ascii=True, sort_keys=True)
            except Exception:
                payload_text = repr(payload)
            payload_suffix = f" payload={self._trim_message(payload_text, 1400)}"
        line = f"[client] {normalized_message}{payload_suffix}"
        if level_name == "error":
            decky.logger.error(line)
        elif level_name in {"warn", "warning"}:
            decky.logger.warning(line)
        elif level_name == "debug":
            decky.logger.debug(line)
        else:
            decky.logger.info(line)
        self._write_debug_log(level_name, line)
        return True

    async def get_localconfig_app_ids(self) -> dict[str, Any]:
        return {"app_ids": self._read_localconfig_app_ids()}

    async def get_steam_library_games(self) -> dict[str, Any]:
        games, installed_app_ids = await asyncio.to_thread(self._read_steam_library_games)
        return {
            "games": games,
            "installed_app_ids": sorted(installed_app_ids),
        }

    async def resolve_store_app_names(self, app_ids: list[int]) -> dict[str, str]:
        unique_ids = sorted(
            {
                int(value)
                for value in app_ids or []
                if isinstance(value, (int, float, str)) and str(value).strip()
            }
        )
        unique_ids = [app_id for app_id in unique_ids if app_id > 0]
        if not unique_ids:
            return {}

        resolved: dict[str, str] = {}
        chunk_size = 20
        for index in range(0, len(unique_ids), chunk_size):
            chunk = unique_ids[index : index + chunk_size]
            try:
                resolved.update(
                    await asyncio.to_thread(self._resolve_store_app_names_chunk, chunk)
                )
            except Exception as error:
                decky.logger.error(
                    f"resolve_store_app_names chunk failed ({chunk[0]}..{chunk[-1]}): {error}"
                )

        unresolved_ids = [app_id for app_id in unique_ids if str(app_id) not in resolved]
        if unresolved_ids:
            decky.logger.info(
                f"resolve_store_app_names falling back for {len(unresolved_ids)} app ids"
            )

            semaphore = asyncio.Semaphore(2)

            async def resolve_one(app_id: int) -> tuple[int, str | None]:
                async with semaphore:
                    try:
                        community_name = await asyncio.to_thread(
                            self._resolve_steamcommunity_app_name, app_id
                        )
                        if community_name:
                            return app_id, community_name
                    except Exception as error:
                        decky.logger.error(
                            f"resolve_steamcommunity_app_name failed ({app_id}): {error}"
                        )
                    return app_id, None

            resolved_pairs = await asyncio.gather(
                *(resolve_one(app_id) for app_id in unresolved_ids)
            )
            for app_id, name in resolved_pairs:
                if name:
                    resolved[str(app_id)] = name
        return resolved

    @staticmethod
    def _playlist_entries(track: dict[str, Any]) -> list[dict[str, Any]]:
        return [{k: v for k, v in track.items() if k != "additional_tracks"},
                *track.get("additional_tracks", [])] if track.get("path") else []

    def _append_track(self, key: str, track: dict[str, Any]) -> None:
        previous = self._tracks.get(key)
        if not previous:
            self._tracks[key] = track
            return
        entries = self._playlist_entries(previous)
        # Adding the same file again is harmless and does not duplicate it.
        if any(item["path"] == track["path"] for item in entries):
            return
        self._tracks[key] = {**previous, "additional_tracks": [*entries[1:], track]}

    def _keep_playlist_entries(self, key: str, entries: list[dict[str, Any]]) -> None:
        if not entries:
            self._tracks.pop(key, None)
            return
        previous = self._tracks[key]
        self._tracks[key] = {**entries[0],
                             **{name: previous[name] for name in ("volume", "start_offset", "loop") if name in previous},
                             "additional_tracks": entries[1:]}

    async def move_playlist_track(self, key: str, path: str, direction: int) -> dict[str, dict[str, Any]]:
        if direction not in (-1, 1):
            raise ValueError("Invalid playlist direction")
        if key not in self._tracks:
            raise ValueError("Playlist no longer exists")
        entries = self._playlist_entries(self._tracks[key])
        index = next((i for i, item in enumerate(entries) if item["path"] == path), None)
        if index is None:
            raise ValueError("Song no longer exists in this playlist")
        destination = index + direction
        if not 0 <= destination < len(entries):
            return self._tracks
        entries[index], entries[destination] = entries[destination], entries[index]
        previous = self._tracks.copy()
        self._keep_playlist_entries(key, entries)
        try:
            self._save_tracks()
        except Exception:
            self._tracks = previous
            raise
        return self._tracks

    async def remove_playlist_track(self, key: str, path: str) -> dict[str, dict[str, Any]]:
        previous = self._tracks.copy()
        if key in self._tracks:
            self._keep_playlist_entries(key, [item for item in self._playlist_entries(self._tracks[key]) if item["path"] != path])
        try:
            self._save_tracks()
        except Exception:
            self._tracks = previous
            raise
        return self._tracks

    async def set_track(
        self, app_id: int, path: str, filename: str
    ) -> dict[str, dict[str, Any]]:
        key = str(app_id)
        decky.logger.info(f"set_track request app={app_id} path={path}")
        try:
            resolved = Path(path).expanduser().resolve()
            if not resolved.exists() or not resolved.is_file():
                raise ValueError(f"File not found or inaccessible: {resolved}")
            try:
                resolved.open("rb").close()
            except PermissionError as error:
                raise PermissionError(f"Permission denied: {resolved}") from error
            self._append_track(key, {
                "app_id": app_id,
                "assigned_at": time.time(),
                "path": str(resolved),
                "filename": filename,
                "volume": self._tracks.get(key, {}).get("volume", 1.0),
                "start_offset": self._tracks.get(key, {}).get("start_offset", 0.0),
                "loop": bool(self._tracks.get(key, {}).get("loop", True)),
            })
            self._save_tracks()
            decky.logger.info(f"set_track stored app={app_id} path={resolved}")
            return self._tracks
        except Exception as error:
            decky.logger.error(
                f"set_track failed app={app_id} path={path}: {error}"
            )
            raise

    async def load_track_audio(self, path: str) -> dict[str, Any]:
        resolved = Path(path).expanduser().resolve()
        decky.logger.info(f"load_track_audio path={resolved}")
        if not resolved.exists() or not resolved.is_file():
            raise FileNotFoundError(f"Audio file not found: {resolved}")

        try:
            data = resolved.read_bytes()
        except PermissionError as error:
            raise PermissionError(f"Permission denied: {resolved}") from error

        suffix = resolved.suffix.lower().lstrip(".")
        mime = {
            "mp3": "audio/mpeg",
            "aac": "audio/aac",
            "flac": "audio/flac",
            "ogg": "audio/ogg",
            "wav": "audio/wav",
            "m4a": "audio/mp4",
        }.get(suffix, "application/octet-stream")

        encoded = base64.b64encode(data).decode("ascii")
        stats = resolved.stat()
        decky.logger.info(
            f"load_track_audio served bytes={len(data)} mtime={stats.st_mtime}"
        )
        return {"data": encoded, "mime": mime, "mtime": stats.st_mtime}

    async def set_volume(
        self, app_id: int, volume: float
    ) -> dict[str, dict[str, Any]]:
        key = str(app_id)
        if key not in self._tracks:
            raise ValueError(f"No track found for app {app_id}")
        self._tracks[key]["volume"] = clamp(volume)
        self._save_tracks()
        return self._tracks

    async def set_start_offset(
        self, app_id: int, start_offset: float
    ) -> dict[str, dict[str, Any]]:
        key = str(app_id)
        if key not in self._tracks:
            raise ValueError(f"No track found for app {app_id}")
        self._tracks[key]["start_offset"] = clamp_seconds(start_offset)
        self._save_tracks()
        return self._tracks

    async def set_loop(self, app_id: int, loop: bool) -> dict[str, dict[str, Any]]:
        key = str(app_id)
        if key not in self._tracks:
            raise ValueError(f"No track found for app {app_id}")
        self._tracks[key]["loop"] = bool(loop)
        self._save_tracks()
        return self._tracks

    async def remove_track(self, app_id: int) -> dict[str, dict[str, Any]]:
        self._tracks.pop(str(app_id), None)
        self._save_tracks()
        return self._tracks

    def _storage_path(self, file_id: str) -> Path:
        """Accept only relative IDs under our own non-symlink storage trees."""
        relative = Path(file_id)
        if relative.is_absolute() or ".." in relative.parts or len(relative.parts) < 2:
            raise ValueError("Invalid storage file")
        root = {"downloads": self._downloads_dir, "previews": self._preview_dir}.get(relative.parts[0])
        if root is None or root.is_symlink():
            raise ValueError("Only ThemeDeck downloads and previews can be deleted")
        candidate = root
        for part in relative.parts[1:]:
            candidate = candidate / part
            if candidate.is_symlink():
                raise ValueError("Symbolic links cannot be managed")
        if not candidate.resolve().is_relative_to(root.resolve()):
            raise ValueError("File is outside ThemeDeck storage")
        return candidate

    def _storage_references(self, path: Path) -> list[str]:
        resolved = path.resolve()
        return [key for key, track in self._tracks.items()
                if any(Path(item["path"]).expanduser().resolve() == resolved for item in self._playlist_entries(track))]

    async def get_song_storage(self) -> dict[str, Any]:
        files: list[dict[str, Any]] = []
        references: dict[Path, list[str]] = {}
        missing: list[str] = []
        for key, track in self._tracks.items():
            for item in self._playlist_entries(track):
                path = Path(item["path"]).expanduser().resolve()
                references.setdefault(path, []).append(key)
                if not path.is_file() and key not in missing:
                    missing.append(key)
        for category, root in (("downloads", self._downloads_dir), ("previews", self._preview_dir)):
            if not root.exists() or root.is_symlink():
                continue
            for directory, dirs, names in os.walk(root, followlinks=False):
                dirs[:] = [name for name in dirs if not (Path(directory) / name).is_symlink()]
                for name in names:
                    path = Path(directory) / name
                    file_id = str(Path(category) / path.relative_to(root))
                    try:
                        self._storage_path(file_id)
                        if not path.is_file():
                            continue
                        size = path.stat().st_size
                        refs = references.get(path.resolve(), [])
                    except (OSError, ValueError):
                        continue
                    files.append({"id": file_id, "name": name, "path": str(path),
                                  "category": category, "bytes": size, "assignments": refs})
        files.sort(key=lambda item: (-item["bytes"], item["id"]))
        return {"files": files, "total_bytes": sum(item["bytes"] for item in files),
                "download_bytes": sum(item["bytes"] for item in files if item["category"] == "downloads"),
                "preview_bytes": sum(item["bytes"] for item in files if item["category"] == "previews"),
                "unused_bytes": sum(item["bytes"] for item in files if not item["assignments"]),
                "missing_assignments": missing, "busy": self._storage_lock.locked()}

    def _delete_storage_file(
        self, file_id: str, remove_assignments: bool, known_refs: list[str] | None = None
    ) -> int:
        path = self._storage_path(file_id)
        refs = self._storage_references(path) if known_refs is None else known_refs
        if refs and not remove_assignments:
            raise ValueError("This file is assigned. Confirm removal of its assignments first.")
        if path.exists() and not path.is_file():
            raise ValueError("Select a file, not a folder")
        size = path.stat().st_size if path.exists() else 0
        previous = self._tracks.copy()
        for key in refs:
            self._keep_playlist_entries(key, [item for item in self._playlist_entries(self._tracks[key])
                                              if Path(item["path"]).expanduser().resolve() != path.resolve()])
        # Save before deleting; restore assignments if saving/deleting fails.
        try:
            if refs:
                self._save_tracks()
            path.unlink(missing_ok=True)
        except Exception:
            self._tracks = previous
            if refs:
                self._save_tracks()
            raise
        parent = path.parent
        root = self._downloads_dir if file_id.startswith("downloads/") else self._preview_dir
        while parent != root and parent.is_relative_to(root):
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
        return size

    async def delete_song_storage(
        self, file_id: str, remove_assignments: bool = False,
        expected_assignments: list[str] | None = None,
    ) -> dict[str, Any]:
        if self._storage_lock.locked():
            raise RuntimeError("A preview or download is in progress. Wait for it to finish before deleting files.")
        async with self._storage_lock:
            if expected_assignments is not None:
                actual = self._storage_references(self._storage_path(file_id))
                if set(actual) != set(expected_assignments):
                    raise ValueError("This file's assignments changed. Refresh storage and review them before deleting.")
            freed = self._delete_storage_file(file_id, remove_assignments)
        return {"freed_bytes": freed, "storage": await self.get_song_storage()}

    async def clean_song_storage(self, category: str) -> dict[str, Any]:
        if category not in {"previews", "unused"}:
            raise ValueError("Invalid cleanup category")
        if self._storage_lock.locked():
            raise RuntimeError("A preview or download is in progress. Wait for it to finish before cleaning storage.")
        freed = 0
        deleted = 0
        errors: list[str] = []
        async with self._storage_lock:
            storage = await self.get_song_storage()
            for item in storage["files"]:
                if item["assignments"] or (category == "previews" and item["category"] != "previews"):
                    continue
                try:
                    freed += self._delete_storage_file(item["id"], False, [])
                    deleted += 1
                except (OSError, ValueError) as error:
                    errors.append(f"{item['name']}: {error}")
        return {"freed_bytes": freed, "deleted": deleted, "errors": errors,
                "storage": await self.get_song_storage()}

    async def clear_missing_song_assignments(self) -> dict[str, Any]:
        # Clears broken references only; never deletes files, including local music.
        missing = (await self.get_song_storage())["missing_assignments"]
        previous = self._tracks.copy()
        for key in missing:
            self._keep_playlist_entries(key, [item for item in self._playlist_entries(self._tracks[key])
                                              if Path(item["path"]).expanduser().is_file()])
        try:
            self._save_tracks()
        except Exception:
            self._tracks = previous
            raise
        return await self.get_song_storage()

    async def get_track(self, app_id: int) -> dict[str, Any] | None:
        return self._tracks.get(str(app_id))

    async def get_global_track(self) -> dict[str, Any] | None:
        return self._tracks.get(self._global_track_key)

    async def set_global_track(self, path: str, filename: str) -> dict[str, Any]:
        decky.logger.info(f"set_global_track request path={path}")
        try:
            resolved = Path(path).expanduser().resolve()
            if not resolved.exists() or not resolved.is_file():
                raise ValueError(f"File not found or inaccessible: {resolved}")
            try:
                resolved.open("rb").close()
            except PermissionError as error:
                raise PermissionError(f"Permission denied: {resolved}") from error
            previous = self._tracks.get(self._global_track_key, {})
            self._append_track(self._global_track_key, {
                "scope": "global",
                "assigned_at": time.time(),
                "path": str(resolved),
                "filename": filename,
                "volume": previous.get("volume", 1.0),
                "start_offset": previous.get("start_offset", 0.0),
                "loop": bool(previous.get("loop", True)),
            })
            self._save_tracks()
            return self._tracks[self._global_track_key]
        except Exception as error:
            decky.logger.error(f"set_global_track failed path={path}: {error}")
            raise

    async def set_global_volume(self, volume: float) -> dict[str, Any]:
        if self._global_track_key not in self._tracks:
            raise ValueError("No global track found")
        self._tracks[self._global_track_key]["volume"] = clamp(volume)
        self._save_tracks()
        return self._tracks[self._global_track_key]

    async def set_global_start_offset(self, start_offset: float) -> dict[str, Any]:
        if self._global_track_key not in self._tracks:
            raise ValueError("No global track found")
        self._tracks[self._global_track_key]["start_offset"] = clamp_seconds(
            start_offset
        )
        self._save_tracks()
        return self._tracks[self._global_track_key]

    async def set_global_loop(self, loop: bool) -> dict[str, Any]:
        if self._global_track_key not in self._tracks:
            raise ValueError("No global track found")
        self._tracks[self._global_track_key]["loop"] = bool(loop)
        self._save_tracks()
        return self._tracks[self._global_track_key]

    async def remove_global_track(self) -> dict[str, dict[str, Any]]:
        self._tracks.pop(self._global_track_key, None)
        self._save_tracks()
        return self._tracks

    async def get_store_track(self) -> dict[str, Any] | None:
        return self._tracks.get(self._store_track_key)

    async def set_store_track(self, path: str, filename: str) -> dict[str, Any]:
        decky.logger.info(f"set_store_track request path={path}")
        try:
            resolved = Path(path).expanduser().resolve()
            if not resolved.exists() or not resolved.is_file():
                raise ValueError(f"File not found or inaccessible: {resolved}")
            try:
                resolved.open("rb").close()
            except PermissionError as error:
                raise PermissionError(f"Permission denied: {resolved}") from error
            previous = self._tracks.get(self._store_track_key, {})
            self._append_track(self._store_track_key, {
                "scope": "store",
                "assigned_at": time.time(),
                "path": str(resolved),
                "filename": filename,
                "volume": previous.get("volume", 1.0),
                "start_offset": previous.get("start_offset", 0.0),
                "loop": bool(previous.get("loop", True)),
            })
            self._save_tracks()
            return self._tracks[self._store_track_key]
        except Exception as error:
            decky.logger.error(f"set_store_track failed path={path}: {error}")
            raise

    async def set_store_volume(self, volume: float) -> dict[str, Any]:
        if self._store_track_key not in self._tracks:
            raise ValueError("No store track found")
        self._tracks[self._store_track_key]["volume"] = clamp(volume)
        self._save_tracks()
        return self._tracks[self._store_track_key]

    async def set_store_start_offset(self, start_offset: float) -> dict[str, Any]:
        if self._store_track_key not in self._tracks:
            raise ValueError("No store track found")
        self._tracks[self._store_track_key]["start_offset"] = clamp_seconds(
            start_offset
        )
        self._save_tracks()
        return self._tracks[self._store_track_key]

    async def set_store_loop(self, loop: bool) -> dict[str, Any]:
        if self._store_track_key not in self._tracks:
            raise ValueError("No store track found")
        self._tracks[self._store_track_key]["loop"] = bool(loop)
        self._save_tracks()
        return self._tracks[self._store_track_key]

    async def remove_store_track(self) -> dict[str, dict[str, Any]]:
        self._tracks.pop(self._store_track_key, None)
        self._save_tracks()
        return self._tracks

    async def list_directory(
        self, path: str | None = None
    ) -> dict[str, Any]:
        base = path or os.path.expanduser("~")
        resolved = Path(os.path.expanduser(base)).resolve()
        if not resolved.exists():
            resolved = resolved.parent
        if not resolved.exists() or not resolved.is_dir():
            resolved = Path(os.path.expanduser("~"))
        decky.logger.info(f"Listing directory: {resolved}")

        directories: list[str] = []
        files: list[str] = []

        try:
            for entry in sorted(resolved.iterdir(), key=lambda p: p.name.lower()):
                try:
                    if entry.is_dir():
                        directories.append(entry.name)
                    elif entry.is_file():
                        files.append(entry.name)
                except PermissionError:
                    continue
        except Exception as error:
            decky.logger.error(f"Failed to list directory {resolved}: {error}")

        return {
            "path": str(resolved),
            "dirs": directories,
            "files": files,
        }

    async def get_yt_dlp_status(self) -> dict[str, Any]:
        invocation = await self._working_yt_dlp_invocation()
        installed = bool(invocation)
        deno_path = self._resolve_deno_path()
        deno_version = await self._get_deno_version(deno_path) if deno_path else None
        deno_installed = bool(deno_path and self._is_supported_deno_version(deno_version))
        status: dict[str, Any] = {
            "installed": installed,
            "path": invocation["path"] if invocation else "",
            "source": "none",
            "version": "",
            "deno_installed": deno_installed,
            "deno_path": str(deno_path) if deno_path else "",
            "deno_version": deno_version or "",
            "cookies_browser": "firefox" if self._use_firefox_cookies else "",
            "firefox_cookies_enabled": self._use_firefox_cookies,
            "ready": installed and deno_installed,
        }
        if not invocation:
            self._log_info("yt-dlp status: not installed")
            return status
        status["source"] = invocation["source"]
        version = await self._get_yt_dlp_version(invocation)
        if version:
            status["version"] = version
        self._log_info(
            f"yt-dlp status source={status.get('source')} "
            f"path={status.get('path')} version={status.get('version') or 'unknown'} "
            f"deno={deno_version or 'not installed'} ready={status.get('ready')}"
        )
        return status

    async def set_youtube_firefox_cookies(self, enabled: bool) -> dict[str, Any]:
        previous = self._use_firefox_cookies
        self._use_firefox_cookies = enabled is True
        try:
            self._save_youtube_support_settings()
        except Exception:
            self._use_firefox_cookies = previous
            raise
        self._log_info(
            "YouTube Firefox cookie access "
            f"{'enabled' if self._use_firefox_cookies else 'disabled'}"
        )
        return await self.get_yt_dlp_status()

    async def _finish_youtube_support_setup(self) -> dict[str, Any]:
        deno_error = await self._ensure_deno()
        if deno_error:
            raise RuntimeError(
                f"yt-dlp installed, but Deno setup failed: {deno_error}"
            )

        status = await self.get_yt_dlp_status()
        if not status.get("installed"):
            raise RuntimeError("yt-dlp update completed but executable was not found")
        if not status.get("deno_installed"):
            raise RuntimeError("Deno setup completed but a supported executable was not found")
        return status

    async def update_yt_dlp(self) -> dict[str, Any]:
        self._log_info("yt-dlp update requested")
        self._bin_dir.mkdir(parents=True, exist_ok=True)
        venv_error = await self._install_yt_dlp_in_venv()
        if venv_error:
            self._log_warning(f"yt-dlp venv install/update failed: {venv_error}")
        else:
            self._set_preferred_yt_dlp_source("venv")
            self._log_info("yt-dlp venv install/update completed")
        status = await self.get_yt_dlp_status()
        if not venv_error and status.get("source") == "venv":
            status = await self._finish_youtube_support_setup()
            if status.get("version"):
                self._log_info(
                    "YouTube support available via "
                    f"{status.get('source')} yt-dlp {status.get('version')} and "
                    f"Deno {status.get('deno_version') or 'unknown'}"
                )
            return status

        file_descriptor, temp_name = tempfile.mkstemp(
            prefix="yt-dlp-", dir=str(self._bin_dir)
        )
        os.close(file_descriptor)
        temp_path = Path(temp_name)
        try:
            await self._download_yt_dlp_binary(temp_path)
            temp_path.chmod(0o755)
            temp_path.replace(self._yt_dlp_path)
            version = await self._get_yt_dlp_version(
                {
                    "command": [str(self._yt_dlp_path)],
                    "env": None,
                }
            )
            if not version:
                raise RuntimeError(
                    f"Installed file is not executable: {self._yt_dlp_path}"
                )
            self._set_preferred_yt_dlp_source("local")
            self._log_info(f"yt-dlp local binary updated successfully ({version})")
        except Exception as error:
            self._log_error(f"Failed to update yt-dlp local binary: {error}")
            pip_error = await self._try_install_yt_dlp_with_pip()
            if pip_error:
                self._log_warning(f"yt-dlp user pip fallback failed: {pip_error}")
            else:
                self._set_preferred_yt_dlp_source("system")
            status = await self.get_yt_dlp_status()
            if not pip_error and status.get("source") == "system":
                self._log_info("yt-dlp became available via pip/system fallback")
                return await self._finish_youtube_support_setup()
            summary = self._trim_message(str(error), 140)
            if venv_error:
                summary = self._trim_message(f"{summary}; venv: {venv_error}", 220)
            if pip_error:
                summary = self._trim_message(f"{summary}; pip: {pip_error}", 220)
            raise RuntimeError(f"Failed to update yt-dlp: {summary}") from error
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
        status = await self._finish_youtube_support_setup()
        self._log_info(
            f"yt-dlp update finished source={status.get('source')} "
            f"version={status.get('version') or 'unknown'} "
            f"deno={status.get('deno_version') or 'unknown'}"
        )
        return status

    async def search_youtube(self, query: str, limit: int = 10) -> dict[str, Any]:
        try:
            cleaned_query = (query or "").strip()
            if not cleaned_query:
                raise ValueError("Search query is required")

            yt_dlp = await self._require_yt_dlp_invocation()
            safe_limit = max(1, min(int(limit), 25))

            search_queries = self._youtube_search_candidates(cleaned_query)
            results: list[dict[str, Any]] = []
            last_stdout = ""
            for search_query in search_queries:
                self._log_info(
                    f"youtube search requested query={search_query!r} "
                    f"source={yt_dlp.get('source')} path={yt_dlp.get('path')}"
                )
                command = [
                    *yt_dlp["command"],
                    *self._youtube_access_args(),
                    "--no-warnings",
                    "--no-check-certificate",
                    "--ignore-config",
                    "--skip-download",
                    "--flat-playlist",
                    "--dump-json",
                    f"ytsearch{safe_limit}:{search_query}",
                ]
                result = await self._run_command(command, timeout=90, env=yt_dlp["env"])
                last_stdout = result.stdout or ""
                if result.returncode != 0:
                    raise RuntimeError(self._command_error(result, "YouTube search failed"))

                results = self._parse_youtube_search_json_lines(last_stdout)
                if results:
                    if search_query != cleaned_query:
                        self._log_info(
                            f"youtube search fallback succeeded original={cleaned_query!r} "
                            f"fallback={search_query!r}"
                        )
                    break

                self._log_warning(
                    f"youtube search returned no parseable results query={search_query!r} "
                    f"stdout_sample={self._trim_message(last_stdout, 500)!r}"
                )

            self._log_info(
                f"youtube search completed query={cleaned_query!r} results={len(results)}"
            )
            return {"results": results}
        except Exception as error:
            self._log_error(f"search_youtube failed query={query!r}: {error}")
            self._log_error(traceback.format_exc())
            raise

    async def get_youtube_preview_stream(self, video_url: str) -> dict[str, Any]:
        try:
            async with self._storage_lock:
                return await self._prepare_youtube_preview(video_url)
        except Exception:
            self._log_error(f"YouTube preview failed:\n{traceback.format_exc()}")
            raise

    async def _prepare_youtube_preview(self, video_url: str) -> dict[str, Any]:
        yt_dlp = await self._require_yt_dlp_invocation()
        normalized_url = self._normalize_youtube_url(video_url)
        video_id = self._extract_youtube_video_id(normalized_url)
        preview_key = re.sub(r"[^A-Za-z0-9_-]+", "_", video_id or "preview")[:80]
        preview_dir = self._preview_dir / preview_key
        preview_dir.mkdir(parents=True, exist_ok=True)
        self._log_info(f"youtube preview requested url={normalized_url} key={preview_key}")

        cached_path = self._find_latest_audio_file(preview_dir)
        if cached_path:
            self._log_info(f"youtube preview using cached file={cached_path}")
            payload = await self.load_track_audio(str(cached_path))
            payload["path"] = str(cached_path)
            return payload

        command = [
            *yt_dlp["command"],
            *self._youtube_access_args(),
            "--no-warnings",
            "--no-check-certificate",
            "--no-playlist",
            # YouTube supplies browser-playable AAC/M4A directly. Avoid the
            # MP3 postprocessor, which needs system ffmpeg/ffprobe after OS updates.
            "--ignore-config",
            "--format",
            "bestaudio[ext=m4a]",
            "--fixup",
            "never",
            "--restrict-filenames",
            "--force-overwrites",
            "--paths",
            str(preview_dir),
            "-o",
            "preview.%(ext)s",
            "--print",
            "after_move:filepath",
            normalized_url,
        ]
        result = await self._run_command(command, timeout=240, env=yt_dlp["env"])
        if result.returncode != 0:
            raise RuntimeError(
                self._command_error(result, "Failed to prepare preview audio")
            )
        output_lines = [
            line.strip() for line in (result.stdout or "").splitlines() if line.strip()
        ]
        preview_path = self._extract_downloaded_path(output_lines, preview_dir)
        if not preview_path:
            preview_path = self._find_latest_audio_file(preview_dir)
        if not preview_path:
            raise RuntimeError("Preview completed but no audio file was found")
        self._log_info(f"youtube preview prepared file={preview_path}")
        payload = await self.load_track_audio(str(preview_path))
        payload["path"] = str(preview_path)
        return payload

    async def download_youtube_audio(
        self, app_id: int, video_url: str
    ) -> dict[str, Any]:
        async with self._storage_lock:
            return await self._download_youtube_audio(app_id, video_url)

    async def _download_youtube_audio(
        self, app_id: int, video_url: str
    ) -> dict[str, Any]:
        if app_id <= 0 and app_id not in (-1, -2):
            raise ValueError("Invalid app id")

        yt_dlp = await self._require_yt_dlp_invocation()
        normalized_url = self._normalize_youtube_url(video_url)
        video_id = self._extract_youtube_video_id(normalized_url)
        key = self._global_track_key if app_id == -1 else self._store_track_key if app_id == -2 else str(app_id)
        app_download_dir = self._downloads_dir / ("global" if app_id == -1 else "store" if app_id == -2 else str(app_id))
        app_download_dir.mkdir(parents=True, exist_ok=True)
        self._log_info(
            f"youtube download requested app={app_id} url={normalized_url} "
            f"video_id={video_id} source={yt_dlp.get('source')} path={yt_dlp.get('path')}"
        )

        command = [
            *yt_dlp["command"],
            *self._youtube_access_args(),
            "--no-warnings",
            "--no-check-certificate",
            "--no-playlist",
            # YouTube supplies browser-playable AAC/M4A directly. Avoid the
            # MP3 postprocessor, which needs system ffmpeg/ffprobe after OS updates.
            "--ignore-config",
            "--format",
            "bestaudio[ext=m4a]",
            "--fixup",
            "never",
            "--restrict-filenames",
            "--force-overwrites",
            "--paths",
            str(app_download_dir),
            "-o",
            "%(title).150B [%(id)s].%(ext)s",
            "--print",
            "after_move:filepath",
            normalized_url,
        ]
        result = await self._run_command(command, timeout=900, env=yt_dlp["env"])
        if result.returncode != 0:
            raise RuntimeError(
                self._command_error(result, "YouTube download failed")
            )

        output_lines = [
            line.strip() for line in (result.stdout or "").splitlines() if line.strip()
        ]
        downloaded_path = self._extract_downloaded_path(output_lines, app_download_dir)
        if not downloaded_path:
            downloaded_path = self._find_latest_audio_file(app_download_dir)
        if not downloaded_path:
            raise RuntimeError("Download completed but no audio file was found")

        if app_id == -1:
            await self.set_global_track(str(downloaded_path), downloaded_path.name)
        elif app_id == -2:
            await self.set_store_track(str(downloaded_path), downloaded_path.name)
        else:
            await self.set_track(app_id, str(downloaded_path), downloaded_path.name)
        tracks = self._tracks
        root = self._tracks[key]
        target = root if root["path"] == str(downloaded_path) else next(item for item in root.get("additional_tracks", []) if item["path"] == str(downloaded_path))
        target["youtube_id"] = video_id
        self._save_tracks()
        self._log_info(f"youtube download assigned app={app_id} file={downloaded_path}")
        return {
            "tracks": tracks,
            "path": str(downloaded_path),
            "filename": downloaded_path.name,
        }

    @staticmethod
    def _file_creation_timestamp(path: Path) -> float | None:
        """Read birth time; never substitute modified/change times for creation."""
        try:
            info = path.stat()
            if not path.is_file():
                return None
            created = getattr(info, "st_birthtime", None)
            if created is None and sys.platform.startswith("linux"):
                # Python's Linux stat omits birth time; GNU stat reads it via statx.
                result = subprocess.run(
                    ["stat", "--format=%W", "--", str(path)],
                    capture_output=True, text=True, timeout=2, check=False,
                )
                if result.returncode == 0:
                    created = float(result.stdout.strip())
            if isinstance(created, (int, float)) and math.isfinite(created) and created > 0:
                return float(created)
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
        return None

    def _recover_assignment_date(self, key: str, track: dict[str, Any]) -> bool:
        saved = track.get("assigned_at")
        if isinstance(saved, (int, float)) and math.isfinite(saved) and saved > 0:
            return False
        if not key.isdigit() or int(key) <= 0 or not track.get("path"):
            return False
        path = Path(track["path"]).expanduser()
        try:
            # Older downloads may lack youtube_id, but their per-game download
            # directory still identifies them as ThemeDeck downloads.
            downloaded = path.resolve().is_relative_to(
                (self._downloads_dir / key).resolve()
            )
        except (OSError, ValueError):
            downloaded = False
        if not track.get("youtube_id") and not downloaded:
            return False
        created = self._file_creation_timestamp(path)
        if created is None:
            return False
        track["assigned_at"] = created
        track["assigned_at_estimated"] = True
        track["assigned_at_source"] = "file_creation"
        return True

    def _load_tracks(self) -> None:
        if not self._tracks_file.exists():
            self._tracks = {}
            return

        try:
            with self._tracks_file.open("r", encoding="utf-8") as handle:
                self._tracks = json.load(handle)
            changed = False
            for key, track in list(self._tracks.items()):
                if not isinstance(track, dict):
                    continue
                if self._recover_assignment_date(key, track):
                    changed = True
                if "loop" not in track:
                    track["loop"] = True
                    changed = True
            if changed:
                self._save_tracks()
        except Exception as error:
            decky.logger.error(f"Failed to read tracks.json: {error}")

    def _load_youtube_support_settings(self) -> None:
        self._use_firefox_cookies = False
        self._preferred_yt_dlp_source = "venv"
        if not self._youtube_support_settings_file.exists():
            return

        try:
            with self._youtube_support_settings_file.open(
                "r", encoding="utf-8"
            ) as handle:
                settings = json.load(handle)
            if not isinstance(settings, dict):
                raise ValueError("settings root must be an object")
            self._use_firefox_cookies = settings.get("use_firefox_cookies") is True
            preferred_source = settings.get("preferred_yt_dlp_source")
            if preferred_source in {"venv", "local", "system"}:
                self._preferred_yt_dlp_source = preferred_source
        except Exception as error:
            decky.logger.error(f"Failed to read youtube-support.json: {error}")

    def _resolve_audio_player(self) -> str | None:
        if self._find_command_path("ffplay"):
            return "ffplay"
        if self._find_command_path("ffmpeg"):
            return "ffmpeg"
        if self._find_command_path("mpv"):
            return "mpv"
        if self._find_command_path("mpg123"):
            return "mpg123"
        return None

    def _find_command_path(self, command: str) -> str | None:
        resolved = shutil.which(command)
        if resolved:
            return resolved
        direct = Path("/usr/bin") / command
        if direct.exists() and os.access(direct, os.X_OK):
            return str(direct)
        return None

    def _build_backend_audio_env(self) -> dict[str, str]:
        env = dict(os.environ)
        uid = os.getuid()
        runtime_dir = env.get("XDG_RUNTIME_DIR") or f"/run/user/{uid}"
        env["XDG_RUNTIME_DIR"] = runtime_dir
        pulse_native = Path(runtime_dir) / "pulse" / "native"
        if pulse_native.exists():
            env["PULSE_SERVER"] = f"unix:{pulse_native}"
        return env

    def _stop_playback_process(self) -> bool:
        process = self._playback_process
        self._playback_process = None
        self._playback_player = None
        if not process:
            return False
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=1.0)
                except Exception:
                    process.kill()
                    process.wait(timeout=1.0)
            else:
                # Reap exited child to avoid zombies.
                process.wait(timeout=0.1)
            return True
        except Exception as error:
            decky.logger.error(f"Failed stopping backend playback process: {error}")
            return False

    def _monitor_playback_process(
        self,
        process: subprocess.Popen[bytes],
        player: str,
        path: str,
        log_handle: Any,
    ) -> None:
        try:
            return_code = process.wait()
            decky.logger.info(
                f"backend playback exited player={player} rc={return_code} path={path}"
            )
            try:
                log_handle.write(
                    f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] exit rc={return_code}\n".encode(
                        "utf-8", errors="ignore"
                    )
                )
                log_handle.flush()
            except Exception:
                pass
        except Exception as error:
            decky.logger.error(f"backend playback monitor failed: {error}")
        finally:
            try:
                log_handle.close()
            except Exception:
                pass
            if self._playback_process is process:
                self._playback_process = None
                self._playback_player = None

    def _save_tracks(self) -> None:
        # Storage deletion must not proceed after a silent/partial settings write.
        descriptor, temp_name = tempfile.mkstemp(prefix="tracks-", suffix=".tmp", dir=self._tracks_file.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(self._tracks, handle, indent=2, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self._tracks_file)
        except Exception as error:
            decky.logger.error(f"Failed to save tracks.json: {error}")
            raise
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def _save_youtube_support_settings(self) -> None:
        self._settings_dir.mkdir(parents=True, exist_ok=True)
        settings = {
            "use_firefox_cookies": self._use_firefox_cookies,
            "preferred_yt_dlp_source": self._preferred_yt_dlp_source,
        }
        fd, name = tempfile.mkstemp(prefix="youtube-support-", dir=str(self._settings_dir))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(settings, handle, indent=2)
            Path(name).replace(self._youtube_support_settings_file)
        finally:
            Path(name).unlink(missing_ok=True)

    def _set_preferred_yt_dlp_source(self, source: str) -> None:
        if source not in {"venv", "local", "system"}:
            raise ValueError(f"Unsupported yt-dlp source: {source}")
        self._preferred_yt_dlp_source = source
        self._save_youtube_support_settings()

    def _write_debug_log(self, level: str, message: str) -> None:
        try:
            self._debug_log_file.parent.mkdir(parents=True, exist_ok=True)
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            with self._debug_log_file.open("a", encoding="utf-8") as handle:
                handle.write(f"[{timestamp}] [{level.upper()}] {message}\n")
        except Exception:
            pass

    def _log_info(self, message: str) -> None:
        decky.logger.info(message)
        self._write_debug_log("info", message)

    def _log_warning(self, message: str) -> None:
        decky.logger.warning(message)
        self._write_debug_log("warning", message)

    def _log_error(self, message: str) -> None:
        decky.logger.error(message)
        self._write_debug_log("error", message)

    def _read_localconfig_app_ids(self) -> list[int]:
        candidates = [
            Path.home() / ".local" / "share" / "Steam" / "userdata",
            Path.home() / ".steam" / "steam" / "userdata",
        ]
        app_ids: set[int] = set()
        for base in candidates:
            if not base.exists():
                continue
            try:
                for user_dir in base.iterdir():
                    if not user_dir.is_dir():
                        continue
                    localconfig = user_dir / "config" / "localconfig.vdf"
                    if not localconfig.exists() or not localconfig.is_file():
                        continue
                    app_ids.update(self._extract_app_ids_from_localconfig(localconfig))
            except Exception as error:
                decky.logger.error(
                    f"Failed scanning localconfig under {base}: {error}"
                )
        return sorted(app_ids)

    def _read_steam_library_games(self) -> tuple[list[dict[str, Any]], set[int]]:
        by_id: dict[int, dict[str, Any]] = {}
        installed_app_ids: set[int] = set()

        def add_game(app_id: int, name: str | None = None, installed: bool = False) -> None:
            if app_id <= 0:
                return
            existing = by_id.get(app_id)
            clean_name = self._trim_message(str(name or "").strip(), 180)
            if not clean_name:
                clean_name = f"App {app_id}"
            if existing is None:
                by_id[app_id] = {"appid": app_id, "name": clean_name}
            elif existing["name"].startswith("App ") and not clean_name.startswith("App "):
                existing["name"] = clean_name
            if installed:
                installed_app_ids.add(app_id)

        for app_id in self._read_localconfig_app_ids():
            add_game(app_id)

        for steam_root in self._get_steam_roots():
            for library_path in self._read_steam_library_paths(steam_root):
                manifest_dir = library_path / "steamapps"
                if not manifest_dir.exists():
                    continue
                try:
                    manifests = list(manifest_dir.glob("appmanifest_*.acf"))
                except Exception as error:
                    decky.logger.error(
                        f"Failed listing Steam app manifests under {manifest_dir}: {error}"
                    )
                    continue
                for manifest in manifests:
                    app_id, name = self._read_appmanifest_summary(manifest)
                    if app_id > 0:
                        add_game(app_id, name, installed=True)

        games = sorted(by_id.values(), key=lambda game: str(game["name"]).lower())
        self._log_info(
            f"Steam library filesystem scan found games={len(games)} installed={len(installed_app_ids)}"
        )
        return games, installed_app_ids

    def _get_steam_roots(self) -> list[Path]:
        candidates = [
            Path.home() / ".local" / "share" / "Steam",
            Path.home() / ".steam" / "steam",
        ]
        seen: set[Path] = set()
        roots: list[Path] = []
        for candidate in candidates:
            try:
                resolved = candidate.expanduser().resolve()
            except Exception:
                resolved = candidate
            if resolved in seen or not resolved.exists():
                continue
            seen.add(resolved)
            roots.append(resolved)
        return roots

    def _read_steam_library_paths(self, steam_root: Path) -> list[Path]:
        paths: list[Path] = [steam_root]
        libraryfolders = steam_root / "steamapps" / "libraryfolders.vdf"
        try:
            text = libraryfolders.read_text(encoding="utf-8", errors="ignore")
        except FileNotFoundError:
            return paths
        except Exception as error:
            decky.logger.error(f"Failed reading Steam libraryfolders {libraryfolders}: {error}")
            return paths

        for match in re.finditer(r'"path"\s+"([^"]+)"', text, flags=re.IGNORECASE):
            raw_path = match.group(1).replace("\\\\", "\\")
            path = Path(raw_path).expanduser()
            if not path.is_absolute():
                path = steam_root / path
            try:
                resolved = path.resolve()
            except Exception:
                resolved = path
            if resolved not in paths:
                paths.append(resolved)
        return paths

    def _read_appmanifest_summary(self, path: Path) -> tuple[int, str | None]:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as error:
            decky.logger.error(f"Failed reading app manifest {path}: {error}")
            return 0, None

        app_id = 0
        name: str | None = None
        app_id_match = re.search(r'"appid"\s+"(\d+)"', text, flags=re.IGNORECASE)
        name_match = re.search(r'"name"\s+"([^"]*)"', text, flags=re.IGNORECASE)
        if app_id_match:
            try:
                app_id = int(app_id_match.group(1))
            except ValueError:
                app_id = 0
        if name_match:
            name = name_match.group(1).strip()
        return app_id, name

    def _extract_app_ids_from_localconfig(self, path: Path) -> set[int]:
        app_ids: set[int] = set()
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception as error:
            decky.logger.error(f"Failed reading localconfig {path}: {error}")
            return app_ids

        current_section: str | None = None
        pending_section: str | None = None
        depth = 0
        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue

            if current_section is None:
                section_match = re.fullmatch(r'"([^"]+)"', line)
                # Only trust the localconfig "apps" section. "apptickets" includes
                # alias/internal ticket ids that can map to the same canonical app.
                if section_match and section_match.group(1).lower() in {"apps"}:
                    pending_section = section_match.group(1).lower()
                    continue
                if pending_section and line == "{":
                    current_section = pending_section
                    pending_section = None
                    depth = 1
                    continue
                pending_section = None
                continue

            if line == "{":
                depth += 1
                continue
            if line == "}":
                depth -= 1
                if depth <= 0:
                    current_section = None
                    depth = 0
                continue

            if depth == 1:
                match = re.match(r'^"(\d{1,7})"', line)
                if match:
                    try:
                        app_id = int(match.group(1))
                    except ValueError:
                        continue
                    if app_id > 0:
                        app_ids.add(app_id)

        return app_ids

    def _resolve_store_app_names_chunk(self, app_ids: list[int]) -> dict[str, str]:
        if not app_ids:
            return {}
        resolved: dict[str, str] = {}
        for app_id in app_ids:
            if app_id <= 0:
                continue
            name = self._resolve_store_app_name_single(app_id)
            if name:
                resolved[str(app_id)] = name
        return resolved

    def _resolve_store_app_name_single(self, app_id: int) -> str | None:
        if app_id <= 0:
            return None
        context = ssl._create_unverified_context()
        url = (
            "https://store.steampowered.com/api/appdetails"
            f"?appids={app_id}&filters=basic&l=english"
        )
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "ThemeDeck/2.5.0 (+Decky Loader)"},
        )
        try:
            with urllib.request.urlopen(request, timeout=10, context=context) as response:
                payload = json.loads(response.read().decode("utf-8", errors="ignore"))
        except Exception:
            return None

        if not isinstance(payload, dict):
            return None
        value = payload.get(str(app_id))
        if not isinstance(value, dict) or not value.get("success"):
            return None
        data = value.get("data")
        if not isinstance(data, dict):
            return None
        name = data.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
        return None

    def _resolve_steamcommunity_app_name(self, app_id: int) -> str | None:
        if app_id <= 0:
            return None

        url = f"https://steamcommunity.com/app/{app_id}/?l=english"
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) ThemeDeck/2.5.0",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        context = ssl._create_unverified_context()
        try:
            with urllib.request.urlopen(request, timeout=10, context=context) as response:
                final_url = response.geturl()
                payload = response.read().decode("utf-8", errors="ignore")
        except urllib.error.HTTPError as error:
            # Steam Community rate-limits occasionally; skip quietly.
            if error.code == 429:
                return None
            raise

        canonical_match = re.search(r"/app/(\d+)", final_url or "", re.IGNORECASE)
        if canonical_match:
            canonical_app_id = int(canonical_match.group(1))
            if canonical_app_id > 0:
                # Secondary safety: normalize redirect/alias ids to canonical app id.
                canonical_name = self._resolve_store_app_name_single(canonical_app_id)
                if canonical_name:
                    return canonical_name

        title_match = re.search(
            r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
            payload,
            re.IGNORECASE,
        )
        if not title_match:
            title_match = re.search(
                r"<title>(.*?)</title>", payload, re.IGNORECASE | re.DOTALL
            )
        if not title_match:
            return None

        raw_title = html_lib.unescape(title_match.group(1)).strip()
        if not raw_title:
            return None

        cleaned = re.sub(r"^\s*Steam Community\s*::\s*", "", raw_title, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+on\s+Steam\s*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*::\s*Steam Community\s*$", "", cleaned, flags=re.IGNORECASE)
        if cleaned.lower() in {"steam community", "error", "access denied"}:
            return None
        cleaned = cleaned.strip()
        if not cleaned:
            return None
        return cleaned

    def _resolve_yt_dlp_invocation(
        self, excluded: set[str] | None = None
    ) -> dict[str, Any] | None:
        excluded = excluded or set()
        candidates = {
            "venv": [str(self._yt_venv_yt_dlp)],
            "local": [str(self._yt_dlp_path)],
            "system": [shutil.which("yt-dlp"), str(Path.home() / ".local" / "bin" / "yt-dlp")],
        }
        order = ["venv", "system", "local"]
        preferred = self._preferred_yt_dlp_source
        if preferred in order:
            order.remove(preferred)
            order.insert(0, preferred)
        for source in order:
            for path in candidates[source]:
                if path and path not in excluded and Path(path).exists() and os.access(path, os.X_OK):
                    return {"command": [path], "env": None, "source": source, "path": path}
        return None

    def _resolve_deno_path(self) -> Path | None:
        candidates: list[Path] = [self._deno_path]
        system_deno = shutil.which("deno")
        if system_deno:
            candidates.append(Path(system_deno))
        candidates.extend(
            [
                Path.home() / ".deno" / "bin" / "deno",
                Path("/home/deck/.deno/bin/deno"),
            ]
        )

        seen: set[str] = set()
        for candidate in candidates:
            candidate_text = str(candidate)
            if candidate_text in seen:
                continue
            seen.add(candidate_text)
            if candidate.exists() and os.access(candidate, os.X_OK):
                return candidate
        return None

    def _youtube_access_args(self) -> list[str]:
        args: list[str] = []
        if self._use_firefox_cookies:
            args.extend(["--cookies-from-browser", "firefox"])
        deno_path = self._resolve_deno_path()
        if deno_path:
            args.extend(["--js-runtimes", f"deno:{deno_path}"])
        return args

    async def _working_yt_dlp_invocation(self) -> dict[str, Any] | None:
        # Executable permission does not prove that a script's Python still works.
        excluded: set[str] = set()
        while invocation := self._resolve_yt_dlp_invocation(excluded):
            if await self._get_yt_dlp_version(invocation):
                return invocation
            excluded.add(invocation["path"])
            self._log_warning(f"Skipping broken yt-dlp: {invocation['path']}")
        return None

    async def _require_yt_dlp_invocation(self) -> dict[str, Any]:
        invocation = await self._working_yt_dlp_invocation()
        if invocation:
            return invocation
        # Concurrent previews/downloads share one repair attempt.
        async with self._yt_dlp_repair_lock:
            invocation = await self._working_yt_dlp_invocation()
            if not invocation:
                self._log_warning("Repairing unavailable yt-dlp runtime")
                await self.update_yt_dlp()
                invocation = await self._working_yt_dlp_invocation()
        if not invocation:
            raise RuntimeError(
                "ThemeDeck could not repair its YouTube downloader. "
                "Use Update yt-dlp and check themedeck-debug.log for details."
            )
        return invocation

    async def _get_yt_dlp_version(self, invocation: dict[str, Any]) -> str | None:
        command = [*invocation["command"], "--version"]
        try:
            result = await self._run_command(command, timeout=20, env=invocation["env"])
        except (OSError, subprocess.TimeoutExpired) as error:
            self._log_warning(f"yt-dlp runtime check failed: {error}")
            return None
        if result.returncode != 0:
            return None
        version = (result.stdout or "").strip()
        if not version:
            return None
        return version.splitlines()[0]

    async def _get_deno_version(self, deno_path: Path) -> str | None:
        try:
            result = await self._run_command([str(deno_path), "--version"], timeout=20)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0:
            return None
        first_line = (result.stdout or "").strip().splitlines()
        if not first_line:
            return None
        match = re.search(r"\bdeno\s+(\d+(?:\.\d+){1,3})", first_line[0])
        return match.group(1) if match else None

    def _is_supported_deno_version(self, version: str | None) -> bool:
        if not version:
            return False
        parts = [int(value) for value in re.findall(r"\d+", version)[:3]]
        parts.extend([0] * (3 - len(parts)))
        return tuple(parts) >= DENO_MINIMUM_VERSION

    async def _run_command(
        self, command: list[str], timeout: int = 120, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        command_text = " ".join(command)
        self._log_info(f"Executing command: {command_text}")
        run_env = os.environ.copy()
        # Decky loader can inject PyInstaller/OpenSSL paths that break Python tools.
        run_env.pop("LD_LIBRARY_PATH", None)
        run_env.pop("PYTHONHOME", None)
        run_env.pop("PYTHONPATH", None)
        if env:
            run_env.update(env)
        result = await asyncio.to_thread(
            subprocess.run,
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            env=run_env,
        )
        if result.returncode != 0:
            self._log_error(f"Command failed rc={result.returncode}: {command_text}")
            if result.stderr:
                self._log_error(f"stderr: {self._trim_message(result.stderr, 1200)}")
            if result.stdout:
                self._log_error(f"stdout: {self._trim_message(result.stdout, 1200)}")
        else:
            self._log_info(f"Command completed rc=0: {command_text}")
        return result

    def _command_error(
        self, result: subprocess.CompletedProcess[str], fallback: str
    ) -> str:
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        details = f"{stderr} {stdout}".lower()
        if "not a bot" in details or "sign in to confirm" in details:
            return ("YouTube requires sign-in verification. Sign into YouTube in Firefox, "
                    "then enable Use Firefox cookies for YouTube in ThemeDeck. "
                    "If already enabled, refresh your Firefox sign-in and retry.")
        if any(text in details for text in ("403", "signature solving failed", "n challenge", "page needs to be reloaded")):
            return ("YouTube rejected the audio request. Use Update YouTube support in ThemeDeck "
                    "to update yt-dlp and Deno, then retry. If it persists, try the optional "
                    "Firefox cookies setting after signing into YouTube in Firefox. "
                    "See themedeck-debug.log for the original error.")
        if stderr and stdout:
            return self._trim_message(
                f"{stderr.splitlines()[-1]} | {stdout.splitlines()[-1]}", 220
            )
        if stderr:
            return self._trim_message(stderr.splitlines()[-1], 220)
        if stdout:
            return self._trim_message(stdout.splitlines()[-1], 220)
        return fallback

    def _normalize_youtube_url(self, value: str) -> str:
        candidate = (value or "").strip()
        if not candidate:
            raise ValueError("YouTube URL is required")

        if "://" not in candidate and candidate.startswith(
            ("youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be")
        ):
            candidate = f"https://{candidate}"
        elif "://" not in candidate and "/" not in candidate and " " not in candidate:
            candidate = f"https://www.youtube.com/watch?v={candidate}"

        parsed = urllib.parse.urlparse(candidate)
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        if host not in {"youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}:
            raise ValueError("Only YouTube links are supported")
        return candidate

    def _extract_youtube_video_id(self, value: str) -> str:
        parsed = urllib.parse.urlparse(value)
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        if host == "youtu.be":
            video_id = parsed.path.strip("/").split("/")[0]
            if video_id:
                return video_id
        query = urllib.parse.parse_qs(parsed.query)
        video_ids = query.get("v") or []
        if video_ids and video_ids[0]:
            return video_ids[0]
        parts = [part for part in parsed.path.split("/") if part]
        for marker in ("shorts", "embed", "live"):
            if marker in parts:
                index = parts.index(marker)
                if index + 1 < len(parts):
                    return parts[index + 1]
        return re.sub(r"[^A-Za-z0-9_-]+", "_", value)[-80:]

    def _simplify_youtube_query(self, value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value or "")
        ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
        cleaned = re.sub(r"[^\w\s:'&+.-]+", " ", ascii_text)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def _youtube_search_candidates(self, query: str) -> list[str]:
        candidates: list[str] = []

        def add(value: str) -> None:
            cleaned = re.sub(r"\s+", " ", (value or "").strip())
            if cleaned and cleaned not in candidates:
                candidates.append(cleaned)

        add(query)
        simplified = self._simplify_youtube_query(query)
        add(simplified)
        if simplified:
            add(re.sub(r"\btheme\s+music\b", "soundtrack", simplified, flags=re.IGNORECASE))
            add(re.sub(r"\btheme\s+music\b", "ost", simplified, flags=re.IGNORECASE))
        return candidates[:4]

    def _parse_youtube_search_json_lines(self, stdout: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for raw_line in (stdout or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except Exception:
                self._log_warning(
                    f"youtube search skipped non-json line={self._trim_message(line, 240)!r}"
                )
                continue
            if not isinstance(item, dict):
                continue

            video_id = str(item.get("id") or "").strip()
            if not video_id or video_id in seen_ids:
                continue
            title = str(item.get("title") or video_id).strip()
            uploader = str(
                item.get("uploader") or item.get("channel") or item.get("creator") or ""
            ).strip()
            duration_raw = item.get("duration")
            duration: int | None = None
            if duration_raw not in {None, "", "NA"}:
                try:
                    duration = int(float(duration_raw))
                except (TypeError, ValueError):
                    duration = None
            if duration is not None and duration > 15 * 60:
                continue

            url_raw = str(
                item.get("webpage_url")
                or item.get("original_url")
                or item.get("url")
                or ""
            ).strip()
            if url_raw.startswith("http://") or url_raw.startswith("https://"):
                webpage_url = url_raw
            else:
                webpage_url = f"https://www.youtube.com/watch?v={video_id}"

            seen_ids.add(video_id)
            results.append(
                {
                    "id": video_id,
                    "title": title,
                    "uploader": uploader,
                    "duration": duration,
                    "webpage_url": webpage_url,
                }
            )
        return results

    def _extract_downloaded_path(
        self, lines: list[str], base_dir: Path
    ) -> Path | None:
        for line in reversed(lines):
            raw = line.strip()
            if not raw:
                continue
            candidate = Path(raw).expanduser()
            if not candidate.is_absolute():
                candidate = (base_dir / candidate).expanduser()
            resolved = candidate.resolve()
            if (
                resolved.exists()
                and resolved.is_file()
                and resolved.suffix.lower().lstrip(".") in SUPPORTED_AUDIO_EXTENSIONS
            ):
                return resolved
        return None

    def _find_latest_audio_file(self, directory: Path) -> Path | None:
        if not directory.exists():
            return None
        audio_files = [
            path
            for path in directory.iterdir()
            if path.is_file()
            and path.suffix.lower().lstrip(".") in SUPPORTED_AUDIO_EXTENSIONS
        ]
        if not audio_files:
            return None
        return max(audio_files, key=lambda path: path.stat().st_mtime)

    async def _ensure_deno(self) -> str | None:
        existing_path = self._resolve_deno_path()
        if existing_path:
            existing_version = await self._get_deno_version(existing_path)
            if self._is_supported_deno_version(existing_version):
                self._log_info(
                    f"Using Deno {existing_version} at {existing_path} for yt-dlp"
                )
                return None
            self._log_warning(
                f"Deno at {existing_path} is unsupported "
                f"({existing_version or 'unknown version'}); installing a managed copy"
            )

        try:
            await self._install_deno()
        except Exception as error:
            self._log_error(f"Failed to install Deno: {error}")
            return self._trim_message(str(error), 220)

        installed_version = await self._get_deno_version(self._deno_path)
        if not self._is_supported_deno_version(installed_version):
            return (
                f"installed Deno version is unsupported: "
                f"{installed_version or 'unknown'}"
            )
        self._log_info(
            f"Deno {installed_version} installed successfully at {self._deno_path}"
        )
        return None

    async def _install_deno(self) -> None:
        platform_key = (platform.system().lower(), platform.machine().lower())
        asset_name = DENO_RELEASE_ASSETS.get(platform_key)
        if not asset_name:
            raise RuntimeError(
                "automatic Deno installation is not supported on "
                f"{platform_key[0] or 'unknown OS'}/{platform_key[1] or 'unknown architecture'}"
            )

        self._settings_dir.mkdir(parents=True, exist_ok=True)
        self._deno_path.parent.mkdir(parents=True, exist_ok=True)
        asset_url = f"{DENO_RELEASE_BASE_URL}/{asset_name}"
        checksum_url = f"{asset_url}.sha256sum"

        with tempfile.TemporaryDirectory(
            prefix="deno-install-", dir=str(self._settings_dir)
        ) as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            archive_path = temp_dir / asset_name
            checksum_path = temp_dir / f"{asset_name}.sha256sum"
            extracted_path = temp_dir / "deno"

            await self._download_file(asset_url, archive_path, timeout=300)
            await self._download_file(checksum_url, checksum_path, timeout=60)

            checksum_match = re.search(
                r"\b([0-9a-fA-F]{64})\b",
                checksum_path.read_text(encoding="utf-8", errors="replace"),
            )
            if not checksum_match:
                raise RuntimeError("Deno release checksum was missing or invalid")

            digest = hashlib.sha256()
            with archive_path.open("rb") as archive_handle:
                for chunk in iter(lambda: archive_handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            expected_digest = checksum_match.group(1).lower()
            if digest.hexdigest().lower() != expected_digest:
                raise RuntimeError("Deno release checksum verification failed")

            with zipfile.ZipFile(archive_path) as archive:
                deno_member = next(
                    (
                        member
                        for member in archive.infolist()
                        if not member.is_dir() and Path(member.filename).name == "deno"
                    ),
                    None,
                )
                if deno_member is None:
                    raise RuntimeError("Deno release archive did not contain the executable")
                with archive.open(deno_member) as source, extracted_path.open("wb") as target:
                    shutil.copyfileobj(source, target)

            extracted_path.chmod(0o755)
            extracted_path.replace(self._deno_path)

    async def _download_file(
        self, url: str, target_path: Path, timeout: int = 220
    ) -> None:
        errors: list[str] = []

        def clear_target() -> None:
            try:
                if target_path.exists():
                    target_path.unlink()
            except OSError:
                pass

        curl_path = shutil.which("curl")
        if curl_path:
            clear_target()
            try:
                result = await self._run_command(
                    [
                        curl_path,
                        "-fsSL",
                        "--retry",
                        "3",
                        "--retry-delay",
                        "1",
                        "--connect-timeout",
                        "20",
                        "--max-time",
                        str(timeout),
                        "-A",
                        "ThemeDeck/3 (+Decky Loader)",
                        "-o",
                        str(target_path),
                        url,
                    ],
                    timeout=timeout + 20,
                )
                if (
                    result.returncode == 0
                    and target_path.exists()
                    and target_path.stat().st_size > 0
                ):
                    return
                errors.append(
                    f"curl: {self._command_error(result, 'download failed')}"
                )
            except Exception as error:
                errors.append(f"curl: {error}")

        wget_path = shutil.which("wget")
        if wget_path:
            clear_target()
            try:
                result = await self._run_command(
                    [
                        wget_path,
                        "--quiet",
                        "--tries=3",
                        "--timeout=20",
                        "-O",
                        str(target_path),
                        url,
                    ],
                    timeout=timeout + 20,
                )
                if (
                    result.returncode == 0
                    and target_path.exists()
                    and target_path.stat().st_size > 0
                ):
                    return
                errors.append(
                    f"wget: {self._command_error(result, 'download failed')}"
                )
            except Exception as error:
                errors.append(f"wget: {error}")

        clear_target()
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": "ThemeDeck/3 (+Decky Loader)"}
            )

            def download_with_urllib() -> None:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    with target_path.open("wb") as target:
                        shutil.copyfileobj(response, target)

            await asyncio.to_thread(download_with_urllib)
            if target_path.exists() and target_path.stat().st_size > 0:
                return
            errors.append("urllib: download returned no data")
        except Exception as error:
            errors.append(f"urllib: {error}")

        clear_target()
        raise RuntimeError(self._trim_message("; ".join(errors), 280))

    async def _download_yt_dlp_binary(self, target_path: Path) -> None:
        errors: list[str] = []

        curl_path = shutil.which("curl")
        wget_path = shutil.which("wget")
        for url in YTDLP_RELEASE_URLS:
            if curl_path:
                result = await self._run_command(
                    [
                        curl_path,
                        "-fsSL",
                        "-k",
                        "--http1.1",
                        "--retry",
                        "3",
                        "--retry-delay",
                        "1",
                        "--connect-timeout",
                        "20",
                        "--max-time",
                        "180",
                        "-A",
                        "ThemeDeck/1.1 (+Decky Loader)",
                        "-o",
                        str(target_path),
                        url,
                    ],
                    timeout=220,
                )
                if (
                    result.returncode == 0
                    and target_path.exists()
                    and target_path.stat().st_size > 0
                    and self._is_valid_yt_dlp_binary(target_path)
                ):
                    return
                errors.append(
                    f"curl {url}: {self._command_error(result, 'download failed')}"
                )
                try:
                    if target_path.exists():
                        target_path.unlink()
                except OSError:
                    pass

            if wget_path:
                result = await self._run_command(
                    [
                        wget_path,
                        "--quiet",
                        "--tries=3",
                        "--timeout=20",
                        "--no-check-certificate",
                        "-O",
                        str(target_path),
                        url,
                    ],
                    timeout=220,
                )
                if (
                    result.returncode == 0
                    and target_path.exists()
                    and target_path.stat().st_size > 0
                    and self._is_valid_yt_dlp_binary(target_path)
                ):
                    return
                errors.append(
                    f"wget {url}: {self._command_error(result, 'download failed')}"
                )
                try:
                    if target_path.exists():
                        target_path.unlink()
                except OSError:
                    pass

            try:
                request = urllib.request.Request(
                    url,
                    headers={"User-Agent": "ThemeDeck/1.1 (+Decky Loader)"},
                )
                context = ssl._create_unverified_context()
                with urllib.request.urlopen(request, timeout=90, context=context) as response:
                    data = response.read()
                if not data:
                    raise RuntimeError("no data returned")
                target_path.write_bytes(data)
                if (
                    target_path.stat().st_size <= 0
                    or not self._is_valid_yt_dlp_binary(target_path)
                ):
                    raise RuntimeError("downloaded file was not a valid yt-dlp binary")
                return
            except Exception as error:
                errors.append(f"urllib {url}: {error}")
                try:
                    if target_path.exists():
                        target_path.unlink()
                except OSError:
                    pass

        error_summary = "; ".join(errors) if errors else "unknown download error"
        raise RuntimeError(self._trim_message(error_summary, 280))

    def _is_valid_yt_dlp_binary(self, path: Path) -> bool:
        try:
            content = path.read_bytes()
        except OSError:
            return False
        if len(content) < 64:
            return False
        head = content[:4096].lower()
        if b"<!doctype html" in head or b"<html" in head:
            return False
        if content.startswith(b"\x7fELF"):
            return True
        if content.startswith(b"#!"):
            return True
        if content.startswith(b"MZ"):
            return True
        if len(content) > 1024 * 1024:
            return True
        return False

    def _trim_message(self, message: str, limit: int = 220) -> str:
        cleaned = " ".join((message or "").split())
        if len(cleaned) <= limit:
            return cleaned
        return f"{cleaned[:limit - 3]}..."

    async def _try_install_yt_dlp_with_pip(self) -> str | None:
        python3 = shutil.which("python3")
        if not python3:
            return "python3 not found"
        command = [
            python3,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "--user",
            "yt-dlp[default]",
            "--trusted-host",
            "pypi.org",
            "--trusted-host",
            "files.pythonhosted.org",
        ]
        result = await self._run_command(command, timeout=300)
        if result.returncode == 0:
            return None
        return self._command_error(result, "pip install failed")

    async def _install_yt_dlp_in_venv(self) -> str | None:
        python3 = shutil.which("python3")
        if not python3:
            return "python3 not found"

        self._yt_venv_dir.parent.mkdir(parents=True, exist_ok=True)
        create_command = [python3, "-m", "venv"]
        if self._yt_venv_dir.exists():
            healthy = await self._get_yt_dlp_version({
                "command": [str(self._yt_venv_yt_dlp)], "env": None,
            })
            if not healthy:
                # A Python minor-version upgrade leaves old site-packages behind.
                # Only recreate the dedicated runtime; music/settings live elsewhere.
                create_command.append("--clear")
        create_venv_result = await self._run_command(
            [*create_command, str(self._yt_venv_dir)],
            timeout=180,
        )
        if create_venv_result.returncode != 0:
            return self._command_error(create_venv_result, "venv creation failed")

        if not self._yt_venv_python.exists():
            return f"venv python not found at {self._yt_venv_python}"

        install_result = await self._run_command(
            [
                str(self._yt_venv_python),
                "-m",
                "pip",
                "install",
                "--upgrade",
                "pip",
                "yt-dlp[default]",
                "--trusted-host",
                "pypi.org",
                "--trusted-host",
                "files.pythonhosted.org",
            ],
            timeout=300,
        )
        if install_result.returncode != 0:
            return self._command_error(install_result, "venv pip install failed")

        if not self._yt_venv_yt_dlp.exists():
            return f"yt-dlp not found at {self._yt_venv_yt_dlp}"
        return None
