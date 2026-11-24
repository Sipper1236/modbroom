# ModBroom

A free, local desktop app for **The Sims 4** that finds broken, duplicate, conflicting and risky mods — no account, no subscription, no network calls, and nothing leaves your machine.

It is the grown-up answer to "which of these 1,400 files is crashing my game."

## What it does

- **Real DBPF parsing** — reads the actual binary `.package` format (header, index, zlib resources). Not filename guessing.
- **Diagnostics** — conflicts (same resource ID in multiple packages), duplicates (byte-identical and identical-resource-set), truncated/corrupt packages, unreadable files.
- **Script-mod analysis** — scans `.ts4script` archives for risky patterns (`os.system`, `exec`, network calls, Discord webhooks, `ctypes`, obfuscation).
- **Crash-log reader** — parses `LastException`/crash logs and ranks your script mods by suspicion.
- **50/50 bisect that actually works** — ModBroom physically moves half your suspect files out of Mods, you launch the game and say whether it still breaks, and it repeats until it names the one file. Automatic backup first; everything reversible.
- **Quarantine** (reversible) and **permanent delete**.
- **Backups** (zip of your Mods folder), **manifest export** (JSON), **CSV export**.
- **Crash-proof paths**: OneDrive-redirected Documents, `.ts4script` nested too deep for the game to load, loose `.py` files the game ignores, `>259` char paths, dotfiles, zero-byte files, and the in-game checkboxes the game silently resets.
- **In-game companion** (optional): a real script mod (`ModBroomBridge.ts4script`) that adds `mb_status`, `mb_stats`, `mb_find`, `mb_help` cheat commands so you can ask the game about your Mods folder.
- **Demo library** if you have no game here — one click builds a synthetic Mods folder with every failure mode represented.

## Run it

**Windows (the target platform)**

1. Install Python 3.10+ from python.org (tick "Add to PATH").
2. `pip install -r requirements.txt`
3. Double-click `run.bat`, or `python -m modbroom`

**Linux/macOS (for development)**

```
pip install -r requirements.txt
./run.sh
```

**Build a single-file Windows .exe**

```
pip install pyinstaller PySide6-Essentials
pyinstaller modbroom.spec
```
`dist/ModBroom.exe` needs no Python install. (Built and smoke-tested on Linux; the Windows exe is produced by the same `modbroom.spec` on a Windows machine.)

## First run

1. Hit **Scan now**. ModBroom auto-detects the usual Windows location (`Documents\Electronic Arts\The Sims 4\Mods`); if you keep it elsewhere, set it in **Settings**.
2. Read **Dashboard** for the headline, **Diagnostics** for the details.
3. Nothing is changed until you click something. Quarantine is always reversible from **Tools**.

No Sims 4? **Settings → Load demo library** builds a fake Mods folder so every feature works end to end.

## The in-game companion

**Companion** tab → **Install into my Mods folder**. Then in game: enable *Custom Content and Mods* and *Script Mods Allowed* in Options → Other, restart, open the cheat console (Ctrl+Shift+C), and type `mb_help`.

> Honest status: the companion is written against the public Sims 4 script-mod API (`sims4.commands`, `CheatOutput`). It is syntax-checked and packaged correctly, but **it has not been run inside the game** — there is no Sims 4 on the machine that built it. If a command does nothing in-game, that is why; the desktop app does not depend on it.

## The 50/50 wizard, in detail

1. Pick the suspects (Diagnostics pre-selects them).
2. ModBroom zips your whole Mods folder to `~/.modbroom/backups`, then moves half the suspects out of Mods.
3. You launch the game and reproduce (or not).
4. Click **Still broken** or **It's fixed**. The surviving half is split again.
5. When one file remains it is moved aside and named. Everything else is put back.

Every step is reversible from **Tools → Quarantine**; a pre-bisect backup is always taken first.

## Layout

```
modbroom/
  dbpf.py         DBPF parser (header / index / zlib resources)
  scanner.py      walk Mods, duplicates, conflicts, integrity, script risk, usage
  game_rules.py   Sims-4-specific loading rules (depth, OneDrive, path length…)
  crashlog.py     crash-log parsing + suspect ranking
  bisect.py       the 50/50 engine (moves real files, with backup + undo)
  bridge.py       builds ModBroomBridge.ts4script + writes partner.json
  companion_src/  the in-game script mod (Python, zipped as .ts4script)
  store.py        settings, quarantine, backups, state
  core.py         scan pipeline shared by UI and CLI
  cli.py          headless scan (python -m modbroom --cli-scan)
  ui/             PySide6 app (theme, pages, widgets)
```

## Honest limits

- It cannot tell you a mod is *safe*, only that it shows no known-risky patterns. Obfuscation defeats pattern matching.
- "Unused CC" means "no references found in your saves/Tray" — a hint, not proof.
- It does not repair `.package` files; it finds problems and moves files.
- The in-game companion has not been executed inside the real game.
- Not affiliated with Electronic Arts or Maxis.
