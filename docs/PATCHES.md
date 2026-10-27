# Patches

What the build changes besides text and images, one section per patch: what the original code
does, what changed, why it works, the tool that makes it, limits to respect, and whether it was
*verified in game*.

## Text system (every English build)
*From the code; not yet seen in game.*
- **Single-byte letters.** The two half-width katakana tables in `1ST.BIN` (0x0604F990 for the
  name renderer 0x0601F478, 0x0604FA48 for the main renderer 0x06020C48 and the converter in
  2ND.BIN) are rewritten: bytes A6-DD now stand for a-z, A-Z, `. , ' -` and are drawn with the
  font's full-width Latin glyphs. No code changes. (`tools/textins.py letters`)
- **Tightened Latin font.** In the font (`FPS.SBL` resource 68) the Latin and punctuation glyphs
  are moved flush left, and their advances in the width table (0x0603B098) set to ink width + 1:
  `.` and `,` 3 px instead of 8, capitals 8-11 instead of 10-12. Digits keep 8 px (number columns).
- **Repointed strings.** Every pointed string of `1ST.BIN` and `2ND.BIN` is written into the
  freed string areas of its file (byte-aligned) and every pointer to it is rewritten; the build
  then follows every pointer again and stops if one doesn't lead to its text.
- **Records and move names** are written in place (fixed fields; the move pool deduplicated and
  its u16 offset table rewritten).

## Unlocked (`--unlocks unlock`, the "(Unlocked)" patches)
Everything a full game clear unlocks, from the start, plus hidden Wrestler Edit options
(docs/HIDDEN_CONTENT.md). In the English and the untranslated Japanese patches.
- **Game-clear flag treated as set** - the flag (save byte 0x00212B49, RAM copy 0x060682E8; set
  when both Victory Road singles titles have champions) is tested in seven places; each load of
  it (`mov.b @rN,r1`) becomes `mov #1,r1` (`E101`): 1ST.BIN 0x0601C09E (hidden roster wrestlers,
  roster order 136-159), 0x0601B82C (their wrestler groups); 2ND.BIN 0x0608E430 (Music Test range
  2-36 instead of 5-34), 0x06081F18 and 0x06082494 (One Night Match: more players than pads),
  0x0608F02A and 0x0608F60C (Edit point pool 200). The save is never changed. *Verified in game*
  2026-10-27 (14 promotions with Legends); Music Test range and points *seen headless*.
- **Full Edit points** - 2ND.BIN 0x0608F058 `8902` and 0x0608F63E `A086` -> `0009`: the pool is
  255 only with all five title records (checked on entering Edit, 0x0608F028, and on reload,
  0x0608F602); the skip after each check becomes a no-op, so it is always 255. *Seen headless*
  ("0 / 255", English and Japanese).
- **Hidden Edit presets** - 2ND.BIN 0x060B2C2C `6220` (`mov.b @r2,r2`, the list end 204 read from
  0x060C4E0A) -> `E2D5` (`mov #213,r2`): Wrestler Edit's Appearance Face list runs to 212, the
  last preset the tables hold (32bits used 232; 213-231 read other data as colours). *Verified in
  game* 2026-10-27.
- **G Gundam theme in Wrestler Edit** - 2ND.BIN 0x060BF900 `0022` -> `0025`: the Theme field's
  maximum (u16 min/max at 0x060BF8FE) goes from 34 to 37, the secret "G Gundam Theme" (FPS.STR
  streams 40-41). Its name: the theme name table 0x060BE444 ends in an empty string, so the English
  text step adds "G Gundam Theme" for entry 37 (textins NEW_STRINGS); the Japanese patch shows no
  name there, as the original. *Verified in game* 2026-10-27 (heard at an entrance).

## Process Select (`--unlocks debug-menu`, developer only - never released)
*Seen headless* 2026-10-27.
- 1ST.BIN 0x06024E28 `E100` -> `E101`: the boot code stores 1 instead of 0 in the mode value
  0x0605629C, so 2ND.BIN returns at once and 1ST.BIN shows PROCESS SELECT (the Gian editor is
  3RD.BIN). HARAKI_PROCESS leads to the normal Mode Select. Its labels are developer ASCII.

## Match monitor (`--unlocks debug-monitor`, developer only - never released)
*Seen headless* 2026-10-27.
- 1ST.BIN 0x060242B4 (28 bytes of an unused helper) -> a hook: `sts.l pr`, call 0x06016398 (the
  unused monitor), call 0x06027D44 (what the paused-match loop called), `lds.l pr`, `rts`.
- 1ST.BIN 0x0600A430, the paused loop's pool word `06027D44` -> `060242B4` (the hook).
- Pause a match: R steps the eight pages, L the wrestler in focus.
