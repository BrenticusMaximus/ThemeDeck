# Changelog

## Unreleased
- Smarter theme search: Steam games are searched by their own name from Wikidata (looked up by Steam app ID, no API key, cached); games not on Wikidata keep their full Steam name, only dropping ™/®/©.
- YouTube results are scored (main/menu theme, 1–12 minute length, view count) and trailers, gameplay, covers, remixes and hour-long loops are ranked down. Bulk auto-assign picks the best-scoring result and falls back to the previous search if nothing scores well.
- Manual searches on the music page are sorted by the same score (nothing is hidden), the search box is pre-filled with "<game> main theme", and games without music search automatically when the page opens (online only).
- The music page shows the current track's YouTube thumbnail and title, or a music icon for local files.
- Bulk auto-assign can now include non-Steam shortcuts (read from `userdata/*/config/shortcuts.vdf`), behind an "Include non-Steam shortcuts" toggle (on by default).
- Adds a "Skip launcher and app shortcuts" toggle (on by default) so shortcuts like Battle.net, EA App or Ubisoft Connect are not given game music.
- Cleans shortcut names before searching YouTube (drops tags like "(USA)" or "[GOG]" and trademark symbols).
- "Download music for new games" (off by default): when Steam reports a library change (checked ~15 s later) or every 30 minutes, newly installed games — including owned games installed later, reinstalls and new non-Steam shortcuts — get a track in the background via the smart search. Opening an installed game's page without music also queues it. Downloads never run while a game is running, in Desktop Mode or offline. Enabling it first records the current library, so it doesn't download for every game.
- Per-game "Download music automatically for this game" switch on the music page; excluded games are skipped by automatic downloads but still included in the manual bulk download. Removing a game's music doesn't change the switch; with automatic downloads on, the game may get music again on the next visit.
- Bulk and automatic downloads reuse a kept download for the game before searching YouTube (hand-picked first, then the newest auto-picked).
- YouTube downloads and searches retry temporary errors (403/429/5xx, "not a bot", timeouts, network resets) after 3 s and 10 s; automatic downloads pause for 30 minutes when YouTube rate-limits. Errors now say what happened (rate limited, ffmpeg missing, video unavailable).
- An automatic or bulk download no longer replaces music that was picked or reattached while it was running.
- Error details are kept in the debug log instead of empty messages.
- Now playing on the game page can be shown as a play bar button left of the controller icon (Steam's own button style, reachable with the D-pad) instead of the floating card. Press it to pause or resume the game's music; it stays paused until resumed or the page is left. Falls back to the card if the button can't be placed.
- Play bar button display: "Always expanded" (artwork, title and play state) or "Expand on press" (thumbnail with a play/pause mark; first press expands, the next pauses or resumes).
- Settings: choices use bulleted rows that work with the D-pad, sub-options only show under the selected choice, and the general section's buttons use Steam's own button rows.
- "Manage music" section: shows how many games have music and how much space downloads use (auto-picked vs hand-picked, and unused).
- "Remove music from all games…" with a confirmation and a choice of what to delete: auto-picked downloads (default), all ThemeDeck downloads, or nothing. Global/store tracks and the user's own music files are never touched.
- "Delete unused auto-picked downloads" and "Delete all unused downloads" free space without changing any game's music.
- Downloads are recorded in `downloads/index.json` with their game, video and whether they were picked by hand or by bulk/automatic download (older files count as auto-picked).

## 3.0.2 - 2026-09-06
- Stops and releases browser audio and visualizer resources before system sleep.
- Rebuilds playback state after wake and resumes eligible global ambient music.
- Recovers when Steam suspends the audio element but ThemeDeck's playback state is stale.

## 2.5.5 - 2026-04-21
- Adds a "Now Playing" overlay card that displays the active track while browsing game pages.
- Adds a real audio-reactive visualizer synced to active playback.
- Fixes visualizer reliability across game-to-game transitions by rebuilding analysis bindings when sources change.

## 2.4.2 - 2026-02-25
- Prevents global/ambient auto-play while inside ThemeDeck track-assignment screens.
- Stops global ambient playback when entering ThemeDeck assignment routes to avoid overlap during per-game selection.

## 2.4.1 - 2026-02-24
- Prevents ThemeDeck from playing any game/global/store music tracks while Steam is in Desktop Mode.

## 2.4.0 - 2026-02-24
- Adds an optional store-only track that plays only on Steam Store pages.
- Adds store-only track controls for preview, remove, volume, and start-truncation.
- Keeps existing game-page and global/ambient playback behavior while adding dedicated store context routing.

## 1.1.0 - 2025-11-18
- Fixes ThemeDeck context-menu injection so assigning music works again on SteamOS 3.7.17 (Steam Client build date Nov 17 2025).
- Displays build timestamp more clearly in the settings panel and bumps the published Decky version number.
