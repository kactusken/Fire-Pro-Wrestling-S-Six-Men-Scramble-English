# Tools

Everything is Python 3 and runs from the project folder or anywhere else; every tool has `--help`
(or prints its usage). Folder locations come from [paths.py](paths.py) and can be moved with the
folder options. `build.py`, `make_patches.py` and everything they import use only the standard
library; the tools marked *Pillow* or *capstone* need `.venv` (`pip install -r requirements.txt`).

Set up from the translation kit (version b9807f6-dirty). Tools marked *game* are stubs to fill in.

## Used by the build

| Tool | What it does |
|---|---|
| [../build.py](../build.py) | builds the translated image (text steps, code patches, images, write-back) |
| [paths.py](paths.py) | every folder location and the folder options |
| [image.py](image.py) | the output image: fresh copy or fast restore from a journal; checksums |
| [disc.py](disc.py) | reads and writes files in the image (SATURN; a cartridge ROM is one file - docs/PLATFORM.md) |
| [codepatch.py](codepatch.py) | applies code patch tables, checking the original bytes first |
| [catalog.py](catalog.py) | the image catalogue: which file the build uses, fingerprints, stale renders |
| [gfx.py](gfx.py) | *game*: exports the original images, imports the English ones |
| [pngio.py](pngio.py) | PNG reading and indexed PNG writing without dependencies |
| [blocks.py](blocks.py), [textdb.py](textdb.py) | message block files; every translatable string as one list |
| [fpstext.py](fpstext.py) | the game's text: codec ({codes}), single-byte English letters, pixel widths, the tightened Latin font, pointed strings of 1ST/2ND.BIN |
| [textins.py](textins.py) | build text steps: font, letters, strings packed + repointed (self-checked), name records, move pool; `report` shows the space |
| [names.py](names.py) | `<name>` tokens: real or parody names per build; writes the glossary's name rows |
| [sh2.py](sh2.py) | `asm`: a small SH-2 assembler for hooks (labels, .long/.word, `mov.l =x` literal pools; refuses branches and PC-relative loads in delay slots) |

## Checking

| Tool | What it does |
|---|---|
| [check.py](check.py) | runs every check (`--quick` for the pre-commit hook, `--control` for a lossless-build proof) |
| [textrender.py](textrender.py) | draws strings like the game (font, widths, codes) to a PNG: previews and layout checks |
| [lint.py](lint.py) | text: leftover source text, control codes, line/char/byte limits, glossary |
| [status.py](status.py) | how far along the text and images are |
| [records.py](records.py) | fixed-record text tables (names, items, menus of records): `dump` the CSV, `verify` the layout, `measure` unknown data, build step - configure `TABLES` |
| [stepcheck.py](stepcheck.py) | run one build text step against `extracted/` (no image, nothing written) and list what it changed - for testing a step while the image is busy |

## Translating

| Tool | What it does |
|---|---|
| [dumptext.py](dumptext.py) | pointed strings of 1ST/2ND.BIN -> script/interviews.txt, text/menus.txt, text/messages.txt (keeps English) |
| [dumprecords.py](dumprecords.py) | roster, promotions, move names -> text/*.csv (keeps English; --suggest a Fire Pro G project) |
| [fill_text.py](fill_text.py) | fills repeated strings from a source → English table |
| [render.py](render.py) | *Pillow*: automatic English renders, only redrawing what changed |
| [edit.py](edit.py) | *Pillow*: hand-edit workflow - start, check, approve, reset, sheets |
| [letter.py](letter.py) | *Pillow*: letters English into pictures `render.py` can't do (tinted or gradient lettering) from specs in `translation/letters/`, keeping the original palette; fonts in `fonts/` |
| [compare.py](compare.py) | *Pillow*: original \| English sheets |
| [contact.py](contact.py) | *Pillow*: every original image on labelled sheets |

## Releasing

| Tool | What it does |
|---|---|
| [../make_patches.py](../make_patches.py) | builds every variant, makes and re-verifies the patches, README.txt and the zip |

## Research

| Tool | What it does |
|---|---|
| [extract.py](extract.py) | unpacks the disc into `extracted/` and exports the images (*game*: `unpack()`) |
| [sjisscan.py](sjisscan.py) | finds Shift-JIS text in binary files |
| [fontid.py](fontid.py) | *Pillow, numpy*: guesses a font's characters from a PNG sheet of its glyphs (per glyph, or the best JIS-ordered assignment) - a start for the table |
| [parts.py](parts.py) | bulk translation: `split` the untranslated text into part files for parallel translators, `check` a part (lint against the real limits), `status`, `merge` back (duplicates filled, blocks with errors skipped) |
| [pagedata.py](pagedata.py) | fills the JSON data block of a reference page in `docs/` (`--check`); a game's data tool calls `pagedata.write()` |
| [sh2.py](sh2.py) | `dis`/`refs`/`calls`: SH-2 disassembler (raw binary at 0x06004000) with pool constants inline, delay slots marked, literal-pool reference and jsr/bsr call search |

## Added for this game
- `pairs.py` - two-letter glyphs: choose the pairs (`choose --write` -> translation/text/pairs.txt),
  the font bitmaps; the encoder uses them automatically (docs/TECHNICAL.md).
- `slots.py` - text slots in an emulator savestate: room and use, overflows; `play` drives the
  emulator (the kit's platforms/saturn/emu.py) to a screen first.
- `gfx.py` - FPS.SBL resource 10 sprites (graphics.csv `FPS.SBL#10`): export and import.
- `textins.py` - also LAYOUT_PATCHES (data the English layout needs), fields.csv, save titles,
  the keyboard and the pair hook.
