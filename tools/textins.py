#!/usr/bin/env python3
"""Insert the English into 1ST.BIN and 2ND.BIN (build.py's text steps).

  textins.py report [--names real|parody]     space used and free per file (both builds), without building

Steps (each takes the build's Files and the name variant):
  letters      the single-byte letters: both half-width tables of 1ST.BIN (0x0604F990, 0x0604FA48)
  pointed      every pointed string of 1ST/2ND.BIN (tools/fpstext.py Pointed): English from
               script/interviews.txt, text/menus.txt, text/messages.txt (or the original bytes),
               packed into the freed string areas of that file, every pointer rewritten
  records      wrestler names and nicknames, promotion names: fixed fields, NUL-padded; a wrestler's
               name order and separator (record byte +1) per build
  save titles  the backup files' comments (text/save_titles.csv), plain ASCII
  moves        the move-name pool: deduplicated, rewritten from the pool start, offsets updated

Strings are packed byte-aligned (text is read a byte at a time); the free areas are the original
strings' slots (up to the next 4-byte boundary when the padding is zero). A file's English that
doesn't fit stops the build with the shortfall.
"""
import argparse
import csv
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blocks  # noqa: E402
import dumprecords as dr  # noqa: E402
import fpstext as ft  # noqa: E402
import names  # noqa: E402
import paths  # noqa: E402

# Pointers into the middle of a string (compiler-shared tails): {file: [address]} - handled as
# strings of their own, keeping their original bytes.
SHARED_TAILS = {'2ND.BIN': [0x060BFEF0]}
SOURCES = {'2ND.BIN': ['script/interviews.txt', 'text/menus.txt'], '1ST.BIN': ['text/messages.txt']}
KANA_TABLES = [0x0604F990, 0x0604FA48]


def _id_addr(ident):
    return int(ident.split(':')[1], 16)


SPACING = re.compile(r'#\s*spacing:\s*\+(\d)')


def spaced(text, n):
    """`text` with n extra pixels after every drawn character but the last ({xN,} codes take no
    glyph): for bold title styles, where 1-px gaps close up."""
    toks = [m.group(0) for m in ft.TOKEN.finditer(text)]
    drawn = [i for i, t in enumerate(toks) if len(t) == 1 and t not in ' \n']
    for i in reversed(drawn[:-1]):
        toks.insert(i + 1, f'{{x{n},}}')
    return ''.join(toks)


def english(name, variant):
    """{address: English text with names resolved} for the pointed strings of a code file. A block
    with a `# spacing: +N` comment gets N extra pixels between its letters."""
    out = {}
    for rel in SOURCES[name]:
        bf = blocks.BlockFile(paths.TRANSLATION / rel)
        for b in bf.blocks:
            en = b.english
            if not en:
                continue
            sp = next((int(m.group(1)) for c in b.tagged('#') for m in [SPACING.search('#' + c)] if m), 0)
            if sp:
                en = [spaced(names.resolve(ln, variant), sp) for ln in en]
            if b.meta.startswith('lines='):
                addrs = [int(a, 16) for a in b.meta[6:].split(',')]
                en = en + [''] * (len(addrs) - len(en))
                for a, line in zip(addrs, en):
                    out[a] = names.resolve(line, variant)
            else:
                out[_id_addr(b.id)] = names.resolve(''.join(en), variant)
    return out


def _slots(pt):
    """Free byte ranges [(start, end)] (file offsets) made by the pointed strings, merged."""
    d, spans = pt.data, []
    for a, (o, n) in pt.strings.items():
        end = o + n + 1
        pad = (end + 3) & ~3
        if not any(d[end:pad]):
            end = pad
        spans.append((o, end))
    spans.sort()
    merged = []
    for a, b in spans:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return merged


# Strings the original lacks: {file: [(pointer word addresses, English)]} - placed with the other
# strings, and each pointer word set to them. The pointers lead to an empty string in the original.
NEW_STRINGS = {
    # Theme 37 (the secret G Gundam theme, reachable in Wrestler Edit with --unlocks extras): the
    # theme name table 0x060BE444 ends in an empty name.
    '2ND.BIN': [((0x060BE4D8,), 'Ｇ Ｇｕｎｄａｍ Ｔｈｅｍｅ')],
}


