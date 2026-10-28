#!/usr/bin/env python3
"""Write the pointed strings of 1ST.BIN and 2ND.BIN into translation/ (English already there is kept).

  dumptext.py [--force]

  translation/script/interviews.txt   Victory Road interviews and narration: one block per speech
                                      (「 to 」) or narration run; each EN line is one string on screen
  translation/text/menus.txt          the other 2ND.BIN strings, one block per string, grouped by the
                                      pointer table or the code that uses them
  translation/text/messages.txt       the pointed strings of 1ST.BIN (save and backup messages)

Re-running keeps the English and hand-added `#` comments (tools/blocks.py merge).
Block ids are the string addresses (`2ND:0609A6E4`); in interviews.txt the `@` line lists every
line's address. Strings the build handles itself (KEYBOARD) are left out. Run tools/lint.py after.
"""
import argparse
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blocks  # noqa: E402
import fpstext as ft  # noqa: E402
import paths  # noqa: E402

STORY_TABLES = [0x060C1190, 0x060C128C, 0x060C1324, 0x060C188C, 0x060C18B0, 0x060C83F8, 0x060C840C, 0x060C86CC]
STORY_WIDTH = 236          # px: the widest original line (provisional - check the box in game)
KEYBOARD = [0x060C3EA0, 0x060C3F00]   # name-entry character grids: the build writes an English keyboard

HEAD_STORY = '''# Victory Road: the interviews before each match and the narration.
# One block per speech; each EN line is one line on screen (one string in the game).
# limit lines: as many EN lines as JP lines (fewer is fine - the rest stay empty), never more.
# limit px=204: each line at most 204 pixels wide - the in-ring interview box shows lines from
#   x=89 to its edge at x=293, the speaker's name in the margin (seen in the emulator 2026-10-27;
#   python3 tools/fpstext.py width "text" measures). lint.py checks both.
# Speakers are wrestlers: keep each one's voice. Names in the text: see translation/glossary.csv.
# Control codes: none here. Quotes 「」 become "" (open on the first line, close on the last).
'''
HEAD_MENUS = '''# Menus, options, help lines, match and mode text of 2ND.BIN - one block per string.
# Each block is one string; {n} is a new line inside it, {t} a tab. Other codes stay exactly as
# they are: {s3} colour, {p8,32,} position, {x1,}/{y7,} move, {r12,} line height, {b}, {w..}/{c..}
# boxes, {$hh} a raw byte (see the header of tools/fpstext.py).
# px= in a block's comment is the original width in pixels - a guide (menus may have more room);
#   keep labels short where the original is short. Strings are relocated: no byte limit.
# Half-width katakana (ｼﾝｸﾞﾙ) is the same text as full-width - just compressed.
'''
HEAD_MESSAGES = '''# Messages of 1ST.BIN (the resident program): backup memory / save warnings and others.
# Same notation as text/menus.txt. Strings are relocated: no byte limit.
'''


# Comment lines this dump writes and may write differently next time: re-dumps replace them; every
# other `#` line in the files is a hand note and is kept (blocks.merge).
GENERATED = re.compile(r'# (table [0-9A-F]{8}|code near [0-9A-F]{8}|px=\d+ \(original width\)|\(also here, )')


def write_blocks(path, header, items):
    """items: [(id, meta, [source lines], [comments])] - merged into the file: English and hand
    comments stay (tools/blocks.py merge)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    st = blocks.merge(path, header.rstrip('\n').split('\n'),
                      [(i, m, src, [f'# {n}' for n in notes]) for i, m, src, notes in items], GENERATED)
    print(f'{paths.show(path)}: {len(items)} blocks ({st["new"]} new, {len(st["orphans"])} no longer dumped)')


def story_items(pt):
    """Speeches of the story tables; a line already in an earlier block is shown as a comment only."""
    tabs = {}
    for o, v in pt.tables():        # each story table: the pointer run that contains its address
        for t in STORY_TABLES:
            if pt.base + o <= t < pt.base + o + 4 * len(v):
                tabs[t] = v
    out, done, prev_table = [], set(), None
    for t in STORY_TABLES:
        groups, cur = [], []
        for a in (a for a in tabs[t] if a):
            text = pt.text(a)
            if not cur or text.startswith('「') or cur[-1][1].endswith('」'):
                if cur:
                    groups.append(cur)
                cur = []
            cur.append((a, text))
        if cur:
            groups.append(cur)
        for grp in groups:
            new = [(a, s) for a, s in grp if a not in done]
            if not new:
                continue
            notes = [f'table {t:08X}'] if t != prev_table else []
            prev_table = t
            notes += [f'(also here, translated in an earlier block: {s})' for a, s in grp if a in done]
            done.update(a for a, _ in new)
            out.append((f'2ND:{new[0][0]:08X}', 'lines=' + ','.join(f'{a:08X}' for a, _ in new),
                        [s for _, s in new], notes))
    return out, done


def menu_items(pt, skip):
    tabs = {}
    for o, v in pt.tables():
        for k, a in enumerate(v):
            if a:
                tabs.setdefault(a, (pt.base + o, k))
    out, last = [], None
    for a in pt.strings:
        if a in skip:
            continue
        refs = pt.refs[a]
        where = tabs.get(a)
        group = f'table {where[0]:08X}' if where else f'code near {pt.base + refs[0]:08X}'
        notes = [group] if group != last else []
        last = group
        text = pt.text(a)
        px = max(ft.line_widths(text, english=False))
        out.append((f'{pt.name[:3]}:{a:08X}', '', [text], notes + [f'px={px} (original width)']))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], epilog=paths.FOLDER_HELP,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    args = ap.parse_args(paths.configure(sys.argv[1:] if argv is None else argv))  # noqa: F841
    p2 = ft.Pointed('2ND.BIN')
    story, done = story_items(p2)
    kb = set()
    for t in KEYBOARD:                  # read each keyboard table from its address to its end
        o = t - p2.base
        while struct.unpack_from('>I', p2.data, o)[0] in p2.strings:
            kb.add(struct.unpack_from('>I', p2.data, o)[0])
            o += 4
    f = paths.SCRIPT / 'interviews.txt'
    write_blocks(f, HEAD_STORY, story)
    f = paths.TEXT / 'menus.txt'
    write_blocks(f, HEAD_MENUS, menu_items(p2, done | kb))
    f = paths.TEXT / 'messages.txt'
    write_blocks(f, HEAD_MESSAGES, menu_items(ft.Pointed('1ST.BIN'), set()))


if __name__ == '__main__':
    main()
