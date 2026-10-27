# Platform notes: Sega Saturn

Starting notes for Saturn projects. The first project is Fire Pro Wrestling S - 6Men Scramble
(T-4308G). Facts are marked **verified** once they have been checked on a real disc or in game. The
rest is general knowledge still to be confirmed. Add what you learn here and in the kit's copy.

## Disc
- **Verified:** Redump images are BIN/CUE with one file per track. Track 1 is the data track
  (MODE1/2352) and the other tracks are CD audio. The project works on Track 1 (`paths.ROM`) and
  never changes the audio. `build.py` copies the audio tracks next to each build and writes a .cue
  (`disc.companion_files`). Release patches apply to Track 1 alone, and the release README says to
  keep the other tracks and the .cue.
- **Verified:** MODE1 sectors have no subheader. The 2048 data bytes start at offset 16, the EDC
  covers bytes 0-2063 with the header included, and P/Q ECC follow. `tools/disc.py` regenerates
  both on every write. `disc.py verify` recomputes every sector.
- **Verified:** sectors 0-15 hold IP.BIN, which carries the system ID (`SEGA SEGASATURN`), the
  product number, version, date, area codes, title and boot code. The BIOS checks it, so never
  write it. `disc.py header <bin>` prints it, including the load address of the first program
  (+0xF0, usually 0x06004000).
- **Verified:** the PVD's volume size counts the whole disc, audio included, so it is larger than
  Track 1. Sizes come from the BIN file.
- `ABS.TXT`, `BIB.TXT` and `CPY.TXT` are the ISO abstract, bibliography and copyright files. Leave
  them alone.
- The BIOS boots the first file in the root directory (here `1ST.BIN`) at the IP.BIN load address.
  Games then usually find files by name through the SBL/SGL file system (GFS). Some games keep the
  directory index or LBAs of files in their own tables. Check before relocating a file that
  outgrows its slot. Discs are often packed with no free sectors, and the last file runs to the
  end of the track.
- Big `.STR`/`.CPK` files are usually streamed movies or audio read by LBA ranges. Never move them.

## Code
- CPU: two Hitachi SH-2 (SH7604) at 28.6 MHz, master and slave, both big-endian. The master runs
  the game and the slave gets jobs from it. Instructions are 16 bits. 32-bit constants and
  addresses come from **literal pools** after the code (`mov.l @(disp,PC),Rn`), so a reference
  search finds the pool word, not an instruction (`tools/sh2.py refs`).
- **Delay slots**: BRA, BSR, BRAF, BSRF, JMP, JSR, RTS, RTE, BT/S and BF/S run the next instruction
  before the branch. Plain BT and BF have no delay slot. Loads have no delay slot. A branch may not
  sit in a delay slot.
- Memory map (cached addresses; add 0x20000000 for the cache-through mirror):
  - Work RAM High (1 MB): 0x06000000-0x060FFFFF. Main program, data and stack.
  - Work RAM Low (1 MB): 0x00200000-0x002FFFFF. Often overlays and buffers.
  - VDP1 VRAM (512 KB): 0x25C00000. Framebuffer: 0x25C80000.
  - VDP2 VRAM (512 KB): 0x25E00000. VDP2 colour RAM: 0x25F00000.
  - Sound RAM (512 KB, for the 68000): 0x25A00000.
- The main program is raw code (no header) loaded at the IP.BIN address. Other `.BIN` files are
  often overlays loaded at fixed addresses. Find each one's load address from the loader's call.
- Debugging: Mednafen (Beetle Saturn) is the accuracy reference and has a built-in debugger. Check
  which emulator offers a GDB stub before writing a client. Kronos and Yabause/YabaSanshiro have
  debug builds. All of them need a Saturn BIOS image.

## Text
- There is no kanji ROM a game can use, so the font is on the disc. It is usually 1bpp or 4bpp
  bitmaps (16x16, or 12x12 for kanji), indexed by Shift-JIS or by the game's own table.
  `tools/sjisscan.py` finds SJIS strings and `tools/fontid.py` identifies glyph sheets.
- Text is drawn either as VDP1 sprites (often one sprite per character or per line, written to
  VRAM at run time) or into VDP2 tile maps. Find out which early: it decides how much room a
  variable-width font gets.
- Backup RAM saves have an 11-character ASCII file name and a 10-byte comment shown by the BIOS
  memory manager (still to be checked on this game).

## Images
- VDP1 sprites: 4bpp with a colour bank or a lookup table, 8bpp, or 16-bit RGB. In 16-bit RGB,
  bit 15 is MSB/"RGB on" and 0x0000 is transparent. VDP2 cells are 8x8 at 4bpp or 8bpp, with
  palettes in colour RAM. Colours are 15-bit: bits 0-4 red, 5-9 green, 10-14 blue.
- Games commonly pack graphics in their own archives, often compressed (RLE/LZ variants, including
  Sega's CMPRS library). Expect `extract.py unpack()` to do real work.

## Screenshots
- Native resolution is usually 320x224 (NTSC), sometimes 352x224/240, and 640/704x448 for
  interlaced hi-res screens. Record the size each project uses in `<kit>/release/shots.py` SIZES
  and here.
