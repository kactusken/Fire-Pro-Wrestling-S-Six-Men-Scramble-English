# Fire Pro Wrestling S - 6Men Scramble — English Translation

An English translation patch for **Fire Pro Wrestling S - 6Men Scramble** (Human, 1996, Sega
Saturn, released only in Japan).

Everything a player reads is in English: every menu and mode, the 160-wrestler roster (names,
nicknames, profiles) in two versions - the real wrestlers' names or the game's own parody names -
about 600 move names, Wrestler Edit, the Victory Road story with all of its pre-match interviews
(about 1,600 lines), the endings, Title Match mode, and the result banners drawn as pictures. The
game draws every letter as its own 16x16 sprite and allows only 46 per line of text, which English
quickly runs out of; the patch adds 184 two-letter characters (common letter pairs drawn as one
sprite) so the English fits without shrinking the font.

> ### 📖 [Read the player's guide](https://kactusken.github.io/Fire-Pro-Wrestling-S-Six-Men-Scramble-English/guide/)
> A complete English guide to the game, written alongside the translation: every mode, the full
> controls, how matches really work (stamina, criticals, reversals, fighting styles), Wrestler Edit
> step by step, **all 160 wrestlers with their complete move lists** (searchable, with a switch for
> real or parody names), the hidden wrestlers and secrets (spoilers folded), and a Japanese
> glossary for players of the original.

**[See screenshots](docs/SCREENSHOTS.md)** of the patched game.