def pack(name, data, variant, check_only=False, reserve=0):
    """Relocate every pointed string of `data` (bytearray, changed in place). Returns (used, free),
    or with reserve=N (used, free, address of N bytes kept free and 4-aligned - for code)."""
    pt = ft.Pointed(name, bytes(data))
    en = english(name, variant)
    items = {}
    for a, (o, n) in pt.strings.items():
        items[a] = ft.encode(en[a]) if a in en else bytes(pt.data[o:o + n])
    for a in SHARED_TAILS.get(name, []):
        o = a - pt.base
        items[a] = bytes(pt.data[o:pt.data.index(b'\0', o)])
    refs = {a: list(pt.refs.get(a, [])) for a in items}
    for ptrs, text in NEW_STRINGS.get(name, []):
        for p in ptrs:
            v = struct.unpack_from('>I', pt.data, p - pt.base)[0]
            if v in pt.strings or pt.data[v - pt.base] != 0:
                raise SystemExit(f'{name} {p:08X}: not a pointer to an empty string - check NEW_STRINGS')
        items[ptrs[0]] = ft.encode(text)            # keyed by its first pointer (not a string address)
        refs[ptrs[0]] = [p - pt.base for p in ptrs]
    for a in SHARED_TAILS.get(name, []):
        refs[a] = [o for o in range(0, len(pt.data) - 3, 4) if struct.unpack_from('>I', pt.data, o)[0] == a]
    regions = _slots(pt)
    free = [list(r) for r in regions]
    kept = None
    if reserve:                                   # code space: the end of the largest area
        r = max(free, key=lambda r: r[1] - r[0])
        start = (r[1] - reserve) & ~3
        if start < r[0]:
            raise SystemExit(f'{name}: no {reserve} bytes free for code')
        kept, r[1] = start, start
    total_free = sum(b - a for a, b in free)
    need = sum(len(v) + 1 for v in items.values())
    if need > total_free:
        raise SystemExit(f'{name}: the text needs {need} bytes, the string areas hold {total_free} '
                         f'({need - total_free} over) - shorten the English (tools/textins.py report)')
    if check_only:
        return (need, total_free) if not reserve else (need, total_free, pt.base + kept)
    place = {}
    for a, b in sorted(items.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        n = len(b) + 1
        for r in free:
            if r[1] - r[0] >= n:
                place[a] = r[0]
                r[0] += n
                break
        else:
            raise SystemExit(f'{name}: no room left for the string at {a:08X} ({n} bytes) - '
                             f'the areas are fragmented; shorten the English')
    for s, e in regions:
        data[s:e] = bytes(e - s)
    for a, o in place.items():
        data[o:o + len(items[a])] = items[a]
        for r in refs[a]:
            struct.pack_into('>I', data, r, pt.base + o)
    for a, b in items.items():          # follow every pointer again: it must lead to exactly this text
        for r in refs[a]:
            o = struct.unpack_from('>I', data, r)[0] - pt.base
            if bytes(data[o:o + len(b) + 1]) != b + b'\0':
                raise SystemExit(f'{name}: pointer at {pt.base + r:08X} does not lead to the text of {a:08X}')
    return (need, total_free) if not reserve else (need, total_free, pt.base + kept)


def letters(data):
    for t in KANA_TABLES:
        o = t - ft.BASES['1ST.BIN']
        data[o:o + 112] = ft.kana_table()


def _field(data, off, size, text, where):
    b = ft.encode(text)
    if len(b) >= size:
        raise SystemExit(f'{where}: {text!r} is {len(b)} bytes, room for {size - 1}')
    data[off:off + size] = b + bytes(size - len(b))


def name_flags(b, order, both):
    """Record byte +1 for an English name: bit 0x80 = name2 first (order 2-1), low 4 bits the
    separator the full-name builder 0x0601B114 puts between the parts (0 space, 3 none - also for
    order 1+2, a short name split for the Wrestler Select grid)."""
    return (b & 0x70) | (0x80 if order == '2-1' else 0) | (0 if both and order != '1+2' else 3)


def records(data, variant):
    base = ft.BASES['1ST.BIN']
    pre = 'en_' if variant == 'real' else 'parody_'
    for r in dr.read_csv(paths.TEXT / 'wrestlers.csv'):
        o = dr.ROSTER - base + int(r['idx']) * dr.ROSTER_STRIDE
        if r[pre + 'name1'] or r[pre + 'name2']:
            _field(data, o + dr.NAME1[0], dr.NAME1[1], r[pre + 'name1'], f'wrestlers.csv {r["idx"]} {pre}name1')
            _field(data, o + dr.NAME2[0], dr.NAME2[1], r[pre + 'name2'], f'wrestlers.csv {r["idx"]} {pre}name2')
            data[o + 1] = name_flags(data[o + 1], r[pre + 'order'], r[pre + 'name1'] and r[pre + 'name2'])
        if r['en_nick']:
            _field(data, o + dr.NICK[0], dr.NICK[1], names.resolve(r['en_nick'], variant), f'wrestlers.csv {r["idx"]} en_nick')
    pre = 'en_' if variant == 'real' else 'parody_'
    for r in dr.read_csv(paths.TEXT / 'promotions.csv'):
        i = int(r['idx'])
        if r[pre + 'long']:
            _field(data, dr.PROMO_LONG[0] - base + i * dr.PROMO_LONG[1], dr.PROMO_LONG[1], r[pre + 'long'], f'promotions.csv {i} long')
        if r[pre + 'short']:
            _field(data, dr.PROMO_SHORT[0] - base + i * dr.PROMO_SHORT[1], dr.PROMO_SHORT[1], r[pre + 'short'], f'promotions.csv {i} short')


def save_titles(data):
    """The backup files' comments (text/save_titles.csv): plain ASCII for the memory manager."""
    for r in dr.read_csv(paths.TEXT / 'save_titles.csv'):
        t = r['english']
        if not t:
            continue
        if len(t) > 10 or any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ' for c in t):
            raise SystemExit(f'save_titles.csv {r["addr"]}: {t!r} - at most 10 capitals, digits or spaces')
        o = int(r['addr'], 16) - ft.BASES['1ST.BIN']
        data[o:o + 11] = t.encode('ascii') + bytes(11 - len(t))


def moves(data, variant, check_only=False):
    """Rewrite the move-name pool. Returns (used, room)."""
    t = dr.MOVE_TABLE - ft.BASES['1ST.BIN']
    offs = [struct.unpack_from('>H', data, t + 2 * i)[0] for i in range(dr.MOVE_COUNT)]
    start = t + min(offs)
    end = max(t + o for o in offs)
    end = data.index(b'\0', end) + 1
    en = {}
    for r in dr.read_csv(paths.TEXT / 'moves.csv'):
        if r['english']:
            for i in r['ids'].split():
                en[int(i)] = ft.encode(names.resolve(r['english'], variant))
    texts = [en.get(i) or bytes(data[t + o:data.index(b'\0', t + o)]) for i, o in enumerate(offs)]
    pool, at = bytearray(), {}
    for b in texts:
        if b not in at:
            at[b] = len(pool)
            pool += b + b'\0'
    if len(pool) > end - start:
        raise SystemExit(f'move names: {len(pool)} bytes, the pool holds {end - start} '
                         f'({len(pool) - (end - start)} over) - shorten translation/text/moves.csv')
    if check_only:
        return len(pool), end - start
    data[start:end] = bytes(pool) + bytes(end - start - len(pool))
    for i, b in enumerate(texts):
        struct.pack_into('>H', data, t + 2 * i, start - t + at[b])
    return len(pool), end - start


def font(files):
    """The tightened English glyphs (FPS.SBL resource 68) and their widths (1ST.BIN 0x0603B098)."""
    glyphs, widths = ft.english_font()
    sbl = files.get('/FPS.SBL')
    o, n = struct.unpack_from('>II', sbl, ft.FONT_ENTRY * 8)
    assert len(glyphs) == n
    sbl[o:o + n] = glyphs
    files.put('/FPS.SBL', sbl)
    d = files.get('/1ST.BIN')
    w = ft.WIDTH_TABLE - ft.BASES['1ST.BIN']
    d[w:w + len(widths)] = widths
    files.put('/1ST.BIN', d)


# Two-letter glyphs (tools/pairs.py): 0x0602099C calls the glyph unpacker through this literal; it
# is pointed at PAIR_HOOK, which unpacks glyph numbers PAIR_BASE..0x2EF (r10, set by the caller) as
# 16x16 1bpp bitmaps (16 rows x 16 bits -> 8 bytes of 4bpp each) and passes the rest on.
# The second renderer 0x0601F478 (wrestler names on some screens) has its own copy of the glyph
# routine (0x0601F1D0) and unpacker (0x06020510) with its own pointers: it gets a hook of its own.
# (unpacker literal, unpacker, bitmap pointer, cell pointer)
RENDERERS = [(0x06020B64, 0x06021F60, 0x0607A278, 0x0607A230),
             (0x0601F394, 0x06020510, 0x06070AFC, 0x06070AF4)]
# Coloured backgrounds (the boot screen's highlight): each glyph routine ORs 0x44444444 and
# 0x44440000 into every cell row - 12 pixels; pairs are wider, so both fill the whole 16-pixel row.
FILL_LITERALS = [0x06020B6C, 0x0601F39C]
PAIR_HOOK = """
    mov.l =PAIR_BASE,r1
    cmp/hs r1,r10          ; glyph number >= PAIR_BASE
    bf normal
    mov.l =0x2EF,r1
    cmp/hi r1,r10          ; > 0x2EF: not a pair
    bt normal
    mov.l =SRC,r0
    mov.l @r0,r2           ; the bitmap
    mov.l =DST,r0
    mov.l @r0,r3           ; the VDP1 cell being built
    mov #16,r6
row:
    mov.w @r2+,r0
    shll16 r0
    mov #8,r5
two:
    mov #0,r1
    shll r0                ; left pixel -> high nibble
    rotcl r1
    shll2 r1
    shll2 r1
    shll r0                ; right pixel -> low nibble
    movt r4
    or r4,r1
    mov.b r1,@r3
    dt r5
    bf/s two
    add #1,r3
    dt r6
    bf row
    mov.l =DST,r0
    rts
    mov.l r3,@r0           ; the next cell, as the original unpacker leaves it
normal:
    mov.l =UNPACKER,r0
    jmp @r0
    nop
    .pool
"""
PAIR_HOOK_SIZE = 96


def pair_hook(d, addr):
    """Write the pair hooks (one per renderer) from addr and point the unpacker literals at them."""
    import pairs
    import sh2
    base = ft.BASES['1ST.BIN']
    for literal, unpacker, src, dst in RENDERERS:
        code, _ = sh2.assemble(PAIR_HOOK, addr, {'PAIR_BASE': pairs.PAIR_BASE, 'UNPACKER': unpacker,
                                                 'SRC': src, 'DST': dst})
        if len(code) > PAIR_HOOK_SIZE:
            raise SystemExit(f'pair hook: {len(code)} bytes, room {PAIR_HOOK_SIZE}')
        d[addr - base:addr - base + len(code)] = code
        o = literal - base
        if struct.unpack_from('>I', d, o)[0] != unpacker:
            raise SystemExit(f'1ST.BIN {literal:08X}: not the unpacker literal - check RENDERERS')
        struct.pack_into('>I', d, o, addr)
        addr += PAIR_HOOK_SIZE
    for a in FILL_LITERALS:
        o = a - base
        if struct.unpack_from('>I', d, o)[0] != 0x44440000:
            raise SystemExit(f'1ST.BIN {a:08X}: not the background fill constant - check FILL_LITERALS')
        struct.pack_into('>I', d, o, 0x44444444)


def step_1st(files, variant):
    """build.py text step: font, letters, 1ST.BIN pointed strings, records, save titles, moves."""
    font(files)
    d = files.get('/1ST.BIN')
    letters(d)
    import pairs
    if pairs.table():
        used, room, hook = pack('1ST.BIN', d, variant, reserve=PAIR_HOOK_SIZE * len(RENDERERS))
        pair_hook(d, hook)
    else:
        used, room = pack('1ST.BIN', d, variant)
    records(d, variant)
    save_titles(d)
    mu, mr = moves(d, variant)
    files.put('/1ST.BIN', d)
    print(f'text: 1ST.BIN strings {used}/{room} bytes, move names {mu}/{mr} bytes')


# Layout data the English needs (always applied with the text): (file, address, original, new, why)
LAYOUT_PATCHES = [
    # Wrestler Edit profile: glyph room of each of the 32 value rows (0x060958xx adds it to the
    # VRAM pointer after allocating the slot) - the Japanese values are 2-4 kanji, the English
    # words (Slow, Poor, Weak, Average...) up to 8 letters.
    ('/2ND.BIN', 0x060BFCFC, bytes([0, 16, 8, 5, 5, 5, 3, 3, 16, 8, 8, 7, 2, 2, 3, 3, 2, 2, 2, 2, 2, 2, 4, 4, 4, 2, 2, 16, 4, 4, 4, 4]), bytes([0, 16, 8, 5, 5, 5, 3, 3, 16, 8, 8, 7, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 16, 8, 8, 8, 8]),
     'profile value rooms'),
    # Endings (heavy 2ND 0x060B7224, junior 0x060B84xx): the text context gets a fixed pitch of 18 px
    # per glyph (+26), even for two-letter glyphs ("t he lo ng"); 0 = the proportional widths of
    # every other screen.
    ('/2ND.BIN', 0x060B72A4, bytes.fromhex('e112'), bytes.fromhex('e100'), 'heavy ending text pitch'),
    ('/2ND.BIN', 0x060B8520, bytes.fromhex('e112'), bytes.fromhex('e100'), 'junior ending text pitch'),
    # Title match banners (2ND 0x06091EBA): prefix (table 0x060BEA5C) + number + suffix (0x060BEA94);
    # line 3 is "" + N + "回目の防衛" (the Nth defence). English needs the word first: the prefix
    # points at the suffix's string ("Defense #") and the suffix at the empty string.
    ('/2ND.BIN', 0x060BEA68, bytes.fromhex('060bea58'), bytes.fromhex('060bea88'), 'defence line: word first'),
    ('/2ND.BIN', 0x060BEAA0, bytes.fromhex('060bea88'), bytes.fromhex('060bea58'), 'defence line: no suffix'),
    # The same function's "Entry No." + number skips 6 bytes of the formatter's buffer (two
    # digits); its literal is shared with the banner lines, which go through NUMBER_HOOK
    # (already trimmed), so it skips 4 like the others.
    ('/2ND.BIN', 0x06091F7E, bytes.fromhex('7106'), bytes.fromhex('7104'), 'entry number: trimmed by NUMBER_HOOK'),
]


def layout(files):
    for name, addr, old, new, why in LAYOUT_PATCHES:
        d = files.get(name)
        o = addr - ft.BASES[name.strip('/')]
        if bytes(d[o:o + len(old)]) not in (old, new):
            raise SystemExit(f'{name} {addr:08X} ({why}): unexpected bytes - check LAYOUT_PATCHES')
        d[o:o + len(new)] = new
        files.put(name, d)


FULL = {chr(c): chr(c + 0xFEE0) for c in range(0x21, 0x7F)}


def fields(files):
    """text/fields.csv: fixed-size fields (the new Edit wrestler's names...), NUL-padded."""
    for r in dr.read_csv(paths.TEXT / 'fields.csv'):
        if not r['english']:
            continue
        text = ''.join(FULL.get(c, c) for c in r['english']) if r['full'] == 'yes' else r['english']
        name = '/' + r['file']
        d = files.get(name)
        _field(d, int(r['id'], 16) - ft.BASES[r['file']], int(r['size']), text, f'fields.csv {r["id"]}')
        files.put(name, d)


KEYBOARD_ROWS = (0x060AC6A0, 0x060ADE80)      # name-entry keyboard: 32-byte rows (fpstext RECORD_AREAS)


def keyboard(files):
    """Blank the keyboard's kanji (full-width spaces): their font bitmaps hold two-letter glyphs now
    (tools/pairs.py; owner 2026-10-27 - no kanji needed in the English release)."""
    d = files.get('/2ND.BIN')
    base = ft.BASES['2ND.BIN']
    for a in range(*KEYBOARD_ROWS, 32):
        o = a - base
        i = o
        while i < o + 32 and d[i]:
            c = d[i]
            if 0x81 <= c <= 0x9F or 0xE0 <= c <= 0xEF:
                if ft.glyph_number(c, d[i + 1]) > ft.FIXED_ABOVE:
                    d[i:i + 2] = b'\x81\x40'
                i += 2
            else:
                i += 1
    files.put('/2ND.BIN', d)


# Numbers after "#" (Past Champs: "#" + number + " Champion"): 0x06021DB8 formats a number as five
# full-width digits with the leading zeros as full-width spaces, and the caller shows the last three
# - "#  2 Champion" (Japanese 第  2代 reads the same). These calls go through NUMBER_HOOK instead,
# which returns the buffer moved past up to two leading spaces (the caller still adds 4).
# (literal of the call; every call through it shows the number from buffer + 4)
NUMBER_CALLS = [0x06095EFC,     # Past Champs "#N Champion"
                0x06092064]     # title match banners ("#N Champion", "Defense #N"), Entry No.

NUMBER_HOOK = """
    sts.l pr,@-r15
    mov.l =FORMAT,r0
    jsr @r0
    nop
    lds.l @r15+,pr
    mov.l =0xFFFF8140,r2   ; full-width space, as mov.w reads it
    mov r0,r3
    add #4,r3              ; the first character the caller shows
    mov #2,r4
skip:
    mov.w @r3,r1
    cmp/eq r2,r1
    bf done
    dt r4
    bf/s skip
    add #2,r3
done:
    add #-4,r3
    rts
    mov r3,r0
    .pool
"""
NUMBER_HOOK_SIZE = 48
NUMBER_FORMAT = 0x06021DB8


def number_hook(d, addr):
    import sh2
    base = ft.BASES['2ND.BIN']
    code, _ = sh2.assemble(NUMBER_HOOK, addr, {'FORMAT': NUMBER_FORMAT})
    if len(code) > NUMBER_HOOK_SIZE:
        raise SystemExit(f'number hook: {len(code)} bytes, room {NUMBER_HOOK_SIZE}')
    d[addr - base:addr - base + len(code)] = code
    for literal in NUMBER_CALLS:
        o = literal - base
        if struct.unpack_from('>I', d, o)[0] != NUMBER_FORMAT:
            raise SystemExit(f'2ND.BIN {literal:08X}: not the number formatter literal - check NUMBER_CALLS')
        struct.pack_into('>I', d, o, addr)


def step_2nd(files, variant):
    layout(files)
    keyboard(files)
    fields(files)
    d = files.get('/2ND.BIN')
    used, room, hook = pack('2ND.BIN', d, variant, reserve=NUMBER_HOOK_SIZE)
    number_hook(d, hook)
    files.put('/2ND.BIN', d)
    print(f'text: 2ND.BIN strings {used}/{room} bytes')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], epilog=paths.FOLDER_HELP,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('report')
    p.add_argument('--names', choices=('real', 'parody'), help='one build (default: both)')
    args = ap.parse_args(paths.configure(sys.argv[1:] if argv is None else argv))
    bad = 0
    for variant in ([args.names] if args.names else ['real', 'parody']):
        for name in ('1ST.BIN', '2ND.BIN'):
            d = bytearray((paths.EXTRACTED / name).read_bytes())
            try:
                used, room = pack(name, d, variant, check_only=True)
                print(f'{variant}: {name} strings {used} of {room} bytes ({room - used} free)')
            except SystemExit as e:
                print(f'{variant}: {e}')
                bad += 1
        d = bytearray((paths.EXTRACTED / '1ST.BIN').read_bytes())
        try:
            used, room = moves(d, variant, check_only=True)
            print(f'{variant}: move names {used} of {room} bytes ({room - used} free)')
        except SystemExit as e:
            print(f'{variant}: {e}')
            bad += 1
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
