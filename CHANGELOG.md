# Changelog

## Unreleased
- Smarter theme search: Steam games are searched by their own name from Wikidata (looked up by Steam app ID, no API key, cached); games not on Wikidata keep their full Steam name, only dropping ™/®/©.
- YouTube results are scored (main/menu theme, 1–12 minute length, view count) and trailers, gameplay, covers, remixes and hour-long loops are ranked down. Bulk auto-assign picks the best-scoring result and falls back to the previous search if nothing scores well.
- Manual searches on the music page are sorted by the same score (nothing is hidden), the search box is pre-filled with "<game> main theme", and games without music search automatically when the page opens (online only).
- The music page shows the current track's YouTube thumbnail and title, or a music icon for local files.

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
