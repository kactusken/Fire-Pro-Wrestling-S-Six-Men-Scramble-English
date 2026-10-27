#!/usr/bin/env python3
"""Two-letter glyphs: common letter pairs drawn as one 16x16 glyph, so English needs fewer glyphs.

  pairs.py choose [--write]     pick the pairs from the English (both name builds) -> text/pairs.txt
  pairs.py stats                glyphs the English needs with and without the pairs

Why: the game draws every glyph into its own 16x16 VDP1 cell and keeps at most 46 per text object
(docs/TECHNICAL.md, "Text slots"); English needs about twice the glyphs of the Japanese. The font's
glyphs are 12 px wide, so most letter pairs don't fit one - the build adds a 16x16 glyph routine:
1ST.BIN calls the glyph unpacker through the literal at 0x06020B64; it points to a dispatcher
(tools/textins.py PAIR_HOOK) that sends glyph numbers PAIR_BASE.. to a routine copying a 16x16 1bpp
bitmap (32 bytes) and everything else to the original unpacker 0x06021F60.

Codes: glyph numbers PAIR_BASE (564, Shift-JIS 84 40 - Cyrillic, box drawing; nothing the game shows)
up to 0x2EF: still proportional, the width table gives each pair the sum of its letters' advances,
so text looks exactly as with single letters. Bitmaps: two consecutive 24-byte slots of the font
(resource 68) each, taken from kanji no remaining Japanese text uses (the name-entry keyboard's
kanji are blanked - owner 2026-10-27: no kanji needed in an English release).
pairs.txt: one pair per line, in code order; the build and every tool read it (stdlib only).
"""
import argparse
import collections
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402

PAIR_BASE, PAIR_LAST = 564, 0x2EF
# Extra glyphs the font lacks, at the end of the range (code PAIR_LAST, PAIR_LAST-1, ...): arrows for
# the move categories, and a solid space - a blank glyph that still gets a cell, so per-glyph
# highlights (the boot screen's backup choice) run through it. Written as these characters.
EXTRA_ART = {
    '↑': ['...#...', '..###..', '.#.#.#.', '#..#..#', '...#...', '...#...', '...#...', '...#...'],
    '↓': ['...#...', '...#...', '...#...', '...#...', '#..#..#', '.#.#.#.', '..###..', '...#...'],
    '←': ['...#....', '..#.....', '.#......', '########', '.#......', '..#.....', '...#....'],
    '→': ['....#...', '.....#..', '......#.', '########', '......#.', '.....#..', '....#...'],
    '↔': ['..#...#..', '.#.....#.', '#########', '.#.....#.', '..#...#..'],
    '↕': ['...#...', '..###..', '.#.#.#.', '...#...', '...#...', '.#.#.#.', '..###..', '...#...'],
    '\u00a0': [],
}
EXTRA_ADVANCE = {'↑': 9, '↓': 9, '←': 10, '→': 10, '↔': 11, '↕': 9, '\u00a0': 8}
EXTRAS = list(EXTRA_ART)
PAIR_COUNT = PAIR_LAST - PAIR_BASE + 1 - len(EXTRAS)
CELL_INK = 15                   # the pair's ink must end before column 15 (bold adds a pixel)
_PAIRS = None


def file():
    return paths.TEXT / 'pairs.txt'


def table():
    """[pair] in code order (empty if there's no pairs.txt)."""
    global _PAIRS
    if _PAIRS is None:
        p = file()
        _PAIRS = [ln.rstrip('\n') for ln in p.read_text(encoding='utf-8').splitlines()
                  if ln and not ln.startswith('#')] if p.exists() else []
        _PAIRS = [x[:2] for x in _PAIRS if len(x) >= 2]
    return _PAIRS


def index():
    return {p: i for i, p in enumerate(table())}


def sjis(g):
    """Shift-JIS bytes of a glyph number below the kanji (lead 0x81-0x84)."""
    lead, t = 0x81 + g // 0xBC, g % 0xBC + 0x40
    return bytes([lead, t + 1 if t >= 0x7F else t])


def code(i):
    return sjis(PAIR_BASE + i)


def by_code():
    out = {code(i): p for i, p in enumerate(table())}
    out.update({extra_code(c): c for c in EXTRAS})
    return out


