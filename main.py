from __future__ import annotations

import asyncio
import base64
import html as html_lib
import json
import math
import os
import re
import shutil
import ssl
import subprocess
import tempfile
import threading
import traceback
import unicodedata
import urllib.parse
import urllib.request
import urllib.error
import time
from pathlib import Path
from typing import Any

import decky

SUPPORTED_AUDIO_EXTENSIONS = {"mp3", "aac", "flac", "ogg", "wav", "m4a"}
YTDLP_RELEASE_URLS = (
    "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp",
    "https://yt-dlp.org/downloads/latest/yt-dlp",
    "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_linux",
)

# --- Smart theme search -------------------------------------------------------
# Steam store names often carry an edition ("Crimson Desert Enhanced"), which makes
# YouTube searches worse. For Steam games we look up the game's own name on Wikidata
# by Steam app ID (property P1733), which needs no API key. If Wikidata has no entry
# we keep the full Steam name and never trim words from it.
WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
WIKIDATA_USER_AGENT = "ThemeDeck (+https://github.com/BrenticusMaximus/ThemeDeck)"
WIKIDATA_BATCH_SIZE = 50
SYSTEM_CA_BUNDLES = (
    "/etc/ssl/certs/ca-certificates.crt",  # Arch, SteamOS, CachyOS, Debian, Ubuntu
    "/etc/pki/tls/certs/ca-bundle.crt",  # Fedora, Bazzite
    "/etc/ssl/cert.pem",
)
WIKIDATA_MISS_TTL_SECONDS = 30 * 24 * 60 * 60
# Same count as the manual search on the game page, so both rank the same results.
THEME_SEARCH_RESULTS_PER_QUERY = 20
THEME_MIN_ACCEPT_SCORE = 25
THEME_CONFIDENT_SCORE = 60
THEME_MAX_CANDIDATES = 5
THEME_MAX_VIEW_BONUS = 8.0
TRADEMARK_SYMBOL_PATTERN = re.compile(r"[™®©]")
WIKIDATA_ENTITY_ID_PATTERN = re.compile(r"^Q\d+$")
THEME_NAME_STOPWORDS = {"the", "of", "and", "a", "an", "to", "in", "on", "for", "edition"}
THEME_STRONG_KEYWORDS = (
    "main theme",
    "main menu",
    "menu theme",
    "menu music",
    "title theme",
    "title screen",
    "opening theme",
)
THEME_KEYWORDS = ("theme", "ost", "soundtrack", "original score", "score")
THEME_HARD_NEGATIVE_KEYWORDS = (
    "trailer",
    "gameplay",
    "walkthrough",
    "playthrough",
    "longplay",
    "let's play",
    "lets play",
    "review",
    "reaction",
    "speedrun",
    "tutorial",
    "guide",
    "teaser",
    "announcement",
    "interview",
    "unboxing",
)
THEME_SOFT_NEGATIVE_KEYWORDS = (
    "cover",
    "remix",
    "piano",
    "lofi",
    "lo-fi",
    "8-bit",
    "8 bit",
    "metal version",
    "guitar",
    "violin",
    "fan made",
    "fanmade",
    "nightcore",
    "slowed",
    "reverb",
    "hour",
    "extended",
    "full album",
    "full soundtrack",
    "complete soundtrack",
    "full ost",
    "compilation",
    "all songs",
    "ambience",
    "ambient mix",
    "asmr",
)


def strip_trademark_symbols(name: str) -> str:
    """Remove ™/®/© only; these are never part of a game's actual name."""
    cleaned = TRADEMARK_SYMBOL_PATTERN.sub("", str(name or ""))
    return re.sub(r"\s+", " ", cleaned).strip()


def _compact_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", value).lower())


