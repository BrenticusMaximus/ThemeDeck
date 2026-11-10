# ThemeDeck Documentation

<a href='https://ko-fi.com/U6U516PSAI' target='_blank'><img height='36' style='border:0px;height:36px;' src='https://storage.ko-fi.com/cdn/kofi5.png?v=6' border='0' alt='Buy Me a Coffee at ko-fi.com' /></a>

## Overview

ThemeDeck lets you add and manage custom music across your Steam library and key Steam UI pages.

<a href="https://discord.gg/qVsuGK6wm8">For support, suggestions, etc. please visit my Discord</a>.

## Install Package

**Latest release: [ThemeDeck v4.0.0](https://github.com/BrenticusMaximus/ThemeDeck/releases/tag/v4.0.0)** — [Download ThemeDeck-v4.0.0.zip](https://github.com/BrenticusMaximus/ThemeDeck/releases/download/v4.0.0/ThemeDeck-v4.0.0.zip).

1. Go to https://github.com/BrenticusMaximus/ThemeDeck/releases/ and download the latest ZIP, not the source code.

2. Put it anywhere on your steam deck where you'll be able to find it later.

3. On steam deck, go to decky settings, general, enable developer mode.

4. On steam deck, go to decky settings, developer, 'install plugin from zip file', and find the zip from step 2. 

## YouTube setup

Use **Install YouTube support** (or **Update YouTube support**) inside ThemeDeck. ThemeDeck installs `yt-dlp` with its recommended dependencies and installs a private Deno runtime when a supported Deno executable is not already available.

Firefox cookies are optional and disabled by default. YouTube may block ThemeDeck previews and downloads with sign-in or bot-verification checks. Firefox cookies can resolve this issue. Sign in to YouTube in Firefox on your Steam Deck, then enable **Use Firefox cookies for YouTube** in ThemeDeck. ThemeDeck passes this option directly to yt-dlp and does not modify your global yt-dlp configuration file.

![ThemeDeck June 29 2026 update thumbnail](https://images.steamusercontent.com/ugc/10246844756434218824/5BE3695A090A9AD263F22EE5F73C7CDA3B84CEB0/?imw=5000&imh=5000&ima=fit&impolicy=Letterbox&imcolor=%23000000&letterbox=false)

## ThemeDeck 4.0 — playlists and a compact music chooser

- Add unlimited songs to each game, global ambient music, and store music. Adding a song keeps your existing assignments. Reorder songs with the arrows or remove individual assignments without deleting their files.
- Use the same YouTube search, preview, download, and local-file options for games, ambient music, and store music. **Download** adds the first song; **Download & Add** appends another.
- Songs play in playlist order. **Loop playlist** repeats the sequence; disabling it stops after the last song. Volume and start skip apply across each playlist.
- The compact Now Playing card includes previous/play-pause/next controls, playlist position, and a countdown. Its music-settings icon opens the matching music chooser. All card buttons support controller navigation; pausing keeps the card size stable.
- YouTube search comes first in the redesigned chooser. Playlist settings, local files, and song storage open below their buttons, one section at a time. Volume and start-skip sliders use compact controls.
- Improved frequency grouping and smoothing in the audio visualizer, with recovery after loops/seeks and separate handling for silence and capture failures.
- Storage management recognizes all playlist members when listing files or deleting downloads.

Existing single-song assignments and settings are preserved when upgrading. Install the release ZIP through Decky's developer settings as usual.

## Main Features

- Add custom music to any game page in your library.
- Use either local music files or YouTube search to find tracks.
- Preview tracks before assigning them.
- One-tap **Download** or **Download & Add** from YouTube results.
- Auto-fill search terms based on the game you selected.
- Highlight which YouTube result is already assigned.
- Set per-game volume.
- Master volume control to override all game music.
- Skip silent intros with per-game "truncate start" timing.
- Remove or change a game's assigned track at any time.
- Auto-play music when opening game pages.
- Displays a live "Now Playing" card overlay on game pages.
- Includes a real, audio-reactive visualizer in the "Now Playing" card.
- Assign a global/ambient playlist for non-game areas.
- Assign a separate store playlist for Steam Store pages.
- Choose how ambient music behaves when interrupted (stop, pause, or mute until return).
- Optionally disable ambient music while in the Steam Store.
- Prevent all plugin music from playing in Desktop Mode.
- Prevent all plugin music from playing while a game is launched/running.
- Bulk auto-assign music to games that don’t have tracks yet.
- See live bulk progress and stop the process anytime.
- View a list of games still missing music.
- See live name-loading progress while that missing-games list is built.
- Works with both installed and uninstalled games in your library.

## Release Updates

## November 3, 2026 Update (v4.0.0)

- Major playlist release: unlimited tracks for games, ambient music, and store music, with reordering and automatic advancement.
- Unified YouTube/local music chooser with compact settings and inline storage management.
- Added controller-accessible playback controls, remaining time, and a direct music-settings shortcut on the Now Playing card.
- Improved visualizer response and recovery, and kept the card size stable when paused.
- Tested playlist additions, YouTube preview/download, settings persistence, and card navigation directly on a Steam Deck. Temporary test songs and settings were removed afterward.

## November 2, 2026 Update (v3.1.7)

- Added **Allow music while games/apps run in the background**, directly below **Stop music after pressing Play**. It is **disabled by default** for new and existing installations; enable it only if you want this behavior.
- When enabled, game themes, global/ambient music, and store music can play while browsing the full Steam menu with an app running in the background. Returning to gameplay stops ThemeDeck music; side overlays and the running-app screen do not restart it.
- Saves your choice between restarts and preserves the selected launch-stop timing.
- Tested game-theme and ambient playback, gameplay/menu transitions, quick access, toggle persistence, and launch-start timing directly on a Steam Deck. Existing music and assignments were preserved.

## November 2, 2026 Update (v3.1.6)

- Integrated [DrRedBird's YouTube support fixes](https://github.com/BrenticusMaximus/ThemeDeck/pull/28) for sign-in and JavaScript challenge failures reported in issues #25 and #27.
- **Update YouTube support** now installs the recommended downloader dependencies and sets up Deno when needed. Run this after upgrading to complete setup on an existing installation.
- Added optional **Use Firefox cookies for YouTube**, disabled by default. Enable only if YouTube requests verification, after signing into YouTube in Firefox on the same device.
- Added downloader/Deno readiness information and clearer guidance for 403, sign-in, and challenge errors. YouTube may still require verification or reject particular videos.
- Keeps direct M4A downloads and all v3.1.5 song storage features.

## November 2, 2026 Update (v3.1.5)

- Added **Song storage** to manage downloaded songs and cached previews, see space usage, and find the largest files.
- Added **Delete from disk** with confirmation, plus cleanup of unused files and cached previews. Deleting an assigned file also clears its affected music assignments.
- Renamed the old removal action to **Unassign music** to make clear that it keeps the audio file. Permanent deletion is now a separate action on game, global, and store music pages.
- Added cleanup of missing-file assignments and stopped repeated automatic playback errors for inaccessible files.
- Tested installation and storage deletion on a Steam Deck; existing music and assignments were preserved.

## November 1, 2026 Update (v3.1.4)

- Fixed YouTube previews and downloads failing with “ffprobe and ffmpeg not found.” New YouTube audio downloads use M4A directly, without converting to MP3 or requiring FFmpeg/FFprobe. Existing MP3 tracks continue to work.
- Added downloader runtime checks, fallback selection, and automatic repair when no working downloader is available.
- Preview and download errors remain visible on the page, and preview failures include full debug-log tracebacks.
- Includes optional Deck Shelves integration for games with music, games without music, and recently assigned music, plus assignment-date recording and recovery. See the integration details below.


## September 6, 2026 Update (v3.0.2)

- Improved sleep/wake behavior for global ambient music.
- ThemeDeck now releases browser audio and visualizer resources before sleep and rebuilds them after wake.
- Fixed stale playback state that could prevent global ambient music from resuming.

## June 30, 2026 Update (v3.0.1)

- Fixed bulk auto-assign library detection when Steam's frontend library cache reports zero games.
- Added a backend Steam library scan so "all games", "installed games", "uninstalled games", and "games without music" use the Deck's actual Steam library files.

## June 29, 2026 Update (v3.0.0)

- Added controller-first navigation for assigning music from the "Choose ThemeDeck music..." screen.
- You can now use the D-pad plus A/B buttons to search YouTube, preview tracks, download and assign tracks, and browse local files while docked or using an external controller.
- Controller controls for YouTube results:
  - D-pad left/right moves between YouTube search results.
  - D-pad up/down switches between **Play Preview** and **Download & Assign** inside the current result.
  - Press A on **Play Preview** to start or stop a preview.
  - Press A on **Download & Assign** to download that result and assign it to the current game.
  - Press B to go back.
  - From the first result, D-pad left returns to the search controls.
  - From the last result, D-pad right moves down to **Or, browse local files**.
- Improved YouTube search handling for game names with special characters, including trademark symbols.
- Added local cached previews so YouTube preview playback works more reliably in Gaming Mode.
- Added clearer **Currently assigned** highlighting when a YouTube search result matches the track already assigned to the game.
- Added extra ThemeDeck debug logging at `/home/deck/ThemeDeck/themedeck-debug.log`.

## April 27, 2026 Update (v2.6.0)

- Added a ThemeDeck master volume override at the bottom of settings.
- At 100%, ThemeDeck respects each game/global/store track volume; below 100%, all ThemeDeck music plays at the selected master level.

## April 21, 2026 Update (v2.5.5)

- Added a "Now Playing" overlay card that shows the current track and source context.
- Added a real audio-reactive visualizer tied to the active music playback.
- Improved visualizer reliability across game-to-game navigation by rebuilding audio analysis when track sources change.

## March 3, 2026 Update (v2.5.4)

This update includes UI and playback behavior improvements:

- Moved per-game controls (Volume, Start skip, Loop track) from the long main settings list into each game page.
- Added a per-game Play/Pause preview button beside Remove music on each game page.
- Fixed playback precedence on game pages: assigned game music now takes priority; if a game has no assigned track, global ambient continues.
- Fixed context-menu behavior so pressing Start on a game from home/library no longer starts that game music outside the full game page.

## February 28, 2026 Update (v2.5.3)

- Improved playback stability so global/ambient audio no longer conflicts with per-game playback during navigation/launch transitions.
- Added per-track loop control for game, global, and store tracks so each assignment can loop or play once.

## February 27, 2026 Update (v2.5.2)

- Added finer control for when game music stops: launch start or launch finish.
- Added a dedicated store-track enable/disable control.

## February 25, 2026 Update (v2.5.1)

- Fixed a critical launch-state issue so ThemeDeck does not play global/ambient or game-page music while a game is running.

## February 25, 2026 Update (v2.5.0)

- Added bulk auto-assign for games without music.
- Added a "Show games without music" list with live name-resolution progress.
- Improved game ID handling to reduce duplicate/alias entries.

## February 25, 2026 Update (v2.4.2)

- Prevented global/ambient auto-play inside ThemeDeck assignment pages, so global music does not play while selecting or assigning per-game tracks.

## February 24, 2026 Update (v2.4.1)

- Ensured ThemeDeck does not play any music tracks while Steam is in Desktop Mode.

## February 24, 2026 Update (v2.4.0)

- Added an optional **store-only music track** that plays only on Steam Store pages.
- Included independent preview, volume, remove, and truncate-start controls for the store track.

## February 23, 2026 Update (v2.3.0)

- Added an optional **global/ambient music track** for non-game pages.
- Included separate volume and playback controls for the ambient track.

## February 21, 2026 Update (v2.2.0)

- Added support for assigning ThemeDeck music to games that are not installed yet, as long as the game has a Steam game page.

## February 21, 2026 Update (v2.1.0)

- Added per-game **Truncate beginning of song** (0-30 seconds) so users can skip silent intros with a custom start offset.

## February 19, 2026 Update (v2.0.0)

- Added **YouTube search/download support powered by `yt-dlp`** for searching, previewing, downloading, and assigning game music directly in ThemeDeck.
- Kept support for manually assigning local music tracks.

<a href='https://ko-fi.com/U6U516PSAI' target='_blank'><img height='36' style='border:0px;height:36px;' src='https://storage.ko-fi.com/cdn/kofi5.png?v=6' border='0' alt='Buy Me a Coffee at ko-fi.com' /></a>

## Deck Shelves integration (v3.1.0)

With Deck Shelves installed, ThemeDeck automatically registers three external shelf sources: **ThemeDeck: Games with music**, **ThemeDeck: Games without music**, and **ThemeDeck: Recently assigned music**. Select one in the Deck Shelves shelf editor. Music means a per-game ThemeDeck assignment; global/store tracks do not count. The without-music source combines ThemeDeck’s Steam library discovery with Steam’s live game and non-Steam shortcut list.

For combinations such as installed games with music, use the **Has music assigned** or **Has no music assigned** filters with the other Deck Shelves criteria. Choose **Most recently assigned music** to sort by assignment date. New and replaced assignments record their date; older YouTube assignments use estimated file-creation dates when available, and undated assignments appear after dated ones, and games without music appear last. Shelves refresh when assignments change. ThemeDeck also works without Deck Shelves.

### Assignment date recovery (v3.1.1)

ThemeDeck keeps recorded assignment dates first. On startup, older YouTube assignments without a date can recover an estimated date from the assigned audio file’s creation time (including Linux filesystems exposing birth time through GNU stat). Recovered dates are saved with `assigned_at_estimated: true` and `assigned_at_source: "file_creation"`. Missing files, filesystems without creation times, and ordinary local-file assignments remain undated. Modified times and inode change times are never used. Copying or restoring a download may change its creation date, so these dates are estimates. Replacing the track records a fresh, exact assignment date.

## Song storage management (v3.1.5)

Open **Song storage → Manage downloaded songs and preview cache** in ThemeDeck. The page shows total download/cache usage and files sorted largest first. Filter by downloads, previews, or unused files. Use **Delete from disk** for an individual file, **Clear cached previews**, or **Delete all unused files**. Permanent deletion requires confirmation; assigned files show every affected game/global/store assignment. Cleanup keeps files that are still assigned.

**Unassign music** removes the assignment and keeps the file. For a ThemeDeck download, **Delete downloaded file from disk** also appears on the assignment screen. Confirming it deletes the file and clears all assignments using it. Music outside ThemeDeck's download/cache folders is never deleted by these controls. If files were deleted manually, **Clear missing-file assignments** removes their broken references. Failed automatic playback is not retried continuously; an assignment change or an explicit Play action allows another attempt.

Deletion is paused while ThemeDeck is preparing a preview or downloading audio. Refresh the storage page once the transfer finishes. Preview files can be downloaded again after clearing the cache. This build manages existing storage; bulk song matching and its search duration filter are unchanged.


## Background app music (v3.1.7)

Below **Stop music after pressing Play**, enable **Allow music while games/apps run in the background** to hear game-page, global/ambient, or store music while browsing the full Steam menu with an app still running. The setting is off by default and is saved between restarts. Returning to gameplay stops ThemeDeck audio; the running-app screen and side overlays do not start it. Existing launch timing, sleep, and Desktop Mode restrictions still apply.

## Localization

ThemeDeck follows the language selected in the Steam client. English is the source language and the fallback, and French is bundled.

Translations live in `src/locales/`, keyed by the English source string. Untranslated or newly added strings automatically fall back to English, so a missing entry never breaks the interface.

```ts
import { formatDateTime, t } from "./i18n";

t("Auto play on game page");
t("Skipped {game} (already assigned).", { game: gameName });
formatDateTime("2026-10-24T18:30:00Z");
```

`formatDateTime` renders timestamps through `Intl.DateTimeFormat` in the current Steam language, so dates follow local conventions instead of one fixed layout, and times are shown in the local timezone. When a timestamp also identifies a build, keep an unambiguous value next to the localized one, the way the settings tab pairs the formatted build time with `BUILD_ID`.

To add a language, create `src/locales/<code>.ts`, register it in `src/i18n.ts`, and map its Steam locale names to the new language there. Keep `{placeholder}` names identical to the English source.
