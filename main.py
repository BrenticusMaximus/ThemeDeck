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
# Steam tools/runtimes that show up as installed apps but aren't games.
LIBRARY_TOOL_APP_IDS = {7, 760, 12210, 12211, 12212, 12213, 12218, 228980}
LIBRARY_TOOL_NAME_PATTERN = re.compile(
    r"^(proton\b|steam linux runtime|steamworks|steamvr|steam audio|"
    r"steam controller configs|app \d+$)",
    re.IGNORECASE,
)


def is_library_tool(app_id: int, name: str) -> bool:
    """True for Proton, runtimes and other installed apps that aren't games."""
    return app_id in LIBRARY_TOOL_APP_IDS or bool(
        LIBRARY_TOOL_NAME_PATTERN.match(str(name or "").strip())
    )
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


# Names of non-Steam shortcuts that are launchers, stores or apps rather than games.
# Matched case-insensitively against the cleaned shortcut name. Game shortcuts that
# launch *through* one of these (e.g. NonSteamLaunchers entries) keep their own name,
# so they are not affected.
NON_STEAM_LAUNCHER_NAMES = {
    "amazon games",
    "amazon luna",
    "antstream arcade",
    "arc launcher",
    "artix game launcher",
    "battle.net",
    "big fish games manager",
    "bottles",
    "decky loader",
    "discord",
    "ea app",
    "emudeck",
    "epic games",
    "epic games launcher",
    "faugus launcher",
    "game jolt client",
    "geforce now",
    "glyph launcher",
    "gog galaxy",
    "google chrome",
    "gryphlink",
    "heroic games launcher",
    "hoyoplay",
    "humble games collection",
    "humble app",
    "indiegala",
    "itch.io",
    "legacy games",
    "lutris",
    "microsoft edge",
    "minecraft launcher",
    "moonlight",
    "moonlight game streaming",
    "mozilla firefox",
    "netflix",
    "nexon launcher",
    "nonsteamlaunchers",
    "nvidia geforce now",
    "origin",
    "playstation plus",
    "plarium play",
    "purple launcher",
    "remoteplaywhatever",
    "remote play whatever",
    "repair ea app",
    "retroarch",
    "rockstar games launcher",
    "spotify",
    "steam rom manager",
    "stove client",
    "tempo launcher",
    "twitch",
    "ubisoft connect",
    "uplay",
    "vfun launcher",
    "vk play",
    "waydroid",
    "xbox cloud gaming",
    "xbox game pass",
    "youtube",
    "youtube tv",
}
NON_STEAM_LAUNCHER_PATTERN = re.compile(
    r"(launchers?|client)$|^(repair|uninstall)\b", re.IGNORECASE
)
NON_STEAM_TRAILING_TAG_PATTERN = re.compile(r"\s*[\(\[\{][^\(\)\[\]\{\}]*[\)\]\}]\s*$")
NON_STEAM_TRADEMARK_PATTERN = re.compile(r"[™®©]")


def parse_binary_vdf(data: bytes) -> dict[str, Any]:
    """Parse Valve's binary KeyValues format (used by shortcuts.vdf)."""

    def read_cstring(offset: int) -> tuple[str, int]:
        end = data.index(b"\x00", offset)
        return data[offset:end].decode("utf-8", errors="replace"), end + 1

    def read_map(offset: int) -> tuple[dict[str, Any], int]:
        result: dict[str, Any] = {}
        while offset < len(data):
            value_type = data[offset]
            offset += 1
            if value_type in (0x08, 0x0B):  # end of map
                return result, offset
            key, offset = read_cstring(offset)
            if value_type == 0x00:
                result[key], offset = read_map(offset)
            elif value_type == 0x01:
                result[key], offset = read_cstring(offset)
            elif value_type in (0x02, 0x04, 0x06):  # int32, pointer, color
                result[key] = int.from_bytes(data[offset : offset + 4], "little", signed=True)
                offset += 4
            elif value_type == 0x03:  # float32
                result[key] = data[offset : offset + 4]
                offset += 4
            elif value_type in (0x07, 0x0A):  # uint64, int64
                result[key] = int.from_bytes(data[offset : offset + 8], "little", signed=value_type == 0x0A)
                offset += 8
            else:
                raise ValueError(f"Unsupported binary VDF type 0x{value_type:02x} at {offset - 1}")
        return result, offset

    parsed, _ = read_map(0)
    return parsed


