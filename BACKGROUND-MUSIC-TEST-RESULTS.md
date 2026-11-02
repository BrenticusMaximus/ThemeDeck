# Background app music test results

Local build: **3.1.7-test.2**, November 2, 2026. Based on published v3.1.6. Not published to GitHub; issue #8 remains open.

The opt-in toggle is directly below **Stop music after pressing Play**. It defaults off, persists between plugin reloads, and applies to game, global/ambient, and store music. It requires the full Steam menu to be foreground; the running-app screen and side overlays cannot restart music. New launches retain the selected stop timing.

## Live Steam Deck checks

- Installed on brent-steamdeck-oled.local; Decky service active.
- Confirmed the rendered toggle location and operated the actual UI checkbox.
- With the toggle off, a running Balatro suppressed ThemeDeck music on its library page.
- With the toggle on and Balatro still running, library-page theme audio played and its playback position advanced.
- Returning to the actual Balatro window stopped ThemeDeck audio. Returning to the library resumed it.
- Temporarily enabling the existing ambient assignment allowed ambient audio in the full menu while Balatro remained running; playback position advanced.
- Ambient audio stopped in gameplay and stayed stopped in the quick-access overlay, then resumed in the full menu.
- An enabled toggle survived a plugin/service reload.
- With background playback enabled and At launch start selected, launching Balatro stopped music without immediately restarting it; returning to the menu resumed music.
- Turning the toggle off restored running-app suppression.
- Restored all pre-test ThemeDeck preferences and left the new option off. Closed the game launched for testing.
- Verified all **60 existing music files** by path, size, and modification timestamp, and all **24 assignments** by the unchanged tracks.json SHA256.

## Automated checks

Production playback-policy, running-app transition, and game/global/store resolver checks cover default-off, toggle changes, gameplay, unknown focus, side overlays, the running-app screen, pending launches, deliberate menu return, and checks after asynchronous audio preparation. TypeScript with skipLibCheck, frontend production build, storage UI, Deck Shelves, error-display regression checks, and ZIP integrity checks passed.

## Limits

Live playback was verified from the real browser audio element (paused state and advancing playback position); no listening test was performed. Physical controller navigation, actual sleep/wake, Desktop Mode switching, and a live store-specific assignment were not tested in this change. Store-track selection was tested automatically. The installed Pause Games plugin was present, but its manual pause controls were not explicitly exercised.

## Backup and artifact

Previous installation and assignment backup:
`/home/deck/homebrew/plugin-backups/ThemeDeck-before-background-20261102-113416`

Installable local ZIP: `ThemeDeck-v3.1.7-background-music-test.zip`

SHA256: `a1c3da8d426025c36a04fa2a6ec2bf363c6b9d54b7aab663fc91eda72fd7f8e0`