def extra_code(c):
    return sjis(PAIR_LAST - EXTRAS.index(c))


def extra_bitmap(c):
    rows = [0] * 16
    art = EXTRA_ART[c]
    top = 6 if len(art) <= 7 else 5
    for y, line in enumerate(art):
        rows[top + y] = sum(0x8000 >> (x + 1) for x, ch in enumerate(line) if ch == '#')
    return b''.join(struct.pack('>H', r) for r in rows)


def runs(letters_run, known):
    """Split a run of single-byte letters into the fewest glyphs: [(text, is_pair)]."""
    n = len(letters_run)
    best = [0] + [10 ** 6] * n
    step = [0] * (n + 1)
    for i in range(1, n + 1):
        best[i], step[i] = best[i - 1] + 1, 1
        if i >= 2 and letters_run[i - 2:i] in known and best[i - 2] + 1 <= best[i]:
            best[i], step[i] = best[i - 2] + 1, 2
    out, i = [], n
    while i > 0:
        out.append((letters_run[i - step[i]:i], step[i] == 2))
        i -= step[i]
    return out[::-1]


# ------------------------------------------------------------------ fitting and bitmaps

def _letter_rows():
    """{letter: (rows of 12 bits, advance, last ink column)} from the tightened English font."""
    import fpstext as ft
    font, w = ft.english_font(pairs=False)
    tbl, data = struct.unpack_from('>HH', font, 0)
    out = {}
    for c in ft.LETTERS:
        b = ft.full(c)
        g = ft.glyph_number(b[0], b[1])
        k = struct.unpack_from('>H', font, (tbl + g) * 2)[0]
        bits = int.from_bytes(font[data * 2 + k * 24:data * 2 + k * 24 + 24], 'big')
        rows = [(bits >> (180 - 12 * y)) & 0xFFF for y in range(16)]
        ink = 0
        for r in rows:
            ink |= r
        last = max((x for x in range(12) if ink & (0x800 >> x)), default=0)
        out[c] = (rows, w[g], last)
    return out


def fits(p, letters=None):
    letters = letters or _letter_rows()
    if len(p) != 2 or p[0] not in letters or p[1] not in letters:
        return False
    return letters[p[0]][1] + letters[p[1]][2] < CELL_INK


def bitmap(p, letters):
    """32 bytes: 16 rows of 16 bits, first letter at x=0, second at its advance."""
    (ra, adv, _), (rb, _, _) = letters[p[0]], letters[p[1]]
    rows = [((a << 4) | ((b << 4) >> adv)) & 0xFFFF for a, b in zip(ra, rb)]
    return b''.join(struct.pack('>H', r) for r in rows)


def kept_glyphs():
    """Glyph numbers (kanji) the English builds still draw: untranslated entries, 3RD.BIN, and
    pointed strings no translation covers."""
    import fpstext as ft
    import textdb
    keep = set()

    def add(b):
        i = 0
        while i < len(b) - 1:
            c = b[i]
            if 0x81 <= c <= 0x9F or 0xE0 <= c <= 0xEF:
                g = ft.glyph_number(c, b[i + 1])
                if g > ft.FIXED_ABOVE:
                    keep.add(g)
                i += 2
            else:
                i += 1
    covered = set()
    for e in textdb.entries():
        if e.english:
            covered.add(e.key)
            continue
        try:
            add(ft.encode(e.source, english=False))
        except ValueError:
            pass
    for name in ('1ST.BIN', '2ND.BIN', '3RD.BIN'):
        pt = ft.Pointed(name)
        for a, (o, n) in pt.strings.items():
            if name == '3RD.BIN' or f'{name[:3]}:{a:08X}' not in covered:
                add(pt.data[o:o + n])
    return keep