def extract_non_steam_shortcuts(data: bytes) -> list[dict[str, Any]]:
    """Return [{appid, name}] for every entry in a shortcuts.vdf blob."""
    root = parse_binary_vdf(data)
    shortcuts = next(
        (value for key, value in root.items() if key.lower() == "shortcuts"),
        root,
    )
    if not isinstance(shortcuts, dict):
        return []

    entries: list[dict[str, Any]] = []
    for entry in shortcuts.values():
        if not isinstance(entry, dict):
            continue
        fields = {str(key).lower(): value for key, value in entry.items()}
        raw_app_id = fields.get("appid")
        name = str(fields.get("appname") or "").strip()
        if not isinstance(raw_app_id, int) or not name:
            continue
        # Stored as a signed int32; Steam's UI uses the unsigned value.
        entries.append({"appid": raw_app_id & 0xFFFFFFFF, "name": name})
    return entries


def clean_game_search_name(name: str) -> str:
    """Strip tags like "(USA)", "[GOG]" and trademark symbols from a game name."""
    cleaned = NON_STEAM_TRADEMARK_PATTERN.sub("", str(name or ""))
    previous = None
    while previous != cleaned:
        previous = cleaned
        cleaned = NON_STEAM_TRAILING_TAG_PATTERN.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -_:|")
    return cleaned or str(name or "").strip()


def _compact_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


# Shortcut tools often save names without spaces ("EAapp", "RockstarGamesLauncher"),
# so launcher names are also compared with spaces and punctuation removed.
NON_STEAM_LAUNCHER_COMPACT_NAMES = {
    _compact_name(launcher) for launcher in NON_STEAM_LAUNCHER_NAMES
}
# Long launcher names are distinctive enough to match as a prefix, which catches
# stray suffixes such as "UbisoftConnectx".
NON_STEAM_LAUNCHER_PREFIX_MIN_LENGTH = 10


def is_launcher_shortcut_name(name: str) -> bool:
    normalized = clean_game_search_name(name).lower()
    compact = _compact_name(normalized)
    if normalized in NON_STEAM_LAUNCHER_NAMES or compact in NON_STEAM_LAUNCHER_COMPACT_NAMES:
        return True
    if any(
        len(launcher) >= NON_STEAM_LAUNCHER_PREFIX_MIN_LENGTH and compact.startswith(launcher)
        for launcher in NON_STEAM_LAUNCHER_COMPACT_NAMES
    ):
        return True
    return bool(NON_STEAM_LAUNCHER_PATTERN.search(normalized))


# --- YouTube errors ---------------------------------------------------------------
# Errors YouTube usually recovers from within seconds or minutes; retried a few times.
YOUTUBE_RETRY_DELAYS_SECONDS = (3, 10)
YOUTUBE_RETRYABLE_PATTERNS = (
    "http error 403",
    "http error 429",
    "http error 5",
    "not a bot",
    "timed out",
    "connection reset",
    "connection refused",
    "temporary failure in name resolution",
    "incompleteread",
    "unable to download webpage",
    "unable to download video data",
)
# YouTube is limiting this PC; automatic downloads should pause instead of retrying.
YOUTUBE_RATE_LIMIT_PATTERNS = ("http error 429", "not a bot", "too many requests")


def is_retryable_youtube_error(message: str) -> bool:
    text = str(message or "").lower()
    return any(pattern in text for pattern in YOUTUBE_RETRYABLE_PATTERNS)