def _name_tokens(value: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", unicodedata.normalize("NFKD", value).lower())
    return [word for word in words if word not in THEME_NAME_STOPWORDS]


def pick_wikidata_label(steam_name: str, labels: list[str]) -> str | None:
    """Choose the Wikidata label to search with for one Steam app.

    An app ID can map to several items (base game and an edition). Prefer the
    shortest label the Steam name starts with, otherwise the shortest label.
    """
    usable = sorted(
        {
            strip_trademark_symbols(label)
            for label in labels
            if label and not WIKIDATA_ENTITY_ID_PATTERN.match(label.strip())
        },
        key=lambda label: (len(label), label),
    )
    usable = [label for label in usable if label]
    if not usable:
        return None
    steam_compact = _compact_text(steam_name)
    for label in usable:
        if steam_compact.startswith(_compact_text(label)):
            return label
    return usable[0]


def build_theme_queries(name: str) -> list[str]:
    return [f"{name} main theme", f"{name} main menu music", f"{name} OST"]


def score_theme_result(result: dict[str, Any], names: list[str]) -> float:
    """Score how likely a YouTube search result is the game's main theme."""
    title = str(result.get("title") or "")
    uploader = str(result.get("uploader") or "")
    title_lower = unicodedata.normalize("NFKD", title).lower()
    title_compact = _compact_text(title)
    title_tokens = set(_name_tokens(title))

    best_name_match = 0.0
    for name in names:
        name_compact = _compact_text(name)
        if name_compact and name_compact in title_compact:
            best_name_match = 1.0
            break
        tokens = _name_tokens(name)
        if tokens:
            best_name_match = max(
                best_name_match,
                sum(1 for token in tokens if token in title_tokens) / len(tokens),
            )
    if best_name_match < 0.6:
        # Results that don't name the game are almost always a different game.
        return -100.0

    names_lower = " ".join(unicodedata.normalize("NFKD", name).lower() for name in names)

    def contains_word(text: str, keyword: str) -> bool:
        # Whole-word match so "ost" doesn't match "Ghost" or "Lost".
        return re.search(rf"(?<![a-z0-9]){re.escape(keyword)}s?(?![a-z0-9])", text) is not None

    def has_keyword(keywords: tuple[str, ...]) -> bool:
        # Ignore keywords that are part of the game's own name ("Darkest Hour").
        return any(
            contains_word(title_lower, keyword) and not contains_word(names_lower, keyword)
            for keyword in keywords
        )

    score = 20.0 * best_name_match
    if has_keyword(THEME_STRONG_KEYWORDS):
        score += 30
    elif has_keyword(THEME_KEYWORDS):
        score += 15
    if has_keyword(THEME_HARD_NEGATIVE_KEYWORDS):
        score -= 40
    if has_keyword(THEME_SOFT_NEGATIVE_KEYWORDS):
        score -= 25
    if "official" in title_lower:
        score += 5
    if uploader.endswith(" - Topic"):
        score += 10

    duration = result.get("duration")
    if isinstance(duration, (int, float)):
        # Menu music is often a long loop, so up to 12 minutes still counts as a track.
        if 60 <= duration <= 12 * 60:
            score += 15
        elif duration < 30:
            score -= 30
        elif duration > 15 * 60:
            # Hour-long loops and full-album uploads, never a single theme.
            score -= 40

    # Small tie-breaker: widely watched uploads tend to be the right, clean track.
    # Log-scaled and capped so it can never outweigh the title rules above.
    views = result.get("view_count")
    if isinstance(views, (int, float)) and views > 1000:
        score += min(THEME_MAX_VIEW_BONUS, 2.0 * math.log10(views / 1000))
    return score


def sort_theme_results(
    results: list[dict[str, Any]], names: list[str]
) -> list[dict[str, Any]]:
    """Order every result by score, best first, without dropping any.

    Used for searches the user runs: they decide, we only put likely matches on top.
    Ties keep YouTube's order.
    """
    scored = [
        (score_theme_result(result, names), index, result)
        for index, result in enumerate(results)
    ]
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [{**result, "score": round(score, 1)} for score, _, result in scored]


def rank_theme_results(
    results: list[dict[str, Any]], names: list[str]
) -> list[dict[str, Any]]:
    """Return results that pass the score threshold, best first."""
    scored: list[tuple[float, int, dict[str, Any]]] = []
    for index, result in enumerate(results):
        score = score_theme_result(result, names)
        if score >= THEME_MIN_ACCEPT_SCORE:
            scored.append((score, index, {**result, "score": round(score, 1)}))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [result for _, _, result in scored]


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def clamp_seconds(value: float, minimum: float = 0.0, maximum: float = 30.0) -> float:
    return max(minimum, min(maximum, value))


class Plugin:
    def __init__(self) -> None:
        self._tracks: dict[str, dict[str, Any]] = {}
        self._global_track_key = "__global__"
        self._store_track_key = "__store__"
        self._settings_dir = Path(decky.DECKY_PLUGIN_SETTINGS_DIR)
        self._tracks_file = self._settings_dir / "tracks.json"
        self._bin_dir = self._settings_dir / "bin"
        self._yt_dlp_path = self._bin_dir / "yt-dlp"
        self._yt_venv_dir = self._settings_dir / "ytvenv"
        self._yt_venv_bin = self._yt_venv_dir / "bin"
        self._yt_venv_python = self._yt_venv_bin / "python"
        self._yt_venv_yt_dlp = self._yt_venv_bin / "yt-dlp"
        self._downloads_dir = self._settings_dir / "downloads"
        self._preview_dir = self._settings_dir / "previews"
        self._debug_log_file = Path.home() / "ThemeDeck" / "themedeck-debug.log"
        self._playback_process: subprocess.Popen[bytes] | None = None
        self._playback_player: str | None = None
        self._playback_started_at: float = 0.0
        self._playback_start_offset: float = 0.0
        self._playback_log_file = self._settings_dir / "backend-player.log"

    async def _main(self) -> None:
        self._settings_dir.mkdir(parents=True, exist_ok=True)
        self._bin_dir.mkdir(parents=True, exist_ok=True)
        self._downloads_dir.mkdir(parents=True, exist_ok=True)
        self._preview_dir.mkdir(parents=True, exist_ok=True)
        self._load_tracks()
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
                "start_offset": self._tracks.get(key, {}).get("start_offset", 0.0),
                "loop": bool(self._tracks.get(key, {}).get("loop", True)),
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
            self._tracks[self._global_track_key] = {
                "scope": "global",
                "path": str(resolved),
                "filename": filename,
                "volume": previous.get("volume", 1.0),
                "start_offset": previous.get("start_offset", 0.0),
                "loop": bool(previous.get("loop", True)),
            }
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
            self._tracks[self._store_track_key] = {
                "scope": "store",
                "path": str(resolved),
                "filename": filename,
                "volume": previous.get("volume", 1.0),
                "start_offset": previous.get("start_offset", 0.0),
                "loop": bool(previous.get("loop", True)),
            }
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
        invocation = self._resolve_yt_dlp_invocation()
        installed = bool(invocation)
        status: dict[str, Any] = {
            "installed": installed,
            "path": invocation["path"] if invocation else "",
            "source": "none",
            "version": "",
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
            f"path={status.get('path')} version={status.get('version') or 'unknown'}"
        )
        return status

    async def update_yt_dlp(self) -> dict[str, Any]:
        self._log_info("yt-dlp update requested")
        self._bin_dir.mkdir(parents=True, exist_ok=True)
        venv_error = await self._install_yt_dlp_in_venv()
        if venv_error:
            self._log_warning(f"yt-dlp venv install/update failed: {venv_error}")
        else:
            self._log_info("yt-dlp venv install/update completed")
        status = await self.get_yt_dlp_status()
        if status.get("installed") and status.get("source") in {"venv", "system"}:
            if status.get("version"):
                self._log_info(
                    f"yt-dlp available via {status.get('source')} ({status.get('version')})"
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
            self._log_info(f"yt-dlp local binary updated successfully ({version})")
        except Exception as error:
            self._log_error(f"Failed to update yt-dlp local binary: {error}")
            pip_error = await self._try_install_yt_dlp_with_pip()
            if pip_error:
                self._log_warning(f"yt-dlp user pip fallback failed: {pip_error}")
            status = await self.get_yt_dlp_status()
            if status.get("installed"):
                self._log_info("yt-dlp became available via pip/system fallback")
                return status
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
        status = await self.get_yt_dlp_status()
        if not status.get("installed"):
            raise RuntimeError("yt-dlp update completed but executable was not found")
        self._log_info(
            f"yt-dlp update finished source={status.get('source')} "
            f"version={status.get('version') or 'unknown'}"
        )
        return status

    async def search_youtube(self, query: str, limit: int = 10) -> dict[str, Any]:
        try:
            cleaned_query = (query or "").strip()
            if not cleaned_query:
                raise ValueError("Search query is required")

            yt_dlp = self._require_yt_dlp_invocation()
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
                    "--no-warnings",
                    "--no-check-certificate",
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

    async def get_theme_search_name(self, app_id: int, game_name: str) -> dict[str, Any]:
        """Name to pre-fill the manual YouTube search with."""
        steam_name = strip_trademark_symbols(game_name)
        canonical_name = await self._lookup_canonical_name(app_id, steam_name)
        return {
            "name": canonical_name or steam_name,
            "source": "wikidata" if canonical_name else "steam",
        }

    async def search_youtube_ranked(
        self, query: str, limit: int, app_id: int, game_name: str
    ) -> dict[str, Any]:
        """search_youtube, with results sorted so the likeliest theme comes first."""
        response = await self.search_youtube(query, limit)
        results = response.get("results", [])
        steam_name = strip_trademark_symbols(game_name)
        names = [steam_name] if steam_name else []
        canonical_name = await self._lookup_canonical_name(app_id, steam_name)
        if canonical_name:
            names.insert(0, canonical_name)
        if not names:
            return {"results": results}
        return {"results": sort_theme_results(results, names)}

    async def _lookup_canonical_name(self, app_id: int, steam_name: str) -> str | None:
        if not steam_name or not 0 < int(app_id) < 0x80000000:  # skip non-Steam shortcuts
            return None
        try:
            canonical = await asyncio.to_thread(
                self._resolve_canonical_names, {int(app_id): steam_name}
            )
        except Exception as error:
            self._log_warning(f"canonical name lookup failed app={app_id}: {error}")
            return None
        return canonical.get(int(app_id))

    async def find_theme_candidates(self, app_id: int, game_name: str) -> dict[str, Any]:
        """Smart theme search for one game.

        Returns ranked candidates, or an empty list when nothing scored well enough,
        in which case the caller falls back to its original search.
        """
        steam_name = strip_trademark_symbols(game_name)
        canonical_name = await self._lookup_canonical_name(app_id, steam_name)
        query_name = canonical_name or steam_name
        if not query_name:
            return {"query_name": "", "source": "none", "candidates": []}
        names = [name for name in dict.fromkeys([query_name, steam_name]) if name]

        candidates: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for query in build_theme_queries(query_name):
            try:
                response = await self.search_youtube(query, THEME_SEARCH_RESULTS_PER_QUERY)
            except Exception as error:
                self._log_warning(f"theme search query failed query={query!r}: {error}")
                continue
            fresh = [
                result
                for result in response.get("results", [])
                if result.get("id") and result["id"] not in seen_ids
            ]
            seen_ids.update(result["id"] for result in fresh)
            candidates = rank_theme_results(
                [*candidates, *fresh], names
            )
            if candidates and candidates[0]["score"] >= THEME_CONFIDENT_SCORE:
                break

        candidates = candidates[:THEME_MAX_CANDIDATES]
        self._log_info(
            f"theme search app={app_id} steam_name={steam_name!r} query_name={query_name!r} "
            f"source={'wikidata' if canonical_name else 'steam'} candidates="
            + ", ".join(
                f"{c['score']}:{self._trim_message(c['title'], 60)!r}"
                f"({c.get('duration')}s,{c.get('view_count')}v,{self._trim_message(c.get('uploader') or '', 30)})"
                for c in candidates
            )
        )
        return {
            "query_name": query_name,
            "source": "wikidata" if canonical_name else "steam",
            "candidates": candidates,
        }

    async def get_youtube_preview_stream(self, video_url: str) -> dict[str, Any]:
        yt_dlp = self._require_yt_dlp_invocation()
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
            "--no-warnings",
            "--no-check-certificate",
            "--no-playlist",
            "--extract-audio",
            "--audio-format",
            "mp3",
            "--audio-quality",
            "5",
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
        if app_id <= 0:
            raise ValueError("Invalid app id")

        yt_dlp = self._require_yt_dlp_invocation()
        normalized_url = self._normalize_youtube_url(video_url)
        video_id = self._extract_youtube_video_id(normalized_url)
        app_download_dir = self._downloads_dir / str(app_id)
        app_download_dir.mkdir(parents=True, exist_ok=True)
        self._log_info(
            f"youtube download requested app={app_id} url={normalized_url} "
            f"video_id={video_id} source={yt_dlp.get('source')} path={yt_dlp.get('path')}"
        )

        command = [
            *yt_dlp["command"],
            "--no-warnings",
            "--no-check-certificate",
            "--no-playlist",
            "--extract-audio",
            "--audio-format",
            "mp3",
            "--audio-quality",
            "0",
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

        tracks = await self.set_track(app_id, str(downloaded_path), downloaded_path.name)
        self._tracks[str(app_id)]["youtube_id"] = video_id
        self._save_tracks()
        self._log_info(f"youtube download assigned app={app_id} file={downloaded_path}")
        return {
            "tracks": tracks,
            "path": str(downloaded_path),
            "filename": downloaded_path.name,
        }

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
                if "loop" not in track:
                    track["loop"] = True
                    changed = True
            if changed:
                self._save_tracks()
        except Exception as error:
            decky.logger.error(f"Failed to read tracks.json: {error}")

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
        try:
            with self._tracks_file.open("w", encoding="utf-8") as handle:
                json.dump(self._tracks, handle, indent=2, ensure_ascii=False)
        except Exception as error:
            decky.logger.error(f"Failed to save tracks.json: {error}")

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

    def _resolve_canonical_names(self, steam_names: dict[int, str]) -> dict[int, str]:
        """Map Steam app IDs to Wikidata game names, using a persistent cache."""
        cache_file = self._settings_dir / "wikidata-names.json"
        try:
            cache = json.loads(cache_file.read_text(encoding="utf-8"))
            if not isinstance(cache, dict):
                cache = {}
        except Exception:
            cache = {}

        now = time.time()
        resolved: dict[int, str] = {}
        pending: list[int] = []
        for app_id in steam_names:
            entry = cache.get(str(app_id))
            if isinstance(entry, dict) and entry.get("name"):
                resolved[app_id] = str(entry["name"])
            elif isinstance(entry, dict) and now - float(entry.get("checked", 0)) < WIKIDATA_MISS_TTL_SECONDS:
                continue
            else:
                pending.append(app_id)

        if pending:
            for start in range(0, len(pending), WIKIDATA_BATCH_SIZE):
                batch = pending[start : start + WIKIDATA_BATCH_SIZE]
                labels_by_id = self._fetch_wikidata_labels(batch)
                for app_id in batch:
                    name = pick_wikidata_label(steam_names[app_id], labels_by_id.get(app_id, []))
                    cache[str(app_id)] = {"name": name, "checked": now}
                    if name:
                        resolved[app_id] = name
            try:
                cache_file.write_text(json.dumps(cache, indent=2), encoding="utf-8")
            except Exception as error:
                self._log_warning(f"failed writing {cache_file}: {error}")
        return resolved

    def _urlopen_with_tls_fallback(self, request: urllib.request.Request, timeout: int) -> bytes:
        """Fetch a URL, coping with Decky's bundled Python having no CA bundle.

        Tries the default certificates, then the system CA bundle, and only then an
        unverified connection (as the rest of this plugin does). Only used for public,
        read-only data such as game names.
        """
        contexts: list[tuple[str, ssl.SSLContext | None]] = [("default", None)]
        for cafile in SYSTEM_CA_BUNDLES:
            if os.path.isfile(cafile):
                try:
                    contexts.append((cafile, ssl.create_default_context(cafile=cafile)))
                except Exception:
                    pass
                break
        contexts.append(("unverified", ssl._create_unverified_context()))

        last_error: Exception | None = None
        for label, context in contexts:
            try:
                with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
                    return response.read()
            except (ssl.SSLError, urllib.error.URLError) as error:
                reason = getattr(error, "reason", error)
                if not isinstance(reason, ssl.SSLError) and not isinstance(error, ssl.SSLError):
                    raise
                last_error = error
                if label != "unverified":
                    self._log_info(f"TLS verification with {label} certificates failed: {reason}")
        assert last_error is not None
        raise last_error

    def _fetch_wikidata_labels(self, app_ids: list[int]) -> dict[int, list[str]]:
        values = " ".join(f'"{app_id}"' for app_id in app_ids)
        # "mul" holds the language-independent name many game items use instead of "en".
        query = (
            "SELECT ?appid ?label WHERE { "
            f"VALUES ?appid {{ {values} }} "
            "?item wdt:P1733 ?appid. "
            "OPTIONAL { ?item rdfs:label ?en. FILTER(LANG(?en) = \"en\") } "
            "OPTIONAL { ?item rdfs:label ?mul. FILTER(LANG(?mul) = \"mul\") } "
            "BIND(COALESCE(?en, ?mul) AS ?label) "
            "}"
        )
        url = f"{WIKIDATA_SPARQL_URL}?{urllib.parse.urlencode({'query': query, 'format': 'json'})}"
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": WIKIDATA_USER_AGENT,
                "Accept": "application/sparql-results+json",
            },
        )
        # Network errors propagate so a failed lookup isn't cached as a miss.
        raw = self._urlopen_with_tls_fallback(request, timeout=15)
        payload = json.loads(raw.decode("utf-8", errors="ignore"))

        labels: dict[int, list[str]] = {}
        for binding in payload.get("results", {}).get("bindings", []):
            try:
                app_id = int(binding["appid"]["value"])
            except (KeyError, ValueError):
                continue
            label = binding.get("label", {}).get("value")
            if label:
                labels.setdefault(app_id, []).append(label)
        return labels

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

    def _resolve_yt_dlp_invocation(self) -> dict[str, Any] | None:
        if self._yt_venv_yt_dlp.exists() and os.access(self._yt_venv_yt_dlp, os.X_OK):
            return {
                "command": [str(self._yt_venv_yt_dlp)],
                "env": None,
                "source": "venv",
                "path": str(self._yt_venv_yt_dlp),
            }

        system_yt_dlp = shutil.which("yt-dlp")
        if system_yt_dlp:
            return {
                "command": [system_yt_dlp],
                "env": None,
                "source": "system",
                "path": system_yt_dlp,
            }

        user_yt_dlp = Path.home() / ".local" / "bin" / "yt-dlp"
        if user_yt_dlp.exists() and os.access(user_yt_dlp, os.X_OK):
            return {
                "command": [str(user_yt_dlp)],
                "env": None,
                "source": "system",
                "path": str(user_yt_dlp),
            }

        if self._yt_dlp_path.exists() and os.access(self._yt_dlp_path, os.X_OK):
            return {
                "command": [str(self._yt_dlp_path)],
                "env": None,
                "source": "local",
                "path": str(self._yt_dlp_path),
            }

        return None

    def _require_yt_dlp_invocation(self) -> dict[str, Any]:
        invocation = self._resolve_yt_dlp_invocation()
        if not invocation:
            raise RuntimeError(
                "yt-dlp is not available. Use the ThemeDeck install/update button."
            )
        return invocation

    async def _get_yt_dlp_version(self, invocation: dict[str, Any]) -> str | None:
        command = [*invocation["command"], "--version"]
        result = await self._run_command(command, timeout=20, env=invocation["env"])
        if result.returncode != 0:
            return None
        version = (result.stdout or "").strip()
        if not version:
            return None
        return version.splitlines()[0]

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

            view_count: int | None = None
            try:
                view_count = int(item["view_count"]) if item.get("view_count") is not None else None
            except (TypeError, ValueError):
                view_count = None

            seen_ids.add(video_id)
            results.append(
                {
                    "id": video_id,
                    "title": title,
                    "uploader": uploader,
                    "duration": duration,
                    "view_count": view_count,
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
            "yt-dlp",
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
        create_venv_result = await self._run_command(
            [python3, "-m", "venv", str(self._yt_venv_dir)],
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
                "yt-dlp",
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
