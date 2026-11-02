# Changelog

## 3.1.7 - 2026-11-02
- Adds a disabled-by-default, opt-in background-app music setting below the launch stop timing controls (issue #8).
- Allows game/global/store music in the full Steam menu while apps run; stops when gameplay regains focus.
- Preserves default suppression, launch timing, sleep, and Desktop Mode behavior.

## 3.1.6 - 2026-11-02
- Integrates DrRedBird's YouTube support work from PR #28 for issues #25 and #27.
- Installs yt-dlp with recommended dependencies and a checksum-verified managed Deno runtime when needed.
- Adds optional Firefox cookies, disabled by default, with persistent settings and explicit downloader arguments.
- Shows yt-dlp/Deno readiness and actionable sign-in/challenge/403 error guidance.
- Preserves verified fallback selection, OS-update runtime repair, native M4A audio, and song storage management.

## 3.1.5 - 2026-11-02
- Adds song storage management with usage totals, largest-file listing, download/preview/unused filters, and permanent deletion.
- Adds explicit downloaded-file deletion beside game/global/store assignments; clarifies that Unassign music keeps the file.
- Adds cleanup of unused files, cached previews, and missing-file assignments.
- Protects shared assignments, local music outside managed folders, active downloads, and symlink paths during deletion.
- Prevents repeated automatic playback errors for inaccessible files until assignments change or the user retries manually.
- Saves assignments atomically and propagates save failures before deleting files.

## 3.1.4 - 2026-11-01
- Fixes YouTube previews and downloads when FFmpeg or FFprobe is missing by downloading M4A audio directly instead of converting to MP3.
- Preserves existing MP3 tracks and music assignments.
- Verifies downloader runtimes, skips broken installations, and attempts repair when no working runtime is available.
- Displays preview and download errors on the page and records full preview tracebacks in the debug log.
- Includes the Deck Shelves integration and assignment-date improvements described below.

## 3.1.1 - 2026-10-08
- Recovers estimated assignment dates for older YouTube downloads from audio-file creation times when available.
- Preserves recorded assignment dates and marks recovered dates as estimated.
- Leaves local files and downloads without a readable creation date undated; never uses modified/change times.

## 3.1.0 - 2026-10-08
- Adds optional Deck Shelves sources for games with music, without music, and recently assigned music.
- Adds music assignment filters and a most-recently-assigned sort.
- Refreshes shelves after assignments change and supports either plugin load order.
- Records assignment dates for new/replaced tracks; older assignments retain unknown dates.

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
