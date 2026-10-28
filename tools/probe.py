#!/usr/bin/env python3
"""The game's text areas on screen right now and the room each one has - what the kit's headless
runner (testing/drive.py) checks on every screen it visits.

  python3 <kit>/testing/drive.py run [--image IMG] STEP... check NAME     one screen
  python3 <kit>/testing/drive.py sweep [--image IMG]                      every private/work/sweep/*.steps

Fire Pro Wrestling S draws text as text slots (tools/slots.py): one 16x16 VDP1 cell per glyph in
the slot's own area of VDP1 memory; room = the distance to the next slot's area. Areas are named
by slot number and VDP1 address, so the same screen gives the same names in every run.
"""
import slots

REGIONS = ['hwram']


def areas(mem):
    h = mem['hwram']
    used = slots.slots(h)
    starts = sorted({s[1] for s in used})
    out = []
    for i, start, n, end in sorted((s for s in used if s[2]), key=lambda s: s[1]):
        nxt = next((a for a in starts if a > start), None)
        out.append({'area': f'slot {i} @{start:04X}', 'used': n,
                    'room': (nxt - start) // slots.GLYPH_UNITS if nxt is not None else None})
    return out
