"""Wrestler Select info-panel labels (FPS.SBL#10, 40x16, 4bpp): a clean gold plate rebuilt from the
six originals (each pixel from the labels without text there) + the game's own English glyphs in
white (index 1) with a black (15) shadow one pixel right and down. Writes translation/images-handmade/ (then tools/edit.py check / approve).
  .venv/bin/python tools/labels.py [--preview PNG]"""
import sys
from pathlib import Path
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths; paths.configure([])
import fpstext as ft, catalog
IDS = ['r10_00000', 'r10_00140', 'r10_00280', 'r10_003c0', 'r10_00500', 'r10_00640']
W, H = 40, 16
orig = {k: Image.open(paths.ORIGINAL_IMAGES / f'{k}.png') for k in IDS}
px = {k: im.load() for k, im in orig.items()}
plate = {}
for y in range(H):
    for x in range(W):
        vals = [px[k][x, y] for k in IDS if 2 <= px[k][x, y] <= 11]      # the gold; 1, 12-15 are lettering
        if vals:
            plate[x, y] = max(set(vals), key=vals.count)
for _ in range(40):                                  # fill text-only pixels from neighbours
    for y in range(H):
        for x in range(W):
            if (x, y) not in plate:
                nb = [plate[p] for p in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)) if p in plate]
                if nb:
                    plate[x, y] = max(set(nb), key=nb.count)
font, widths = ft.english_font()
import struct
tbl, data = struct.unpack_from('>HH', font, 0)
def glyph(c):
    b = ft.full(c); g = ft.glyph_number(*b)
    k = struct.unpack_from('>H', font, (tbl + g) * 2)[0]
    bits = int.from_bytes(font[data * 2 + k * 24:data * 2 + k * 24 + 24], 'big')
    return [[(bits >> (191 - (y * 12 + x))) & 1 for x in range(12)] for y in range(16)], widths[g]
def draw(text):
    img = Image.new('P', (W, H)); img.putpalette(orig[IDS[0]].getpalette())
    p = img.load()
    for (x, y), v in plate.items():
        p[x, y] = v
    gl = [glyph(c) for c in text]
    tw = sum(a + 1 for _, a in gl) - 1
    x0 = max(1, (W - tw) // 2); y0 = 0
    ink = set()
    x = x0
    for rows, adv in gl:
        for yy in range(16):
            for xx in range(12):
                if rows[yy][xx]:
                    ink.add((x + xx, y0 + yy)); ink.add((x + xx + 1, y0 + yy))     # bold, like the original
        x += adv + 1
    lo = min(y for _, y in ink); hi = max(y for _, y in ink)
    dy = (H - 1 - (hi - lo + 1)) // 2 - lo            # centre vertically, room for the shadow
    ink = {(a, b + dy) for a, b in ink}
    for a, b in ink:
        for s in ((a + 1, b + 1), (a + 1, b), (a, b + 1)):
            if s not in ink and 0 <= s[0] < W and 0 <= s[1] < H:
                p[s] = 15                             # black shadow
    for a, b in ink:
        if 0 <= a < W and 0 <= b < H:
            p[a, b] = 1                               # white lettering
    return img, tw
rows = {r['image']: r for r in catalog.rows()}
out = paths.TRANSLATION / 'images-handmade'; out.mkdir(exist_ok=True)
sheet = Image.new('RGBA', (44 * 6, 40), (40, 40, 60, 255))
for i, k in enumerate(IDS):
    img, tw = draw(rows[k]['english'])
    if tw > W - 2:
        print(f'! {k} {rows[k]["english"]!r}: {tw} px, room {W - 2}')
    img.save(out / f'{k}.png', transparency=0)
    sheet.paste(orig[k].convert('RGBA'), (i * 44 + 2, 2)); sheet.paste(img.convert('RGBA'), (i * 44 + 2, 22))
if '--preview' in sys.argv:
    sheet.resize((sheet.width * 5, sheet.height * 5), Image.NEAREST).save(sys.argv[sys.argv.index('--preview') + 1])
