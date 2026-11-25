# How ModBroom compares to the open-source tools

This is a feature comparison against the free/open tools commonly used for The Sims 4 mod
problems. It is written from each project's public documentation and source, not from
benchmarks we ran on other people's machines. Where ModBroom does not do something, it says so.

| Capability | ModBroom | simscan (caseone115) | sims4-mod-detector (Mecapixel) | SimsForge |
|---|---|---|---|---|
| Reads `.package` DBPF binary format | ✅ own parser | ✅ | partial (heuristic) | ✅ |
| Reads EA **RefPack** compressed resources | ✅ | ✅ | ❌ | partial |
| Content-hash duplicate detection | ✅ (byte-identical + identical resource-set) | ✅ | ✅ | ✅ |
| TGI conflict detection | ✅ | ✅ | ❌ | ✅ |
| **Conflict winner named** (Resource.cfg load order) | ✅ | ✅ | ❌ | partial |
| Load-order / Resource.cfg view | ✅ | ✅ | ❌ | ❌ |
| Truncated / corrupt package detection | ✅ | partial | ✅ | ❌ |
| Script-mod risk scan (`.ts4script`) | ✅ (`os.system`, `ctypes`, network, webhooks…) | ✅ | ❌ | ❌ |
| Crash-log (`LastException`) parsing & suspect ranking | ✅ | ✅ (Better Exceptions logs) | ❌ | ❌ |
| One-click **50/50 bisect** (moves files back and forth, backup + undo) | ✅ | ❌ (manual process) | ❌ | ❌ |
| Quarantine + restore | ✅ | disable-to-`_disabled` rename | ❌ | manual |
| Mod backup (zip) | ✅ | ❌ | ❌ | ❌ |
| In-game companion (`mb_*` cheats) | ✅ (never run in a live game) | ❌ | ❌ | ❌ |
| Export: JSON / CSV / **self-contained HTML report** | ✅ / ✅ / ✅ | ✅ / ✅ / ✅ / txt | ❌ | ✅ |
| Desktop GUI | ✅ PySide6 | CLI (terminal report) | ✅ | ✅ web UI |
| Runs fully offline, no account | ✅ | ✅ | ✅ | varies |
| Own parser, no EA/Maxis code | ✅ | ✅ | ✅ | ✅ |
| License | MIT | MIT (caseone115/simscan) | see repo | see project |

## Where ModBroom is genuinely ahead

1. **The 50/50 bisect actually performs the bisect.** Other tools tell you which files are
   suspects; ModBroom moves half of them out of `Mods`, asks you whether the game still breaks,
   and repeats until one file remains — with an automatic full backup first and a one-click
   restore. This is the single most time-saving part of fixing a broken mod folder and no
   other tool listed does it for you.
2. **In-game companion** — an optional script mod that exposes `mb_status` / `mb_stats` /
   `mb_find` inside the game console so the diagnosis loop is faster. (It has not been run
   inside a live game; see "Honest status" in the README.)
3. **HTML report** that can be pasted into a forum thread when asking for help, generated
   entirely offline.

## Where the others are ahead of ModBroom

1. **Battle-testing.** simscan has been used against thousands of real Mods folders. ModBroom's
   DBPF/RefPack readers are spec-derived and unit-tested but have seen a handful of synthetic
   packages, not a decade of user bug reports.
2. **STBL / DDS / CAS model parsing.** SimsForge-class tools inspect the actual content of
   resources (strings, textures, meshes). ModBroom reads resource headers and hashes, not the
   textures inside them.
3. **Better Exceptions integration.** simscan understands the Better Exceptions log format
   deeply; ModBroom parses the general shape of `LastException` logs and ranks by filename
   match, which is coarser.
4. **Signed/verified publisher metadata** — none of these tools have it, but it is worth
   listing as missing everywhere.

## Honest status

- The Windows `.exe` is built by CI on `windows-latest`. CI verifies the exe exists and is
  non-trivial in size, that every UI module imports cleanly under the offscreen Qt platform, and
  that `--cli-scan` against a generated demo Mods folder reports the expected defect counts. It
  has **not** been run interactively on a real Windows desktop, and it has **not** been run
  against a real Sims 4 install anywhere.
- The companion mod is API-conformant but has never been executed inside the game.
- RefPack decompression is validated by round-trip tests against an independent encoder
  written for this test-suite, plus spec-derived vectors. It has not been fuzzed against a
  corpus of real game packages.
- Conflict "winner" prediction follows the documented priority/depth/name rules; the game's
  actual behaviour can vary by patch, and ModBroom says so in the UI.
