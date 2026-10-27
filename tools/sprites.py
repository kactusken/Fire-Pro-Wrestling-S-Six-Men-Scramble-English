"""Census of the VDP1 sprites emulator savestates draw from FPS.SBL resource 10 (VDP1 0x48000).

  sprites.py OUT.json STATE...         add every sprite drawn: offset, size, colour mode and bank,
                                       palette (VDP2 colour RAM) - tools/gfx.py exports with it
  sprites.py --sheet OUT.json PNG      draw them all on one sheet (2x)

Keep OUT.json in private/ (private/work/img/r10.json): the palettes are game data. Needs the kit's
platforms/saturn/emu.py ($KIT, default: Translation-Kit next to the project folder).
"""
import json, os, struct, sys
from pathlib import Path
sys.path.insert(0, str(Path(os.environ.get('KIT', Path(__file__).resolve().parents[2] / 'Translation-Kit'))
                       / 'platforms' / 'saturn'))
import emu  # noqa: E402
BANK, SIZE = 0x48000, 0x27AE0

def cram(state):
    s = emu.state_sections(state)['VDP2'][b'CRAM']
    return [struct.unpack_from('<H', s, 2 * i)[0] for i in range(len(s) // 2)]

def sprites(state):
    v = emu.state_memory(state, 'vdp1')
    out, i = [], 0
    while i < 0x80000:
        ctrl, link, pmod, colr, srca, size = struct.unpack_from('>HHHHHH', v, i)
        if ctrl & 0x8000:
            break
        if (ctrl & 0xF) in (0, 1, 2) and not ctrl & 0x4000:
            a = srca * 8
            w, h = ((size >> 8) & 0x3F) * 8, size & 0xFF
            if BANK <= a < BANK + SIZE and w and h:
                out.append((a - BANK, w, h, (pmod >> 3) & 7, colr))
        i += 32
    return out

def rgb(c):
    return ((c & 31) << 3, ((c >> 5) & 31) << 3, ((c >> 10) & 31) << 3)

if __name__ == '__main__':
    if sys.argv[1] == '--sheet':
        cat = json.load(open(sys.argv[2])); res = Path('extracted/FPS.SBL').read_bytes()
        o0 = struct.unpack_from('>I', res, 10 * 8)[0]
        sys.path.insert(0, 'tools'); import pngio
        items = sorted(cat.values(), key=lambda e: e['offset'])
        W = 340; rows = []; x = y = rh = 0; place = []
        for e in items:
            if x + e['w'] + 4 > W: x, y, rh = 0, y + rh + 4, 0
            place.append((x, y, e)); x += e['w'] + 4; rh = max(rh, e['h'])
        H = y + rh + 4
        img = [[(40, 40, 60)] * W for _ in range(H)]
        for x0, y0, e in place:
            d = res[o0 + e['offset']:]
            for yy in range(e['h']):
                for xx in range(e['w']):
                    if e['mode'] == 0:
                        b = d[(yy * e['w'] + xx) // 2]; p = (b >> 4) if xx % 2 == 0 else b & 15
                        if p: img[y0 + yy][x0 + xx] = tuple(e['palette'][p])
                    elif e['mode'] == 1:
                        b = d[(yy * e['w'] + xx) // 2]; p = (b >> 4) if xx % 2 == 0 else b & 15
                        if p: img[y0 + yy][x0 + xx] = (p * 16,) * 3
                    else:
                        p = d[yy * e['w'] + xx]
                        if p: img[y0 + yy][x0 + xx] = tuple(e['palette'][p] if p < len(e['palette']) else (255, 0, 255))
        big = [[c for c in row for _ in range(2)] for row in img for _ in range(2)]
        # write RGB png via pngio? use simple writer
        import zlib
        raw = b''.join(b'\0' + bytes(v for px in r for v in px) for r in big)
        def ch(t, d): return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d))
        Path(sys.argv[3]).write_bytes(b'\x89PNG\r\n\x1a\n' + ch(b'IHDR', struct.pack('>IIBBBBB', len(big[0]), len(big), 8, 2, 0, 0, 0)) + ch(b'IDAT', zlib.compress(raw)) + ch(b'IEND', b''))
        print(len(items), 'sprites'); sys.exit()
    out = Path(sys.argv[1]); cat = json.loads(out.read_text()) if out.exists() else {}
    for s in sys.argv[2:]:
        st = Path(s).read_bytes(); cr = cram(st)
        for off, w, h, mode, colr in sprites(st):
            k = f'r10_{off:05x}'
            if k in cat: 
                if Path(s).stem not in cat[k]['seen']: cat[k]['seen'].append(Path(s).stem)
                continue
            n = 16 if mode in (0, 1) else 256
            base = colr & ~(n - 1) if mode == 0 else colr & ~0xFF
            pal = [rgb(cr[(base + i) % len(cr)]) for i in range(n)]
            cat[k] = dict(offset=off, w=w, h=h, mode=mode, colr=colr, palette=pal, seen=[Path(s).stem])
    out.write_text(json.dumps(cat, indent=0)); print(len(cat), 'sprites catalogued')
