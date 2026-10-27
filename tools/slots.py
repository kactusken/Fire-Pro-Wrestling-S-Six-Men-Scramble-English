#!/usr/bin/env python3
"""Text slots in a savestate: which text areas overflow into the next one (the play-test check).

  slots.py check <state> [<state> ...]     every active text slot, its room and use; overflows marked
  slots.py play <cue> <steps...> [--out NAME]   boot from a savestate or the disc, press, then check

The game draws text as one 16x16 VDP1 cell per glyph (128 bytes, 16 units of VDP1 address) into
slots: a table of 80 records of 0xDE bytes at 0x06070BB0 (1ST.BIN 0x06021314 / 0x0602149C). A
slot keeps its VRAM address (+22), one (x, y) pair per glyph from +30 (ended by FFFF) and its end
address. A screen reserves its slots once - often for the Japanese length - and redraws text into
them; text with more glyphs than the room runs into the next slot (letters of the neighbouring
text appear, or the neighbour's glyphs are replaced). Room = the distance to the next slot's
address. Spaces take no glyph.

Steps for `play`: A B C X Y Z L R START UP DOWN LEFT RIGHT (pressed), wN (wait N frames),
@FILE (load a savestate first, must be the first step). Writes build/work/emu/<out>.png/.state.
Needs platforms/saturn/emu.py of the kit ($KIT, default: Translation-Kit next to the project folder;
the Beetle Saturn core and the BIOS: `emu.py setup`).
"""
import argparse
import os
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402

KIT = Path(os.environ.get('KIT', Path(__file__).resolve().parents[2] / 'Translation-Kit'))
KIT_SATURN = KIT / 'platforms' / 'saturn'          # emu.py: the headless emulator (kit)
SLOTS, SLOT_SIZE, SLOT_COUNT = 0x06070BB0, 0xDE, 80
GLYPH_UNITS = 16                        # 128 bytes per glyph cell, VRAM addresses in 8-byte units


def _emu():
    sys.path.insert(0, str(KIT_SATURN))
    import emu
    return emu


def slots(hwram):
    """[(index, start, glyphs, end)] of the slots in use."""
    def w(a):
        return struct.unpack_from('>H', hwram, a - 0x06000000)[0]
    out = []
    for i in range(SLOT_COUNT):
        b = SLOTS + i * SLOT_SIZE
        start = w(b + 22)
        if start == 0xFFFF or w(b + 2) == 0xFFFF:
            continue
        n, a = 0, b + 30
        while a < b + SLOT_SIZE - 4 and w(a) != 0xFFFF:
            n, a = n + 1, a + 4
        if a >= b + SLOT_SIZE - 4:
            continue
        out.append((i, start, n, w(a + 4)))
    return out


def check(hwram, name=''):
    """Print the slots; returns the overflows [(slot, glyphs, room)]."""
    ss = sorted((s for s in slots(hwram) if s[2]), key=lambda s: s[1])
    starts = sorted({s[1] for s in slots(hwram)})
    bad = []
    for i, start, n, end in ss:
        nxt = next((a for a in starts if a > start), None)
        room = (nxt - start) // GLYPH_UNITS if nxt is not None else None
        over = room is not None and n > room
        if over:
            bad.append((i, n, room))
        print(f'{name} slot {i:2} at {start:04X}: {n:3} glyphs, room {room if room is not None else "-":>3}'
              + ('   <-- OVERFLOW' if over else ''))
    return bad


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], epilog=paths.FOLDER_HELP,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('check')
    p.add_argument('states', nargs='+')
    p = sub.add_parser('play')
    p.add_argument('cue')
    p.add_argument('steps', nargs='*')
    p.add_argument('--out', default='play')
    a = ap.parse_args(paths.configure(sys.argv[1:] if argv is None else argv))
    emu = _emu()
    if a.cmd == 'check':
        bad = 0
        for s in a.states:
            bad += len(check(emu.state_memory(Path(s).read_bytes(), 'hwram'), Path(s).stem))
        return 1 if bad else 0
    e = emu.Saturn(a.cue)
    for s in a.steps:
        if s.startswith('@'):
            e.load_state(Path(s[1:]).read_bytes())
        elif s[0] == 'w' and s[1:].isdigit():
            e.run(int(s[1:]))
        else:
            e.press(s, 6, 20)
    e.run(30)
    out = paths.WORK / 'emu' / a.out
    out.parent.mkdir(parents=True, exist_ok=True)
    e.screenshot(f'{out}.png')
    st = e.save_state()
    Path(f'{out}.state').write_bytes(st)
    print(f'{paths.show(Path(f"{out}.png"))}')
    return 1 if check(emu.state_memory(st, 'hwram'), a.out) else 0


if __name__ == '__main__':
    sys.exit(main())
