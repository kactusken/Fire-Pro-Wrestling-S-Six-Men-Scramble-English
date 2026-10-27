#!/usr/bin/env python3
"""Draw game strings the way the game does - headless, for previews and layout checks.

  textrender.py text "<text>" [--out FILE] [--names real|parody]
  textrender.py block <file> <id>... [--out FILE]      blocks of a translation file (EN, or JP if none)
  textrender.py sheet <file> [--out FILE] [--limit N]  every translated block: JP above, EN below

Follows 0x06020C48: 12x16 glyphs and advances from the English font the build writes
(fpstext.english_font(): FPS.SBL resource 68 and the width table, Latin glyphs tightened),
space 8 px (or SPACE_WIDTH), {n} new line (16 px), {t} tab to 32 px, {x}/{y}/{p} pen moves;
colours are ignored. Single-byte letters are drawn through the English half-width table. The
red line marks a pixel limit (--px, default: the block's limit or none).
Output: an indexed PNG (default build/work/render.png).
"""
import argparse
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blocks  # noqa: E402
import fpstext as ft  # noqa: E402
import names  # noqa: E402
import paths  # noqa: E402
import pngio  # noqa: E402

LINE = 16
PALETTE = [(16, 24, 48), (240, 240, 240), (200, 60, 60), (90, 90, 120)]


class Font:
    def __init__(self):
        self.f, self.widths = ft.english_font()
        self.tbl, self.data = struct.unpack_from('>HH', self.f, 0)

    def glyph(self, sjis):
        g = ft.glyph_number(*sjis)
        k = struct.unpack_from('>H', self.f, (self.tbl + g) * 2)[0] if 0 <= g < self.data - self.tbl else 0
        o = self.data * 2 + k * 24
        bits = int.from_bytes(self.f[o:o + 24], 'big')
        adv = self.widths[g] if 0 <= g <= ft.FIXED_ABOVE else 12
        return [[(bits >> (191 - (y * 12 + x))) & 1 for x in range(12)] for y in range(16)], adv


def draw(text, font, english=True):
    """[(x, y, glyph rows)] and the extent (w, h) of one string."""
    out, x, y, w = [], 0, 0, 0
    for m in ft.TOKEN.finditer(text):
        tok = m.group(0)
        if tok == '{n}':
            x, y = 0, y + LINE
            continue
        if tok == '{t}':
            x = (x & ~31) + 32
            continue
        code = m.group(2)
        if code:
            nums = [int(n) for n in re.findall(r'-?\d+', code[1:])]
            if code[0] == 'x' and nums:
                x += nums[0]
            elif code[0] == 'y' and nums:
                y += nums[0]
            elif code[0] == 'p' and len(nums) == 2:
                x, y = nums
            continue
        if m.group(1):
            continue
        c = m.group(3)
        if c == ' ':
            x += ft.SPACE_WIDTH
            continue
        b = ft.encode(c, english)
        if len(b) == 1 and 0xA6 <= b[0] <= 0xDD:
            b = ft.kana_table_entry(b[0], english)
        if len(b) != 2:
            continue
        if b == b'\x81\x40':
            x += 12
            continue
        rows, adv = font.glyph(b)
        out.append((x, y, rows))
        x += adv
        w = max(w, x)
    return out, (max(w, x), y + LINE)


def render(lines, out, px=None, scale=2):
    """lines: [(text, english)] drawn under each other; px: a red limit line."""
    font = Font()
    drawn = [draw(t, font, e) for t, e in lines]
    width = max([ex[0] for _, ex in drawn] + [px or 0]) + 8
    height = sum(ex[1] + 4 for _, ex in drawn) + 4
    img = [[0] * width for _ in range(height)]
    top = 4
    for glyphs, (_, h) in drawn:
        for x0, y0, rows in glyphs:
            for yy in range(16):
                for xx in range(12):
                    if rows[yy][xx] and 0 <= top + y0 + yy < height and 0 <= 4 + x0 + xx < width:
                        img[top + y0 + yy][4 + x0 + xx] = 1
        top += h + 4
    if px:
        for yy in range(height):
            if 4 + px < width:
                img[yy][4 + px] = 2
    big = [[v for v in row for _ in range(scale)] for row in img for _ in range(scale)]
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    pngio.write(out, big, PALETTE)
    print(f'{paths.show(out)}: {width}x{height}')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], epilog=paths.FOLDER_HELP,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cmd', choices=('text', 'block', 'sheet'))
    ap.add_argument('args', nargs='+')
    ap.add_argument('--out', type=Path)
    ap.add_argument('--names', choices=('real', 'parody'), default='real')
    ap.add_argument('--px', type=int)
    ap.add_argument('--limit', type=int, default=40)
    a = ap.parse_args(paths.configure(sys.argv[1:] if argv is None else argv))
    out = a.out or paths.WORK / 'render.png'
    if a.cmd == 'text':
        render([(names.resolve(a.args[0].replace('\\n', '{n}'), a.names), True)], out, a.px)
        return
    bf = blocks.BlockFile(paths.TRANSLATION / a.args[0])
    want = set(a.args[1:])
    lines, px = [], a.px or bf.limits.get('px')
    sel = [b for b in bf.blocks if (b.id in want) or (a.cmd == 'sheet' and b.english)]
    for b in sel[:a.limit]:
        if a.cmd == 'sheet':
            lines.append(('{n}'.join(bf.source(b)), False))
        en = b.english
        lines.append(('{n}'.join(names.resolve(t, a.names) for t in en) if en else '{n}'.join(bf.source(b)), bool(en)))
    render(lines, out, px)


if __name__ == '__main__':
    main()
