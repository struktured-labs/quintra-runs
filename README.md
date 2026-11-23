# Quintra runs

Public playtest log for [Quintra](https://github.com/struktured-labs/quintra), a Game Boy Color action roguelike.

Each recorded run has a page with per-stage times, death causes, screenshots, a short GIF, an MP4, commentary, and a `run.json` download. These are machine and (later) human-style playtests used to measure balance and catch bugs.

**Live site:** <https://struktured-labs.github.io/quintra-runs/>

**This repository never contains ROMs, SRAM dumps, emulator save-states, or the itch password.** The cartridge is built from the game repo; this site is evidence of play, not a distribution channel.

## Add a new run

1. Record a run into its own folder named with the run id (for example `20261123-1620-285670f7-easy-corvin-v8/`). The folder must contain `run.json` plus any media you want published: `screenshots/*.png`, `gameplay.mp4`, `gameplay-open.gif`, `commentary.md`, and `telemetry.json`.
2. Keep a local archive of *every* run folder you want listed. Rebuild from that archive:

   ```sh
   python3 scripts/build_site.py --src /path/to/run-archive --out .
   ```

   You can pass `--src` more than once. The generator also reads any existing `runs/*/run.json` already in the output tree, so to add one new run to a checkout:

   ```sh
   cp -a /path/to/20261123-...-new-run ./incoming/
   python3 scripts/build_site.py --src ./incoming --src ./runs --out .
   rm -rf ./incoming
   ```

3. The build copies only approved media (`.json`, `.png`, `.gif`, `.mp4`, `.webm`, `.md`, and a few image types). It refuses `.gbc`, `.gb`, `.sav`, `.srm`, `.pyboy`, `.state`, and anything that looks like a password file, and it fails if a video is 50 MB or larger. A tree scan runs at the end of every build.
4. Commit the generated pages and media, then push to `main`. GitHub Pages deploys from the root of `main`.

Manual scan (the build already does this):

```sh
python3 scripts/build_site.py --scan-only --out .
```

## What is not published

- Game Boy ROMs or ROM downloads
- SRAM / save files / emulator states
- The itch password, tokens, or credentials
- Incomplete run folders that have no `run.json`
- Raw `events.jsonl` streams (the public telemetry export is `telemetry.json`)
- Class-select timing probes and other scratch / tool folders