def font_with_pairs(font, widths):
    """Add the pair bitmaps and widths to an English font (bytearray, bytearray)."""
    import fpstext as ft
    pairs = table()
    if not pairs:
        return font, widths
    tbl, data = struct.unpack_from('>HH', font, 0)
    n = data - tbl
    look = [struct.unpack_from('>H', font, (tbl + g) * 2)[0] for g in range(n)]
    keep = kept_glyphs()
    users = collections.defaultdict(list)
    for g, k in enumerate(look):
        if k:
            users[k].append(g)
    free = sorted(k for k, gs in users.items()
                  if all(g > ft.FIXED_ABOVE and g not in keep for g in gs))
    slots, i = [], 0
    need = len(pairs) + len(EXTRAS)
    while i < len(free) - 1 and len(slots) < need:
        if free[i + 1] == free[i] + 1:
            slots.append(free[i])
            i += 2
        else:
            i += 1
    if len(slots) < need:
        raise SystemExit(f'pairs: room for {len(slots)} bitmaps, {need} wanted')
    used = set()
    for k in slots:
        used |= {k, k + 1}
    for g, k in enumerate(look):                      # kanji whose bitmap is reused: crossed box
        if k in used:
            struct.pack_into('>H', font, (tbl + g) * 2, 0)
    letters = _letter_rows()
    for i, (p, k) in enumerate(zip(pairs, slots)):
        g = PAIR_BASE + i
        struct.pack_into('>H', font, (tbl + g) * 2, k)
        o = data * 2 + k * 24
        font[o:o + 32] = bitmap(p, letters)
        widths[g] = letters[p[0]][1] + letters[p[1]][1]
    for c, k in zip(EXTRAS, slots[len(pairs):]):
        g = PAIR_LAST - EXTRAS.index(c)
        struct.pack_into('>H', font, (tbl + g) * 2, k)
        o = data * 2 + k * 24
        font[o:o + 32] = extra_bitmap(c)
        widths[g] = EXTRA_ADVANCE[c]
    return font, widths


# ------------------------------------------------------------------ choosing

def corpus():
    """Every English string the build writes, both name builds."""
    import names
    import textdb
    import dumprecords as dr
    out = []
    for e in textdb.entries():
        if e.english:
            for v in ('real', 'parody'):
                try:
                    out.append(names.resolve(e.english, v))
                except ValueError:
                    pass
    for r in dr.read_csv(paths.TEXT / 'wrestlers.csv'):
        out += [r[k] for k in ('en_name1', 'en_name2', 'parody_name1', 'parody_name2') if r.get(k)]
    for r in dr.read_csv(paths.TEXT / 'promotions.csv'):
        out += [r[k] for k in ('en_long', 'en_short', 'parody_long', 'parody_short') if r.get(k)]
    return out


def letter_runs(text):
    import fpstext as ft
    run = ''
    for m in ft.TOKEN.finditer(text):
        c = m.group(3)
        if c and c in ft.LETTERS:
            run += c
            continue
        if run:
            yield run
        run = ''
    if run:
        yield run


def choose():
    letters = _letter_rows()
    candidates = {a + b for a in letters for b in letters if fits(a + b, letters)}
    count = collections.Counter()
    for t in corpus():
        for r in letter_runs(t):
            for piece, is_pair in runs(r, candidates):
                if is_pair:
                    count[piece] += 1
    return [p for p, _ in count.most_common(PAIR_COUNT)]


def stats():
    import fpstext as ft
    known = set(table())
    before = after = 0
    for t in corpus():
        before += sum(1 for m in ft.TOKEN.finditer(t) if m.group(3) and m.group(3) not in ' \n')
        after += ft.glyph_count(t)
    print(f'{len(known)} pairs: {after} glyphs instead of {before} ({after / max(before, 1):.0%})')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], epilog=paths.FOLDER_HELP,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('choose')
    p.add_argument('--write', action='store_true')
    sub.add_parser('stats')
    a = ap.parse_args(paths.configure(sys.argv[1:] if argv is None else argv))
    if a.cmd == 'stats':
        stats()
        return
    chosen = choose()
    if a.write:
        file().write_text('# Two-letter glyphs (tools/pairs.py choose --write), one per line in code order:\n'
                          '# line N = glyph number 564+N (Shift-JIS 84 40...). Changing the list changes\n'
                          '# the codes: rebuild everything after.\n' + '\n'.join(chosen) + '\n',
                          encoding='utf-8')
        print(f'{paths.show(file())}: {len(chosen)} pairs')
    else:
        print(' '.join(chosen))


if __name__ == '__main__':
    main()
