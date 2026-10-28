# Technical notes - Fire Pro Wrestling S - 6Men Scramble

**Conventions:** numbers in hex with `0x`; addresses are RAM addresses unless marked as file
offsets; `u16`/`u32` big-endian (SH-2) unless marked LE. Findings are marked *verified in game* or
*from the code*.

## Contents
- [Image](#image) · [Disc layout](#disc-layout) · [Executable and memory](#executable-and-memory)
- [Archives and compression](#archives-and-compression) · [Text](#text) · [Images](#images)
- [Open questions](#open-questions)

## Image
`Fire Prowrestling S - 6Men Scramble (Japan) (2M) (Track 1).bin`, 488802048 bytes, SHA-1 `cd78bd2d77c2de30f640d38663e2111fbf576c2a`.

Product number T-4308G, V1.005, mastered 1996-11-25, area J (IP.BIN; `tools/disc.py header`).
Redump-style BIN/CUE with two tracks: Track 1 data (MODE1/2352, 207824 sectors, the image above)
and Track 2 CD audio (`... (Track 2).bin`, 1625232 bytes, CRC32 `fcd26cdc`, SHA-1
`413e93fb3bd1a5730ad8fdce432cae8b8d12316b`), never changed. *Verified:* EDC/ECC of every Track 1
sector is valid. The first program (`1ST.BIN`) loads at 0x06004000 (IP.BIN +0xF0). Matches the
Redump entry "Fire Prowrestling S - 6Men Scramble (Japan) (2M)" (both tracks and the .cue, checked
2026-10-27).

## Prior art
- **English patch v0.91 by Malenko** (SegaXtreme, 2022-01-01, updated 2022-01-05; Sega Saturn
  Patcher format): "Everything is translated except for some of the victory road dialog" (SHIRO!
  lists it as ~50% of the Victory Road story dialogue untranslated); Create-a-Wrestler fully done.
  <https://segaxtreme.net/resources/fire-pro-wrestling-6-men-scramble.106/>. This project is a
  new translation and does not use it.
- **Debug mode and extra characters patch by 32bits** (2024-05-09): debug menu, Wrestler Edit past
  the 204 base characters. Write-up:
  <https://32bits.substack.com/p/expansion-hack-fire-prowrestling>; patch:
  <https://segaxtreme.net/resources/fire-pro-wrestling-s-6men-scramble-debug-mode-extra-characters.321/>.
  Details and leads in [HIDDEN_CONTENT.md](HIDDEN_CONTENT.md).
- Action Replay codes: Almar's Guides
  (<https://almarsguides.com/retro/walkthroughs/Saturn/games/FireProWrestlingS6MenScramble/ActionReplay/>).
- Nothing found on Data Crystal or The Cutting Room Floor.

## Disc layout
| LBA | Size | File | Contents |
|---|---|---|---|
| 21 | 336468 | `/1ST.BIN` |  |
| 186 | 300908 | `/2ND.BIN` |  |
| 333 | 104648 | `/3RD.BIN` |  |
| 385 | 16 | `/ABS.TXT` |  |
| 386 | 21 | `/BIB.TXT` |  |
| 387 | 42 | `/CPY.TXT` |  |
| 388 | 7235584 | `/FPS.SBL` |  |
| 3921 | 3520512 | `/FPS.SND` |  |
| 5640 | 5586944 | `/GCD.BIN` |  |
| 8368 | 17694720 | `/GRD.BIN` |  |
| 17008 | 2174976 | `/GSB.GSF` |  |
| 18070 | 17039360 | `/GSR.GSF` |  |
| 26390 | 2498560 | `/GSS.GSF` |  |
| 27610 | 25556 | `/SDDRVS.TSK` |  |
| 27623 | 12974080 | `/GVB.BIN` |  |
| 33958 | 83034112 | `/GVS.BIN` |  |
| 74502 | 272736256 | `/FPS.STR` |  |

## Executable and memory
*From the code* unless marked.

| File | Loads at | Size | What |
|---|---|---|---|
| `1ST.BIN` | 0x06004000 | 0x52254 | main program, always resident: text renderer, wrestler roster, move names |
| `2ND.BIN` | 0x06080000 | 0x4976C | the game overlay: menus, story (Victory Road), match, edit mode |
| `3RD.BIN` | 0x06080000 | 0x198C8 | the Gian editor (developers' motion editor), loaded instead of 2ND.BIN when the mode value at 0x0605629C is 1; the PROCESS SELECT debug menu itself is in 1ST.BIN (docs/HIDDEN_CONTENT.md) |

- Overlays are loaded by name with 0x06025220 (load) / 0x06025310 and entered at 0x06080000.
- `FPS.SBL` resources are loaded by number: 0x06025388(n) gives a resource's size, 0x060253A0(n,
  dest) loads it. Resource 68 (the font) goes to 0x00200000, 69 to 0x0020DC00, 115 to 0x060D0000,
  116 to 0x060F0000, 114 to 0x00230000 (decompressed?).
- RAM above the overlays: 2ND.BIN's variables reach 0x060CBxxx; 0x060D0000-0x060F1800 and
  0x060DE800/0x060E0000/0x060FA000 are load buffers at different times; stack at 0x060FFC00. No
  region has been proved free yet (needs an emulator memory watch).

## Archives and compression
- `FPS.SBL`: archive, table of (u32 offset, u32 size) big-endian pairs at the start (133 entries,
  sector-aligned data). Graphics (RGB555 palettes, VDP2 maps, cell data, some compressed entries),
  the font (68) and data. No readable text.
- `GCD.BIN`, `FPS.SND`: the same table layout. `GVB.BIN`/`GVS.BIN`: 16-bit PCM sound. `FPS.STR`:
  streams. `GRD.BIN`, `*.GSF`: graphics. None holds readable text (scanned per entry).

## Text
*From the code* (2026-10-26); none of it seen in game yet.

**Where:** all text is Shift-JIS in the three code files (`1ST.BIN` ~16.7 KB, `2ND.BIN` ~63 KB,
`3RD.BIN` mostly ASCII debug labels). The archives hold no text; menus drawn as images are still
to be inventoried.

**Renderer** (`1ST.BIN`): 0x06020C48(string, ctx) draws a string into a 4bpp texture, called by
0x06021314 (VDP1 sprite) and 0x0602149C (print); 0x0601FB48 draws names. The text context at
0x0606A760 (set at 0x06022444 / 0x06016EF4): +0 font (0x00200000), +4 width table (0x0603B098),
+12/14 x/y, +16 left margin, +18, +20 line height, +23 colour/flags, +26 fixed pitch.

Bytes in a string:
| Bytes | Meaning |
|---|---|
| 81-9F, E0-EF + byte | Shift-JIS character; 81 40 (full-width space) only moves the pen (12 px) |
| A6-DD | half-width katakana, turned into full-width through the table at 0x0604FA48 (2 bytes each); a following DE/DF adds the voicing mark |
| 09 | tab (next 32 or 64 px) |
| 0A | new line (x = left margin, y += line height) |
| 20 | space: x += 8 |
| `s`d | colour/flags (one digit, `0`-`?`) |
| `p`n,n, | position x,y (numbers: optional `-`, 1-3 digits, then `,`) |
| `x`n, / `y`n, | move x / y by n |
| `r`n, | line height |
| `e`n, `m`n, | context fields +18 / +24 |
| `b` | x/y from the current box |
| `w`c n,n,n,n, / `c`c n,n,n,n, | box definitions |
| anything else (ASCII 21-7E that isn't a code, A0-A5, DE-DF, F0-FF) | skipped - **ASCII is never drawn** |

**Font:** `FPS.SBL` resource 68 (0xDAB6 bytes), loaded at 0x00200000: u16 table offset, u16 glyph
data offset (both in u16 units), a u16 lookup per glyph number, then 12x16 1bpp glyphs (24 bytes,
row-major, MSB first). 7148 glyph numbers, 1737 stored glyphs; a missing character draws glyph 0
(a crossed box). Glyph number (0x06020930): lead <= 0x87: (lead-0x81)*0xBC + trail' - 0x40;
kanji: row*0xBC + trail' + 0x252 (rows from 0x88 and 0xE0; trail' = trail - 1 above 0x7F). Has
full-width 0-9, A-Z, a-z and the usual punctuation.

**Widths:** proportional for glyph numbers <= 0x2EF from the byte table at 0x0603B098 in
`1ST.BIN` (A-Z 8-12 px, a-z 6-10, 0-9 8), 12 px above; 0x06021D7C measures one character.

**Where strings live:**
- `2ND.BIN`: ~2,660 NUL-terminated strings (61.5 KB), 4-byte aligned, reached through 32-bit
  pointers (pointer tables and literal pools). Story lines are one string each, listed in tables
  (one per scene, in reverse order).
- `1ST.BIN` wrestler roster: 160 records of 0x1AC bytes from 0x0603E680: +0 a group bitmask byte,
  +1 the name flags, +2 name1 = the short name (14 bytes; the family or ring name), +0x10 name2
  (20), +0x24 nickname (24), then stats and move ids. 0x0601BF00(id) finds a record: id & 0xC000
  = 0 the roster, 0x4000 the saved game data (0x0020DC00 + n*0x1F0 + 24, file FPS_6MEN_01),
  0x8000 the edit wrestlers (0x00212E00 + n*0x1F0 + 72, file FPS_6MEN_02). Accessors: 0x0601B0C0
  name1, 0x0601B0DC name2, 0x0601B0F8 nickname, 0x0601B114 the full name into 0x0606EC0C:
  name1 + separator + name2, or name2 first when flags bit 0x80 is set; the separator is flags & 15:
  0 a space (0x20), 1 ・ (81 45), 2 ＝ (81 81), others none. *From the code* (2026-10-26). The
  build sets bit 0x80 and the separator per English name (`tools/textins.py` records).
  Promotions: long names in 26-byte slots from 0x0603E056, short names in 14-byte slots from
  0x0603E1C2.
- Wrestler Edit's 204 "base" characters: 0-159 the roster, 160-203 appearance presets (tables at
  0x060C50C2, 0x060C5ED6, 0x060C60B3, copied by 0x060B26A4) with no names: there is no text on the
  disc for them (searched for the names fans give them, in full- and half-width). *From the code*.
- `1ST.BIN` move names: 0x0601B268(id & 0xFFF) -> table of u16 offsets at 0x06050898 (2,135
  entries, offsets from the table start) into a packed pool from 0x06051947 (~10.6 KB), names mix
  half-width and full-width katakana.
- `1ST.BIN` other: ~100 pointed strings (save/backup messages etc.).
- Backup RAM save comment: `ﾌｧｲﾌﾟﾛﾃﾞｰﾀ` / `ﾌｧｲﾌﾟﾛﾚｽﾗｰ` (half-width, 0x0603DB48 / 0x0603DB74), 10 bytes +
  NUL, inside the save descriptors at 0x0603DB30 / 0x0603DB5C (u32 0/1, u32 RAM address, u32 size,
  file name `FPS_6MEN_01` / `_02`, comment). The English writes plain ASCII capitals there.

**English** (*from the code*, built 2026-10-26, not yet seen in game; docs/PATCHES.md "Text system"):
letters are single bytes A6-DD through the two rewritten half-width tables (0x0604F990,
0x0604FA48); space 0x20 (8 px); digits and other symbols full-width Shift-JIS (`"` and `'`
as the curly 81 67/81 68 and 81 66 - cp932's full-width ＂＇ are IBM extension codes the font
lacks). The Latin glyphs are tightened (font and width table). Pointed strings: found as aligned
32-bit words in a file pointing at a string start (after a NUL, or 4-aligned when code loads the
word or a pointer table holds it); one compiler-shared tail (0x060BFEF0 into 0x060BFEE4) is a
string of its own; the promotion slots 0x0603E03C-0x0603E294 are records, not strings. All
pointed strings of a file are packed into the freed string slots (byte-aligned) and repointed.
English takes less room than the Japanese: 2ND.BIN 56.5 of 71.2 KB, 1ST.BIN 1.5 of 2.2 KB, moves
9.7 of 10.9 KB (`tools/textins.py report`).

**Text slots** (*seen in the emulator*, 2026-10-27, `tools/slots.py`): the renderer draws every
glyph into its own 16x16 4bpp VDP1 cell (128 bytes = 16 units of VDP1 address; 0x06020C48 returns
the glyph count; spaces and codes take none). Text objects are slots: 80 records of 0xDE bytes at
0x06070BB0 - +22 VRAM address, +30 one (x, y) word pair per glyph ended by FFFF, then the end
address. 0x0602149C allocates a slot sized for the text it draws first; 0x06021314 redraws new
text into an existing slot without checking its room, so longer text runs into the next slot.
A slot record holds at most 46 glyphs: the 47th makes the glyph routine call the error
handler 0x06021C54 with code 3 (list pointer reached the record's end, slot+0xDA) and the game
stops (*seen in the emulator*: Wrestler Edit's profile screen). Lint checks every string. The
profile's 32 value slots get their room from the byte table 0x060BFCFC (glyphs per row, added to
the VRAM pointer at 0x060957xx); the build raises the value rows to 8 (textins LAYOUT_PATCHES).
Measured rooms: Mode Select title 15 glyphs, description 30; the Wrestler Select name grid 7
(setup 0x06085304, `add #112` per slot, columns 56 px apart). Measured limits are in
`translation/text/rooms.csv` and checked by lint. Edit appearance: the size code (Ｍ/－) is drawn
where the label string's pen ends; the original labels end with `：{x12,}，{x-20,}` to place it
between the colon and the comma.

**Two-letter glyphs** (*seen in the emulator*, 2026-10-27; tools/pairs.py): 188 common letter
pairs are glyph numbers 564-751 (Shift-JIS 84 40.., Cyrillic and box drawing - nothing the game
shows; proportional, so the width table gives each pair its letters' advances and text looks
exactly as before). Their 16x16 1bpp bitmaps (32 bytes) sit in two 24-byte font slots each, taken
from kanji no remaining text draws (the name-entry keyboard's kanji are blanked). The glyph
routine 0x0602099C calls the unpacker through the literal 0x06020B64; the build points it at a
88-byte hook in 1ST.BIN's freed string space: glyph number (r10) 564-0x2EF -> unpack 16 rows x
16 bits into the 16x16 4bpp cell and store the advanced cell pointer to 0x0607A230 (as the
original 0x06021F60 does - without it the next glyphs overwrite the cell); else jump to the
original. English text needs 67% of the glyphs it needed with single letters.

**Victory Road interviews** (*seen in the emulator*, 2026-10-27): when the configuration
screen's Next is pressed, 2ND 0x060A76E4 picks the interview: the title byte 0x0606076C (0-3; 4,
the 6-man tag title, has none) selects the tables, 0x060A77CC the scene from the match-up (a list
per title at 0x060C39DC; -1 = none); the scene's speeches (0x060C2F40, counts 0x060C2FEC) are
copied to 0x06060910 and a flag (0x1000) set. The match then plays it in the ring before the bell
(1ST 0x06005CD0 / 0x06005E10, drawn by the second renderer): a box with the speaker's short name
in the left margin and two lines of text from x=89 to the box edge at x=293 - 204 px per line.
Scenes per title: 29, 19, 16, 13. Forcing 0x060A77CC to return N (RAM patch) plays any scene on
the first match (private/work/late/interviews.py).

**Endings** (*seen in the emulator*, 2026-10-27): the debug menu's KANEKO_PROCESS (Extras build)
is an ending selector - UP/DOWN pick Heavy Ending, Junior Ending, Staff Roll, Staff Roll Test;
A plays it (private/work/late/endings.py records one). Both endings copy the text context
template 0x060C7D1C to 0x060CADF0 and set a fixed pitch of 18 px per glyph (+26; heavy 2ND
0x060B72A4, junior 0x060B8520); 0x0602099C then advances every glyph by the pitch instead of its
width, so two-letter glyphs and single letters got the same 18 px ("t he lo ng"). The build sets
both to 0 (textins LAYOUT_PATCHES): proportional, as everywhere else. The staff roll draws
otherwise and is unchanged (frames identical before and after). Text: heavy - block 060B7118
(tables 0x060C83F8 / 0x060C840C / 0x060C8418, y positions 0x060B7130 / 0x060B7180 /
0x060B71B4); junior - block 060B8408 (table 0x060C86CC). The staff roll's role titles are English
in the original; the names stay Japanese (owner 2026-10-27).

**YES/NO prompts** (*seen in the emulator*, 2026-10-27): the question boxes ending in ＹＥＳ／ＮＯ
place their cursor boxes where the Japanese words were, at a fixed distance from the end of the
text (the text is centred), not from the English letters. The English is laid out as wide as the
Japanese (the `px` comment + 27 px, as drawn) with `YES/{x3,}NO{x10,}` in its last 66 px:
`Question?{xN,}YES/{x3,}NO{x10,}`, N = px + 27 - width(question) - 66. Checked on Vacate the belt
and End wrestler entry; "Start match? YES/NO/EXIT" (three choices) is not done yet.

**Title Match mode** (*seen in the emulator*, 2026-10-27): Mode Select offers it as a 12th mode
when any of the five title records (low work RAM 0x0021231C + 158 x title; first word = number of
champions, then 26-byte champion entries) is non-zero (2ND 0x0608E82E). Its Title Match item is
enabled by the held-belt table 0x002122CC + 16 x title (byte 0 flag, bit 0x80 checked at
0x060959F2; +10/+12/+14 wrestler ids, FFFF = none). private/work/late/titlematch.py fakes both.

**Name entry:** the keyboard tables 0x060C3EA0 (23 rows of 15) and 0x060C3F00 (kanji by reading)
already hold full-width A-Z / a-z rows; typed names are stored as 2-byte characters. Default names
come from strings such as the mode names, which the original writes in full-width letters: the
English keeps them full-width (1-byte letters there broke deleting and typing). The kanji keyboard
lists almost every glyph of the font (1,422 kanji).

**Custom glyphs:** the font's … cell (81 63) holds 綾 (staff credit 綾野 一郎).

## Images
- 13 `FPS.SBL` screens (entries 14-61: 8bpp cells, 64x28 map of 32-bit entries, RGB555
  palette): interview and ending art, no text.
- `FPS.SBL` resource 10 (0x27AE0 bytes) is a bank of VDP1 sprites copied as-is to VDP1 VRAM
  0x48000: raw 4bpp (colour bank) or other modes, no headers - a sprite is just an offset and
  size the code passes to VDP1 (no table of them found: the offsets are computed). Found by
  reading the VDP1 command list in emulator savestates (`tools/sprites.py`), which
  also gives each sprite's palette from VDP2 colour RAM. Wrestler Select's info-panel labels
  (ニックネーム 出身地 必殺技 身長 生年月日 体重) are 40x16 4bpp sprites at +0x0000..+0x0640
  (palette bank 0x70: index 1 white, 15 black, 2-11 the gold plate). *Seen in the emulator*
  2026-10-27. Images are `r10_<offset>` in graphics.csv; tools/gfx.py exports and imports them.
- Still to inventory: the rest of resource 10 (found screen by screen), the compressed entries
  (3, 13, 114, ...), VDP2 screens, GCD.BIN, GRD.BIN.

## Open questions
-
