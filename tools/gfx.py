#!/usr/bin/env python3
"""Game images: export every catalogued original and import the English ones.

Images are raw VDP1 sprites in FPS.SBL resources: unpacked, 4 bits per pixel (colour bank mode)
or 8 (palette mode), no headers - a sprite is only an offset and a size that the code passes to
VDP1. Resource 10 (0x27AE0 bytes, copied as-is to VDP1 VRAM 0x48000) holds many; they're found by
watching the game draw (tools/sprites.py over emulator savestates), which also reads each
sprite's palette from VDP2 colour RAM. Other resources hold one picture each with its 256-colour
palette in the next resource (512 bytes, 15-bit BGR) - e.g. 64/66, the title match banners.

Image ids: r<resource>_<offset, 5 hex digits>. graphics.csv: source `FPS.SBL#<resource>`, x =
offset (hex), w/h the size, bpp 4 or 8. Exported PNGs are indexed with the pixel values as
indexes (0 = transparent), so an English PNG goes back by packing its indexes - no colour matching.

export_all(extracted, out) -> count    the catalogued sprites as review/images-original/<id>.png
import_images(images, files) -> count   pack English PNGs back into FPS.SBL (same size)
"""
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import catalog  # noqa: E402
import pngio  # noqa: E402
import paths  # noqa: E402

SBL = '/FPS.SBL'
RESOURCE = 10
CENSUS = paths.PRIVATE / 'work' / 'img' / 'r10.json' if hasattr(paths, 'PRIVATE') else \
    Path(__file__).resolve().parent.parent / 'private' / 'work' / 'img' / 'r10.json'


def resource(sbl, n=RESOURCE):
    o, size = struct.unpack_from('>II', sbl, n * 8)
    return o, size


def unpack(data, w, h, bpp):
    if bpp == 4:
        return [[(data[(y * w + x) // 2] >> (4 if x % 2 == 0 else 0)) & 15 for x in range(w)] for y in range(h)]
    return [list(data[y * w:(y + 1) * w]) for y in range(h)]


def pack(rows, bpp):
    if bpp == 4:
        flat = [v for r in rows for v in r]
        return bytes((flat[i] << 4) | flat[i + 1] for i in range(0, len(flat), 2))
    return bytes(v for r in rows for v in r)


def sprites():
    """{id: (resource, offset, w, h, bpp)} from graphics.csv rows with source FPS.SBL#<n>."""
    out = {}
    for r in catalog.rows():
        if r['source'].startswith('FPS.SBL#'):
            out[r['image']] = (int(r['source'][8:]), int(r['x'], 16), int(r['w']), int(r['h']),
                               int(r['bpp']))
    return out


def resource_palette(sbl, n):
    """The 256 colours in resource n+1 (512 bytes, 15-bit BGR), or None."""
    o, size = resource(sbl, n + 1)
    if size != 512:
        return None
    return [((c & 31) * 8, (c >> 5 & 31) * 8, (c >> 10 & 31) * 8)
            for c in struct.unpack_from('>256H', sbl, o)]


def export_all(extracted, out):
    sbl = (Path(extracted) / 'FPS.SBL').read_bytes()
    census = json.loads(CENSUS.read_text()) if CENSUS.exists() else {}
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    for img, (res, off, w, h, bpp) in sprites().items():
        base, size = resource(sbl, res)
        data = sbl[base + off:base + off + w * h * bpp // 8]
        pal = [tuple(c) for c in census.get(img, {}).get('palette', [])] or \
            (res != RESOURCE and resource_palette(sbl, res)) or \
            [(v * 17, v * 17, v * 17) for v in range(16)]
        if len(pal) < (16 if bpp == 4 else 256):
            pal += [(255, 0, 255)] * ((16 if bpp == 4 else 256) - len(pal))
        alpha = [0] + [255] * (len(pal) - 1)
        pngio.write(out / f'{img}.png', unpack(data, w, h, bpp), pal, alpha)
        (out / f'{img}.json').write_text(json.dumps({'file': 'FPS.SBL', 'resource': res, 'offset': off,
                                                     'w': w, 'h': h, 'bpp': bpp}))
        n += 1
    return n


def import_images(images, files):
    if not images:
        return 0
    spr = sprites()
    sbl = files.get(SBL)
    for img, path in images.items():
        if img not in spr:
            raise SystemExit(f'{img}: not a FPS.SBL sprite in graphics.csv - add its source, x, w, h, bpp')
        res, off, w, h, bpp = spr[img]
        base, size = resource(sbl, res)
        png = pngio.read(path)
        if not png.indexed or (png.width, png.height) != (w, h):
            raise SystemExit(f'{path}: must be an indexed PNG of {w}x{h} in the original palette '
                             f'(tools/edit.py check {img})')
        if max(max(r) for r in png.rows) >= (1 << bpp):
            raise SystemExit(f'{path}: uses colour indexes past {(1 << bpp) - 1} - keep to the original palette')
        data = pack(png.rows, bpp)
        if off + len(data) > size:
            raise SystemExit(f'{img}: runs past resource {res}')
        sbl[base + off:base + off + len(data)] = data
    files.put(SBL, sbl)
    return len(images)
