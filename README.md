# ThemeDeck

ThemeDeck lets you attach local audio files (MP3/AAC/FLAC/OGG) to specific titles in your Steam library and plays them automatically whenever you open that game's details page in Gaming Mode.

## Highlights

- Uses Decky's file picker so you can browse your microSD or internal storage without leaving Gaming Mode.
- Stores per-game associations in Decky's settings directory and survives reboots.
- Plays music instantly when you land on a game's details page and fades it out when you navigate away.
- Quick controls inside the Decky tab to preview, pause, or swap a game's track.

## Usage

1. Open a game's details page in Gaming Mode (the one with the big **Play** button).  
   • If automatic detection fails, pick the game manually in the ThemeDeck panel's fallback dropdown.  
2. Open the Decky tab and launch ThemeDeck.
3. Press **Select music file**, browse to your MP3/AAC/FLAC/OGG file, and confirm. ThemeDeck links it to the auto-detected (or manually selected) game.
4. Revisit the game's page at any time—the music starts automatically.
5. Use the ThemeDeck panel to pause, resume, adjust per-game volume, or remove the association.

## Development

Requirements:

- Node.js 18+
- `pnpm` 9 (`npm i -g pnpm@9`)
- Decky Loader 3.0+

Install dependencies and build:

```bash
pnpm install
pnpm run build
```

For iterative work, keep rollup in watch mode:

```bash
pnpm run watch
```

Deploy to your Deck with the Decky CLI:

```bash
decky plugin build --skip-backend
decky plugin install --copy=dist --name=themedeck
```

## Packaging

When publishing, include:

```
ThemeDeck/
├─ dist/
├─ package.json
├─ plugin.json
├─ main.py
├─ README.md
└─ LICENSE
```

Submit a pull request to the [Decky Plugin Database](https://github.com/SteamDeckHomebrew/decky-plugin-database) or host the zip yourself for manual installs.
