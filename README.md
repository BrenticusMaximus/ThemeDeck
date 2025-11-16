## Overview

ThemeDeck is a Decky Loader plugin that associates locally stored music files with specific Steam games. When you open a game's detail page in Gaming Mode, the plugin automatically locates the matching track, streams it into a shared looping `HTMLAudioElement`, and fades playback out as soon as you leave the page. All selections are stored on the Deck under the plugin's settings directory so they survive reboots and Decky updates.

<img width="1280" height="800" alt="20251116-043519-UTC" src="https://github.com/user-attachments/assets/db8bed0b-5381-4709-9dd9-0dc968317d88" />


<img width="1280" height="800" alt="20251116-043551-UTC" src="https://github.com/user-attachments/assets/010211d6-8f31-4cd5-8c3e-e1e3d8e6528d" />


<img width="1280" height="800" alt="20251116-043511-UTC" src="https://github.com/user-attachments/assets/a95e3ecc-dd57-4082-b822-e191356e55cb" />
<br><br>


<a href='https://ko-fi.com/U6U516PSAI' target='_blank'><img height='36' style='border:0px;height:36px;' src='https://storage.ko-fi.com/cdn/kofi5.png?v=6' border='0' alt='Buy Me a Coffee at ko-fi.com' /></a>


## Installation

1. Download the latest ZIP release.
2. Transfer ZIP to your Steam Deck, either its internal or external storage.
3. Go to Decky settings, Developer, Install Plugin from ZIP file.

## Supported File Types

- `mp3`, `aac`, `flac`, `ogg`, `wav`, `m4a`
- The frontend file browser only shows those extensions, and the backend advertises the surrounding MIME types when it returns the encoded audio payload. Unsupported files are ignored.

## Data Flow

1. **Track discovery**
   - The frontend exposes a file browser via `/themedeck/:appid`, reachable from the Decky tab or the Library context menu entry "Choose ThemeDeck music…".
   - Browsing is powered by the backend `list_directory` call, which enumerates folders/files under `/home/deck` (or any manually entered path) while skipping unreadable entries.

2. **Selection**
   - Picking a file invokes `set_track(app_id, path, filename)`, which verifies the file exists, is readable, and then writes a JSON record to `tracks.json`. Each record stores `{app_id, path, filename, volume}`.
   - The frontend emits a `themedeck:tracks-updated` event so every view refreshes its cached track map.

3. **Playback**
   - When a game detail page is opened, a hidden `GameFocusBridge` component looks up the matching `GameTrack` from the React state tied to `get_tracks()`.
   - `playTrack` resolves the audio by calling `load_track_audio(path)`; that backend method reads the file, base64-encodes it, and returns metadata used to create an object URL. Object URLs are cached per path and invalidated whenever a track changes or is removed.
   - The shared audio element loops the file, applies the saved per-game volume, and reports play/pause status to any UI preview buttons.

4. **Stopping**
   - Leaving the page or manually pausing fades the audio out (8 steps over ~320 ms) before rewinding and freeing the source URL. This prevents overlapping playback during rapid navigation.

## Frontend Details

- **Main panel**
  - Shows build info, quick instructions, and the auto-play toggle. Auto-play is stored in `localStorage` (`themedeck:autoPlay`) so it mirrors Gaming Mode’s behavior even before Decky finishes loading.
  - Lists every assigned track with:
    - Preview / pause buttons (manual playback keeps `reason="manual"` so in-page auto-play logic will not override it).
    - Remove buttons with confirmation prompts.
    - A per-game volume slider (0–100%). Adjusting the slider immediately applies gain to the actively playing track and persists via the backend `set_volume`.

- **Change Theme page**
  - Displays the currently linked file (name and absolute path) together with remove and done buttons.
  - Provides directory controls (Go Up, manual path entry, folder/file lists). Files are filtered by the supported extensions; picking one immediately saves and toasts feedback.

## Focus & Auto-Play Detection

- A polling watcher (`startLocationWatcher`) reads the focused Steam UI window's pathname every 750 ms to capture route changes that do not fire SteamClient events.
- Parallel `SteamClient.Apps` subscriptions (`startSteamAppWatchers`) listen for app overview/detail updates; whenever a game ID is detected, `notifyFocus` broadcasts it.
- Library app routes (`/library/app/:appid`, `/library/details/:appid`, and collection variants) are patched to inject `GameFocusBridge`, which:
  - Watches `autoPlay` and the active track list.
  - Starts playback when a matching track exists and auto-play is enabled.
  - Stops playback (with fade-out) when navigating away, when no track exists, or when auto-play is disabled.
- The same focus signal is used by the patched Library context menu to preselect the correct app before opening the `/themedeck/:appid` route.

## Storage & State

- **tracks.json** – lives under `decky.DECKY_PLUGIN_SETTINGS_DIR`, contains every `{app_id, path, filename, volume}` record. It is loaded on startup and persisted after any change.
- **Audio cache** – in-memory `Map<path, {objectUrl, mtime}>` so multiple navigations do not require re-reading files. Cache entries are revoked via `URL.revokeObjectURL` when the track list changes or an individual entry is removed.
- **Preferences** – only auto-play is stored client-side; all other settings live in `tracks.json`.

## Error Handling

- File selection validates existence and permissions before saving. Permission or missing-file errors are surfaced through Decky toasts so users know why a track failed to attach.
- Playback failures (e.g., deleted files) are handled by reporting the error, clearing the audio element, and stopping playback to avoid hung audio threads.
- Directory enumeration gracefully skips entries that raise `PermissionError`, keeping the browser responsive even when encountering protected paths.

## Typical Workflow

1. Navigate to a game's detail page.
2. Choose **Settings → Choose ThemeDeck music…**
3. Browse to the desired local audio file and select it. ThemeDeck stores the association and immediately refreshes the Decky panel.
4. Return to the game's detail page. If auto-play is enabled (default), the music starts instantly. Use the Decky panel to adjust per-game volume, preview, pause, or remove the track at any time.

<a href='https://ko-fi.com/U6U516PSAI' target='_blank'><img height='36' style='border:0px;height:36px;' src='https://storage.ko-fi.com/cdn/kofi5.png?v=6' border='0' alt='Buy Me a Coffee at ko-fi.com' /></a>


