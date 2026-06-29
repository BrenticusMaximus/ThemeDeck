# ThemeDeck Documentation

<a href='https://ko-fi.com/U6U516PSAI' target='_blank'><img height='36' style='border:0px;height:36px;' src='https://storage.ko-fi.com/cdn/kofi5.png?v=6' border='0' alt='Buy Me a Coffee at ko-fi.com' /></a>

## Overview

ThemeDeck lets you add and manage custom music across your Steam library and key Steam UI pages.

<a href="https://discord.gg/Smh4K5Ad">For support, suggestions, etc. please visit my Discord</a>.

## Install Package

1. Go to https://github.com/BrenticusMaximus/ThemeDeck/releases/ and download the latest ZIP, not the source code.

2. Put it anywhere on your steam deck where you'll be able to find it later.

3. On steam deck, go to decky settings, general, enable developer mode.

4. On steam deck, go to decky settings, developer, 'install plugin from zip file', and find the zip from step 2. 

![ThemeDeck February 19 2026 update thumbnail](https://images.steamusercontent.com/ugc/10217922894651388729/0056712F90842A587703E222C9AD211D53B2344E/?imw=5000&imh=5000&ima=fit&impolicy=Letterbox&imcolor=%23000000&letterbox=false)

## Main Features

- Add custom music to any game page in your library.
- Use either local music files or YouTube search to find tracks.
- Preview tracks before assigning them.
- One-tap "Download & Assign" from YouTube results.
- Auto-fill search terms based on the game you selected.
- Highlight which YouTube result is already assigned.
- Set per-game volume.
- Master volume control to override all game music.
- Skip silent intros with per-game "truncate start" timing.
- Remove or change a game's assigned track at any time.
- Auto-play music when opening game pages.
- Displays a live "Now Playing" card overlay on game pages.
- Includes a real, beat-reactive audio visualizer in the "Now Playing" card.
- Assign a global/ambient track for non-game areas.
- Assign a separate store-only track for Steam Store pages.
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

## June 29, 2026 Update (v3.0.0)

- Added controller-first navigation for assigning music from the "Choose ThemeDeck music..." screen.
- You can now use the D-pad plus A/B buttons to search YouTube, preview tracks, download and assign tracks, and browse local files while docked.
- YouTube results now have per-result **Play Preview** and **Download & Assign** buttons, so you no longer need to select a result and scroll back to shared buttons.
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