> **Status: first public beta (v0.1).** All the text is translated and every mode has been
> played or reached in an emulator, including Victory Road title wins and defences, the leagues
> and tournaments, Wrestler Edit and the Unlocked patches. The endings were checked through the
> developers' ending viewer rather than by finishing Victory Road. Please report problems
> ([how to report](#reporting-problems)). [CHANGELOG.md](CHANGELOG.md) lists what's in each
> release.

## Downloads

**[Download v0.1](https://github.com/kactusken/Fire-Pro-Wrestling-S-Six-Men-Scramble-English/releases/download/v0.1/Fire.Pro.Wrestling.S.-.6Men.Scramble.English.Patch.v0.1.zip)** (zip, 0.5 MB), or see all versions on the [Releases](../../releases) page. The zip contains five patches. Pick one:

| Patch | What you get |
|---|---|
| **Fire Pro Wrestling S - 6Men Scramble (English) (Real Names)** | The translation, with the real names of the wrestlers the characters stand for (Tatsumi Fujinami, Stan Hansen...). |
| **Fire Pro Wrestling S - 6Men Scramble (English) (Parody Names)** | The translation, with the game's own parody names (Fighter Yamato, Star Bison...). |
| **... (English) (Real Names) (Unlocked)** | Real names, with everything a full game clear unlocks from the start: all 24 hidden wrestlers (including the Legends promotion), the full Music Test and 255 Wrestler Edit points - plus nine hidden Wrestler Edit presets and the secret "G Gundam Theme" in Wrestler Edit. |
| **... (English) (Parody Names) (Unlocked)** | Parody names with the same unlocks. |
| **Fire Pro Wrestling S - 6Men Scramble (Japan) (Unlocked)** | The original Japanese game, untranslated, with the same unlocks. |

## How to patch

You need your own copy of the original Japanese disc. Disc images are not provided here.

- Game: *Fire Pro Wrestling S - 6Men Scramble* (Japan), serial T-4308G.
- The image must be the two-track BIN/CUE dump whose data track is
  `Fire Prowrestling S - 6Men Scramble (Japan) (2M) (Track 1).bin`, 488802048 bytes, CRC32 `18b025ae`,
  SHA-1 `cd78bd2d77c2de30f640d38663e2111fbf576c2a`. Other dumps (for example the "(1M)" one) won't patch.

Then:

1. Apply the `.xdelta` patch to the Track 1 `.bin` with an xdelta tool:
   - [Rom Patcher JS](https://www.marcrobledo.com/RomPatcher.js/) runs in your web browser.
   - Delta Patcher is a desktop app for Windows, macOS and Linux.
   - On the command line: `xdelta3 -d -s "Fire Prowrestling S - 6Men Scramble (Japan) (2M) (Track 1).bin" "patch.xdelta" "patched.bin"`
2. The patch changes only the data track. Keep Track 2 and the `.cue` as they are, or use the
   `.cue` from the zip; if you give the patched file another name, change its `FILE` line in the
   `.cue` to match.
3. Open the `.cue` in your emulator. Tested in Ymir (and in Mednafen's Saturn core); a Saturn
   BIOS is needed.

## Notes for players

- **Names.** Given name first. The real-names patch uses the names established by the English
  patches of the series' other games (Fire Pro G, Iron Slam '96); the parody patch romanizes the
  game's own names. The hidden promotion HIDE is "Legends" with real names.
- **What's still in Japanese.** The names in the staff credits (kept as they are), text that is
  part of the scenery (signs, the ring apron),
  and the kana rows of the name-entry keyboard (its English letter rows work; its kanji were
  removed to make room for the English lettering). Voices and
  music are unchanged.
- **Saves.** The patch doesn't change the save format; the save files are listed as "FPS6M DATA"
  and "FPS6M EDIT". Loading saves from the Japanese game has not been tested.
- **Unlocking.** Without an "(Unlocked)" patch, the 24 hidden wrestlers appear once both Victory Road
  singles titles are won, or one by one as you beat them; Title Match mode appears once you hold a
  Victory Road title.
- **Guide.** Stuck, or new to Fire Pro? The [player's guide](https://kactusken.github.io/Fire-Pro-Wrestling-S-Six-Men-Scramble-English/guide/) covers everything from the
  controls to every wrestler's moves, with the patch's names.
- **Hidden content.** The developers' debug menu (a build option, not in the patches), unused
  developer tools, cut moves and more: see
  [docs/HIDDEN_CONTENT.md](docs/HIDDEN_CONTENT.md).

## Known issues

- Loading saves made with the Japanese game has not been tested.
- Some short names are cut to fit the Wrestler Select grid (e.g. "Fujinam", "Hashim"), as the
  game's own name fields require.

## Reporting problems

Open an [issue](../../issues) with:

- a screenshot,
- which patch you used,
- where you were: the mode and menu, or roughly what had just happened.

Text that is cut off, overlaps, or still shows Japanese is especially helpful.

## For ROM hackers and contributors

Everything needed to rebuild the patches from the original disc is in this repository: the
translated text, the patching code (Python 3, no dependencies for the build) and documentation of
the game's formats.

| Document | What's in it |
|---|---|
| [docs/BUILDING.md](docs/BUILDING.md) | Setting up, building, making patches, and the checking tools |
| [docs/TRANSLATION.md](docs/TRANSLATION.md) | Text file formats, scope, style guide, glossary, and naming decisions |
| [docs/EDITING.md](docs/EDITING.md) | Editing the in-game text graphics |
| [docs/PATCHES.md](docs/PATCHES.md) | How each code patch works |
| [docs/TECHNICAL.md](docs/TECHNICAL.md) | The game's disc layout, archives, compression, data formats, and memory map |
| [docs/PLATFORM.md](docs/PLATFORM.md) | SATURN pitfalls for this kind of work |
| [docs/HIDDEN_CONTENT.md](docs/HIDDEN_CONTENT.md) | Unlockables, debug features, and unused and cut content |
| [docs/guide/](docs/guide/index.html) | The player's guide (one page; roster data from `tools/guidedata.py`) |
| [tools/README.md](tools/README.md) | Every tool, what it's for and how to run it |

Quick start:

```sh
python3 tools/extract.py                 # unpack the disc in rom/ into extracted/
python3 build.py --names real            # -> build/Fire Pro Wrestling S - 6Men Scramble (English).bin
python3 make_patches.py --version v0.1   # -> release/*.xdelta and a zip (needs xdelta3)
```

## AI disclosure

AI assisted with the translation.

## Legal

This is a non-commercial fan translation, not affiliated with or endorsed by the game's developers
or publishers. It contains no copyrighted game data that would let
anyone play without owning the game. The patches only work on your own copy of the disc.
Fire Pro Wrestling S - 6Men Scramble and its contents belong to their respective owners. The Japanese text in this
repository is included for translation and reference.

The code in this repository is released under the [MIT License](LICENSE).
