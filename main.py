from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

import decky


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


class Plugin:
    def __init__(self) -> None:
        self._tracks: dict[str, dict[str, Any]] = {}
        self._settings_dir = Path(decky.DECKY_PLUGIN_SETTINGS_DIR)
        self._tracks_file = self._settings_dir / "tracks.json"

    async def _main(self) -> None:
        self._settings_dir.mkdir(parents=True, exist_ok=True)
        self._load_tracks()
        decky.logger.info("ThemeDeck backend ready")

    async def _unload(self) -> None:
        decky.logger.info("ThemeDeck backend unloaded")

    async def _migration(self) -> None:
        self._settings_dir.mkdir(parents=True, exist_ok=True)

    async def get_tracks(self) -> dict[str, dict[str, Any]]:
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
            self._tracks[key] = {
                "app_id": app_id,
                "path": str(resolved),
                "filename": filename,
                "volume": self._tracks.get(key, {}).get("volume", 1.0),
            }
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

    async def remove_track(self, app_id: int) -> dict[str, dict[str, Any]]:
        self._tracks.pop(str(app_id), None)
        self._save_tracks()
        return self._tracks

    async def get_track(self, app_id: int) -> dict[str, Any] | None:
        return self._tracks.get(str(app_id))

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

    def _load_tracks(self) -> None:
        if not self._tracks_file.exists():
            self._tracks = {}
            return

        try:
            with self._tracks_file.open("r", encoding="utf-8") as handle:
                self._tracks = json.load(handle)
        except Exception as error:
            decky.logger.error(f"Failed to read tracks.json: {error}")
            self._tracks = {}

    def _save_tracks(self) -> None:
        try:
            with self._tracks_file.open("w", encoding="utf-8") as handle:
                json.dump(self._tracks, handle, indent=2, ensure_ascii=False)
        except Exception as error:
            decky.logger.error(f"Failed to save tracks.json: {error}")