def describe_youtube_error(message: str) -> str:
    """Prefix yt-dlp errors with a short explanation the UI can show."""
    text = str(message or "").lower()
    if any(pattern in text for pattern in YOUTUBE_RATE_LIMIT_PATTERNS):
        return f"YouTube is limiting downloads (rate limited): {message}"
    if "ffmpeg" in text or "ffprobe" in text:
        return f"ffmpeg is missing (install it with: sudo pacman -S ffmpeg): {message}"
    if "video unavailable" in text or "private video" in text:
        return f"This video can't be downloaded: {message}"
    return message


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

    async def get_non_steam_shortcuts(self) -> dict[str, Any]:
        shortcuts = await asyncio.to_thread(self._read_non_steam_shortcuts)
        return {"shortcuts": shortcuts}

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

    async def get_music_storage(self) -> dict[str, Any]:
        """Counts and disk usage for the "Manage music" section."""
        return await asyncio.to_thread(self._music_storage)

    def _music_storage(self) -> dict[str, Any]:
        index = self._read_downloads_index()
        used = self._paths_in_use()
        summary: dict[str, Any] = {"game_tracks": len(self._game_track_keys())}
        for prefix in ("downloaded", "unused"):
            for source in ("auto", "manual"):
                summary[f"{prefix}_{source}_files"] = 0
                summary[f"{prefix}_{source}_bytes"] = 0
        for path in self._downloaded_files():
            source = self._download_source(path, index)
            size = self._file_size(path)
            summary[f"downloaded_{source}_files"] += 1
            summary[f"downloaded_{source}_bytes"] += size
            if str(path.resolve()) not in used:
                summary[f"unused_{source}_files"] += 1
                summary[f"unused_{source}_bytes"] += size
        for prefix in ("downloaded", "unused"):
            summary[f"{prefix}_files"] = summary[f"{prefix}_auto_files"] + summary[f"{prefix}_manual_files"]
            summary[f"{prefix}_bytes"] = summary[f"{prefix}_auto_bytes"] + summary[f"{prefix}_manual_bytes"]
        preview_files = (
            [path for path in self._preview_dir.rglob("*") if path.is_file()]
            if self._preview_dir.exists()
            else []
        )
        summary["preview_bytes"] = sum(self._file_size(path) for path in preview_files)
        return summary

    async def remove_all_game_tracks(self, delete_mode: str = "none") -> dict[str, Any]:
        """Remove the music from every game (global and store tracks are kept).

        delete_mode: "none" keeps all downloaded files, "auto" deletes files picked by
        bulk/automatic download (hand-picked ones are kept), "all" deletes everything
        ThemeDeck downloaded. The user's own local music files are never deleted.
        """
        removed = 0
        for key in self._game_track_keys():
            self._tracks.pop(key, None)
            removed += 1
        self._save_tracks()
        result: dict[str, Any] = {"removed": removed, "deleted_files": 0, "freed_bytes": 0}
        if delete_mode in ("auto", "all"):
            result.update(
                await asyncio.to_thread(
                    self._delete_downloads,
                    False,
                    {"auto"} if delete_mode == "auto" else {"auto", "manual"},
                )
            )
        self._log_info(f"remove_all_game_tracks mode={delete_mode} {result}")
        return {"result": result, "tracks": self._tracks}

    async def delete_unused_downloads(self, mode: str = "all") -> dict[str, Any]:
        """Delete downloaded files no game uses any more (assignments are kept).

        mode "auto" only deletes auto-picked files; "all" also hand-picked ones.
        """
        sources = {"auto"} if mode == "auto" else {"auto", "manual"}
        result = await asyncio.to_thread(self._delete_downloads, True, sources)
        self._log_info(f"delete_unused_downloads mode={mode} {result}")
        return result

    # --- Downloads index ------------------------------------------------------
    # downloads/index.json remembers, per downloaded file, which game it was for and
    # whether it was picked by hand ("manual") or by bulk/automatic download ("auto").
    # Files downloaded before the index existed have no entry and count as "auto".

    def _downloads_index_path(self) -> Path:
        return self._downloads_dir / "index.json"

    def _read_downloads_index(self) -> dict[str, dict[str, Any]]:
        try:
            data = json.loads(self._downloads_index_path().read_text(encoding="utf-8"))
            files = data.get("files") if isinstance(data, dict) else None
            return files if isinstance(files, dict) else {}
        except FileNotFoundError:
            return {}
        except Exception as error:
            self._log_warning(f"failed reading downloads index: {error}")
            return {}

    def _write_downloads_index(self, files: dict[str, dict[str, Any]]) -> None:
        try:
            self._downloads_dir.mkdir(parents=True, exist_ok=True)
            self._downloads_index_path().write_text(
                json.dumps({"version": 1, "files": files}, indent=2), encoding="utf-8"
            )
        except Exception as error:
            self._log_warning(f"failed writing downloads index: {error}")

    def _index_key(self, path: Path) -> str | None:
        try:
            return str(path.resolve().relative_to(self._downloads_dir.resolve()))
        except (ValueError, OSError):
            return None

    def _record_download(
        self, path: Path, *, app_id: int, youtube_id: str, source: str
    ) -> None:
        key = self._index_key(path)
        if not key:
            return
        files = self._read_downloads_index()
        files[key] = {
            "app_id": int(app_id),
            "youtube_id": youtube_id,
            "title": path.stem,
            "source": source,
            "downloaded_at": int(time.time()),
        }
        self._write_downloads_index(files)

    def _download_source(self, path: Path, index: dict[str, dict[str, Any]]) -> str:
        key = self._index_key(path)
        entry = index.get(key) if key else None
        source = entry.get("source") if isinstance(entry, dict) else None
        return "manual" if source == "manual" else "auto"

    def _game_track_keys(self) -> list[str]:
        return [
            key
            for key in self._tracks
            if key not in (self._global_track_key, self._store_track_key)
        ]

    def _downloaded_files(self) -> list[Path]:
        if not self._downloads_dir.exists():
            return []
        index_path = self._downloads_index_path()
        return [
            path
            for path in self._downloads_dir.rglob("*")
            if path.is_file() and path != index_path
        ]

    def _paths_in_use(self) -> set[str]:
        used: set[str] = set()
        for track in self._tracks.values():
            path = track.get("path") if isinstance(track, dict) else None
            if path:
                try:
                    used.add(str(Path(path).expanduser().resolve()))
                except Exception:
                    used.add(str(path))
        return used

    @staticmethod
    def _file_size(path: Path) -> int:
        try:
            return path.stat().st_size
        except OSError:
            return 0

    def _delete_downloads(self, only_unused: bool, sources: set[str]) -> dict[str, int]:
        """Delete files inside ThemeDeck's downloads folder whose source is in sources.

        Files still used by a track are always kept. The preview cache is cleared
        only when removing all music (not only_unused).
        """
        downloads_root = self._downloads_dir.resolve()
        used = self._paths_in_use()
        index = self._read_downloads_index()
        deleted = 0
        freed = 0
        for path in self._downloaded_files():
            resolved = path.resolve()
            # Never touch anything outside ThemeDeck's own downloads folder.
            if downloads_root not in resolved.parents or str(resolved) in used:
                continue
            if self._download_source(path, index) not in sources:
                continue
            size = self._file_size(resolved)
            try:
                resolved.unlink()
                deleted += 1
                freed += size
                key = self._index_key(path)
                if key:
                    index.pop(key, None)
            except OSError as error:
                self._log_warning(f"failed deleting {resolved}: {error}")
        self._write_downloads_index(index)
        for folder in sorted(
            (p for p in self._downloads_dir.rglob("*") if p.is_dir()),
            key=lambda p: len(p.parts),
            reverse=True,
        ):
            try:
                folder.rmdir()  # only removes empty folders
            except OSError:
                pass
        if not only_unused and self._preview_dir.exists():
            for path in self._preview_dir.rglob("*"):
                if path.is_file():
                    size = self._file_size(path)
                    try:
                        path.unlink()
                        freed += size
                    except OSError:
                        pass
        return {"deleted_files": deleted, "freed_bytes": freed}

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
                result = await self._run_with_retries(
                    command, timeout=90, env=yt_dlp["env"], label=f"search {search_query!r}"
                )
                last_stdout = result.stdout or ""
                if result.returncode != 0:
                    raise RuntimeError(
                        describe_youtube_error(self._command_error(result, "YouTube search failed"))
                    )

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

    async def check_new_games(self) -> dict[str, Any]:
        """Games (and non-Steam shortcuts) installed since the last check.

        Includes owned games that were just installed and games reinstalled later.

        The first call only records the current library (so enabling the feature
        doesn't download music for every game) and returns nothing.
        """
        return await asyncio.to_thread(self._check_new_games)

    def _check_new_games(self) -> dict[str, Any]:
        games, installed_ids = self._read_steam_library_games()
        names = {int(game["appid"]): str(game["name"]) for game in games}
        steam = {
            app_id: names.get(app_id, f"App {app_id}")
            for app_id in installed_ids
            if not is_library_tool(app_id, names.get(app_id, ""))
        }
        non_steam = {
            int(shortcut["appid"]): str(shortcut["name"])
            for shortcut in self._read_non_steam_shortcuts()
            if not shortcut["launcher"]
        }

        # {"steam": [...], "non_steam": [...]}; a missing group (first run, or a file
        # from before non-Steam support) is only recorded, never reported as new.
        known_file = self._settings_dir / "known-games.json"
        known: dict[str, set[int] | None] = {"steam": None, "non_steam": None}
        try:
            raw = json.loads(known_file.read_text(encoding="utf-8"))
            if isinstance(raw, list):  # first version: Steam games only
                known["steam"] = {int(value) for value in raw}
            elif isinstance(raw, dict):
                for group in known:
                    if isinstance(raw.get(group), list):
                        known[group] = {int(value) for value in raw[group]}
        except FileNotFoundError:
            pass
        except Exception as error:
            self._log_warning(f"failed reading {known_file}, starting fresh: {error}")

        current = {"steam": steam, "non_steam": non_steam}
        new_games: list[dict[str, Any]] = []
        for group, games_by_id in current.items():
            seen = known[group]
            if seen is None:
                self._log_info(f"new-game check: recorded {len(games_by_id)} {group} games")
                continue
            new_games.extend(
                {"appid": app_id, "name": name}
                for app_id, name in sorted(games_by_id.items())
                if app_id not in seen
            )

        first_run = all(value is None for value in known.values())
        # Store exactly what's installed now, so an uninstalled game that is installed
        # again later counts as newly installed.
        snapshot = {group: sorted(current[group]) for group in current}
        if any(set(snapshot[group]) != (known[group] or set()) or known[group] is None for group in current):
            try:
                known_file.write_text(json.dumps(snapshot), encoding="utf-8")
            except Exception as error:
                self._log_warning(f"failed writing {known_file}: {error}")
        if new_games:
            self._log_info(
                "new-game check found: "
                + ", ".join(f"{game['appid']}:{game['name']!r}" for game in new_games)
            )
        return {"first_run": first_run, "games": new_games}

    # --- Reusing kept downloads -------------------------------------------

    @staticmethod
    def _youtube_id_from_name(name: str) -> str | None:
        match = re.search(r"\[([A-Za-z0-9_-]{11})\]\.[A-Za-z0-9]+$", name or "")
        return match.group(1) if match else None

    def _resolved_str(self, path: str | Path) -> str:
        try:
            return str(Path(path).expanduser().resolve())
        except Exception:
            return str(path)

    def _find_kept_file(self, app_id: int) -> dict[str, Any] | None:
        """Best kept download for a game: hand-picked first, then the newest."""
        index = self._read_downloads_index()
        candidates: list[tuple[int, int, Path, str | None, str]] = []
        seen: set[str] = set()
        for key, entry in index.items():
            if not isinstance(entry, dict) or int(entry.get("app_id") or 0) != int(app_id):
                continue
            path = self._downloads_dir / key
            if not path.is_file():
                continue
            seen.add(self._resolved_str(path))
            youtube_id = entry.get("youtube_id")
            source = "manual" if entry.get("source") == "manual" else "auto"
            candidates.append(
                (1 if source == "manual" else 0, int(entry.get("downloaded_at") or 0), path, youtube_id, source)
            )
        # Files downloaded before the index existed: auto-picked, dated by mtime.
        legacy_dir = self._downloads_dir / str(app_id)
        if legacy_dir.is_dir():
            for path in legacy_dir.iterdir():
                resolved = self._resolved_str(path)
                if not path.is_file() or resolved in seen:
                    continue
                if path.suffix.lower().lstrip(".") not in SUPPORTED_AUDIO_EXTENSIONS:
                    continue
                youtube_id = self._youtube_id_from_name(path.name)
                candidates.append((0, int(path.stat().st_mtime), path, youtube_id, "auto"))
        if not candidates:
            return None
        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        _, _, path, youtube_id, source = candidates[0]
        return {"path": path, "youtube_id": youtube_id, "source": source}

    async def reattach_kept_track(self, app_id: int) -> dict[str, Any]:
        """Assign a kept download to a game without music, instead of searching again."""
        if str(app_id) in self._tracks:
            return {"path": None, "reason": "has_track"}
        kept = self._find_kept_file(app_id)
        if not kept:
            return {"path": None, "reason": "none_kept"}
        path: Path = kept["path"]
        tracks = await self.set_track(app_id, str(path), path.name)
        if kept["youtube_id"]:
            self._tracks[str(app_id)]["youtube_id"] = kept["youtube_id"]
            self._save_tracks()
        self._log_info(f"reattached kept track app={app_id} file={path} source={kept['source']}")
        return {"path": str(path), "source": kept["source"], "tracks": tracks}

    async def get_auto_download_excluded(self) -> list[int]:
        return sorted(self._read_auto_download_excluded())

    async def set_auto_download_excluded(self, app_id: int, excluded: bool) -> list[int]:
        """Exclude a game from automatic downloads (manual bulk download still works)."""
        ids = self._read_auto_download_excluded()
        if excluded:
            ids.add(int(app_id))
        else:
            ids.discard(int(app_id))
        path = self._settings_dir / "auto-download-excluded.json"
        path.write_text(json.dumps(sorted(ids)), encoding="utf-8")
        return sorted(ids)

    def _read_auto_download_excluded(self) -> set[int]:
        path = self._settings_dir / "auto-download-excluded.json"
        try:
            return {int(value) for value in json.loads(path.read_text(encoding="utf-8"))}
        except FileNotFoundError:
            return set()
        except Exception as error:
            self._log_warning(f"failed reading {path}: {error}")
            return set()

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
        self, app_id: int, video_url: str, source: str = "manual"
    ) -> dict[str, Any]:
        """Download a YouTube video's audio and assign it to a game.

        source: "manual" (picked on the game's music page) or "auto" (bulk or
        automatic download); recorded in the downloads index.
        """
        if app_id <= 0:
            raise ValueError("Invalid app id")
        if source == "auto" and str(app_id) in self._tracks:
            # Picked by hand (or reattached) while this automatic download was queued.
            return {"skipped": "has_track", "tracks": self._tracks}

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
        result = await self._run_with_retries(
            command, timeout=900, env=yt_dlp["env"], label=f"download app={app_id}"
        )
        if result.returncode != 0:
            raise RuntimeError(
                describe_youtube_error(self._command_error(result, "YouTube download failed"))
            )

        output_lines = [
            line.strip() for line in (result.stdout or "").splitlines() if line.strip()
        ]
        downloaded_path = self._extract_downloaded_path(output_lines, app_download_dir)
        if not downloaded_path:
            downloaded_path = self._find_latest_audio_file(app_download_dir)
        if not downloaded_path:
            raise RuntimeError("Download completed but no audio file was found")

        if source == "auto" and str(app_id) in self._tracks:
            # Music was assigned while downloading: keep it, just record the file.
            self._record_download(
                downloaded_path, app_id=app_id, youtube_id=video_id, source="auto"
            )
            self._log_info(f"youtube download kept existing track app={app_id}")
            return {"skipped": "has_track", "tracks": self._tracks}

        tracks = await self.set_track(app_id, str(downloaded_path), downloaded_path.name)
        self._tracks[str(app_id)]["youtube_id"] = video_id
        self._save_tracks()
        self._record_download(
            downloaded_path,
            app_id=app_id,
            youtube_id=video_id,
            source="auto" if source == "auto" else "manual",
        )
        self._log_info(
            f"youtube download assigned app={app_id} file={downloaded_path} source={source}"
        )
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

    def _read_non_steam_shortcuts(self) -> list[dict[str, Any]]:
        by_id: dict[int, dict[str, Any]] = {}
        for steam_root in self._get_steam_roots():
            userdata = steam_root / "userdata"
            if not userdata.exists():
                continue
            try:
                shortcut_files = list(userdata.glob("*/config/shortcuts.vdf"))
            except Exception as error:
                decky.logger.error(f"Failed listing shortcuts.vdf under {userdata}: {error}")
                continue
            for shortcut_file in shortcut_files:
                try:
                    entries = extract_non_steam_shortcuts(shortcut_file.read_bytes())
                except Exception as error:
                    decky.logger.error(f"Failed reading non-Steam shortcuts {shortcut_file}: {error}")
                    continue
                for entry in entries:
                    app_id = int(entry["appid"])
                    if app_id <= 0 or app_id in by_id:
                        continue
                    name = self._trim_message(entry["name"], 180)
                    by_id[app_id] = {
                        "appid": app_id,
                        "name": name,
                        "search_name": clean_game_search_name(name),
                        "launcher": is_launcher_shortcut_name(name),
                    }

        shortcuts = sorted(by_id.values(), key=lambda item: str(item["name"]).lower())
        self._log_info(
            "Non-Steam shortcut scan found "
            f"shortcuts={len(shortcuts)} launchers={sum(1 for item in shortcuts if item['launcher'])}"
        )
        return shortcuts

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

    async def _run_with_retries(
        self, command: list[str], *, timeout: int, env: dict[str, str], label: str
    ) -> subprocess.CompletedProcess[str]:
        """Run a yt-dlp command, retrying errors YouTube usually recovers from."""
        result = await self._run_command(command, timeout=timeout, env=env)
        for delay in YOUTUBE_RETRY_DELAYS_SECONDS:
            if result.returncode == 0:
                break
            message = self._command_error(result, "")
            if not is_retryable_youtube_error(message):
                break
            self._log_warning(f"{label} failed ({message}); retrying in {delay}s")
            await asyncio.sleep(delay)
            result = await self._run_command(command, timeout=timeout, env=env)
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
