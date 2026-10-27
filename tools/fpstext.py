#!/usr/bin/env python3
"""The game's text: codec, English encoding, pixel widths and the pointed strings of the code files.

  fpstext.py decode <file> <address>       show the string at an address (control codes as {..})
  fpstext.py width <text>                  pixel width of English text, line by line
  fpstext.py pointed <file>                list the pointed strings of 1ST/2ND/3RD.BIN (address, refs, text)
  fpstext.py roundtrip                     decode/encode every pointed string: must give the same bytes

Text in a string (docs/TECHNICAL.md, "Text"), as written in translation/:
  Japanese          Shift-JIS characters; half-width katakana bytes A6-DF show as ｦ-ﾟ
  {n} {t}           new line (0A), tab (09)
  {s3}              colour/flags: `s` and one character
  {p8,32,} {x1,} {y7,} {r12,} {e5,} {m0,}   position / move / line height / fields: numbers end in `,`
  {b}               x/y from the current box
  {w...} {c...}     box definitions (a character, then four numbers)
  {$hh}             any other byte, kept as it is (ASCII that the renderer skips, odd bytes)
  ' '               space (20): 8 px

English letters are single bytes: the half-width katakana table at 0x0604FA48 (1ST.BIN) is
rewritten so A6-DD stand for LETTERS below (the renderer turns them into the full-width glyphs, with
their proportional widths). Digits and other punctuation are stored as full-width Shift-JIS (2 bytes).
"""
import argparse
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402

BASES = {'1ST.BIN': 0x06004000, '2ND.BIN': 0x06080000, '3RD.BIN': 0x06080000}
KANA_TABLE = 0x0604FA48          # 56 x 2-byte Shift-JIS, one per byte A6-DD (1ST.BIN)
WIDTH_TABLE = 0x0603B098         # one byte per glyph number 0..0x2EF (1ST.BIN)
FIXED_ABOVE = 0x2EF              # glyph numbers above this are 12 px
SPACE_WIDTH = 8                  # 0x20 (the renderer adds 8 - 0x06020E7A)

# The single-byte letters, in byte order from A6 (56 codes; DE/DF must never follow one of them -
# they are the voicing marks the renderer merges into the previous character).
LETTERS = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ.,\'-'
assert len(LETTERS) == 0xDD - 0xA6 + 1
BYTE_OF = {c: 0xA6 + i for i, c in enumerate(LETTERS)}

ARG_CODES = set('pxyrem')        # codes with comma-terminated numbers (p takes two)
NUM = re.compile(rb'-?[0-9]{1,3},')


def full(c):
    """Full-width Shift-JIS for one character (ASCII punctuation shifted to U+FF01-FF5E)."""
    if c == ' ':
        c = '　'
    elif c in QUOTES:
        c = QUOTES[c]
    elif 0x21 <= ord(c) < 0x7F:
        c = chr(ord(c) + 0xFEE0)
    return c.encode('cp932')


# cp932 turns full-width ＂ ＇ into IBM extension codes the font lacks: use the curly ones (81 68, 81 66)
QUOTES = {'"': '”', "'": '’'}


def _code_end(b, i):
    """End of the control code starting at b[i] (a lowercase letter), or None if it isn't one."""
    c = chr(b[i])
    if c == 'b':
        return i + 1
    if c == 's':
        return i + 2 if i + 1 < len(b) and 0x30 <= b[i + 1] <= 0x3F else None
    if c in ARG_CODES:
        j = i + 1
        for _ in range(2 if c == 'p' else 1):
            m = NUM.match(b, j)
            if not m:
                return None
            j = m.end()
        return j
    if c in 'wc':
        j = i + 2
        for _ in range(4):
            m = NUM.match(b, j)
            if not m:
                return None
            j = m.end()
        return j
    return None


def decode(b):
    """Bytes of one string (no NUL) -> text in the translation files' notation (lossless)."""
    out, i = [], 0
    while i < len(b):
        c = b[i]
        if (0x81 <= c <= 0x9F or 0xE0 <= c <= 0xEF) and i + 1 < len(b):
            pair = _pair_codes().get(bytes(b[i:i + 2]))
            if pair:
                out.append(pair)
                i += 2
                continue
            try:
                out.append(b[i:i + 2].decode('cp932'))
                i += 2
                continue
            except UnicodeDecodeError:
                pass
        if 0xA1 <= c <= 0xDF:
            out.append(bytes([c]).decode('cp932'))
        elif c == 0x0A:
            out.append('{n}')
        elif c == 0x09:
            out.append('{t}')
        elif c == 0x20:
            out.append(' ')
        elif 0x61 <= c <= 0x7A and _code_end(b, i):
            j = _code_end(b, i)
            out.append('{' + b[i:j].decode('ascii') + '}')
            i = j
            continue
        else:
            out.append(f'{{${c:02x}}}')
        i += 1
    return ''.join(out)


_PAIR_CODES = None


def _pair_codes():
    global _PAIR_CODES
    if _PAIR_CODES is None:
        import pairs
        _PAIR_CODES = pairs.by_code()
    return _PAIR_CODES


TOKEN = re.compile(r'\{\$([0-9a-f]{2})\}|\{n\}|\{t\}|\{([a-z][^{}]*)\}|(.)', re.S)


def encode(text, english=True):
    """Text -> bytes. english=True: ASCII letters and . , ' - as the single-byte letters."""
    out = bytearray()
    prev = ' '
    run = []
    known = _pair_index() if english else {}

    def flush():
        if not run:
            return
        if known:
            import pairs
            for piece, is_pair in pairs.runs(''.join(run), known):
                out.extend(pairs.code(known[piece]) if is_pair else bytes(BYTE_OF[c] for c in piece))
        else:
            out.extend(BYTE_OF[c] for c in run)
        run.clear()
    for m in TOKEN.finditer(text):
        tok = m.group(0)
        if english and m.group(3) and m.group(3) in BYTE_OF and not (m.group(3) == '"'):
            run.append(m.group(3))
            prev = m.group(3)
            continue
        flush()
        if m.group(3) == '"' and prev in ' ({':    # an opening quote: “ (81 67)
            out += b'\x81\x67'
            prev = '"'
            continue
        prev = m.group(3) or ' '
        if m.group(1):
            out.append(int(m.group(1), 16))
        elif tok == '{n}':
            out.append(0x0A)
        elif tok == '{t}':
            out.append(0x09)
        elif m.group(2):
            out += m.group(2).encode('ascii')
        else:
            c = m.group(3)
            if c == ' ':
                out.append(0x20)
            elif english and c in BYTE_OF:
                out.append(BYTE_OF[c])
            elif '｡' <= c <= 'ﾟ':
                out += c.encode('cp932')
            elif c == '\n':
                out.append(0x0A)
            elif english and c in _extras():
                out += _extras()[c]
            else:
                try:
                    out += full(c)
                except UnicodeEncodeError:
                    raise ValueError(f'{c!r} has no Shift-JIS code: {text!r}')
    flush()
    return bytes(out)


_PAIR_INDEX = None
_EXTRAS = None


def _extras():
    """{character: code} of the extra glyphs (arrows, solid space - tools/pairs.py)."""
    global _EXTRAS
    if _EXTRAS is None:
        import pairs
        _EXTRAS = {c: pairs.extra_code(c) for c in pairs.EXTRAS} if pairs.table() else {}
    return _EXTRAS


def _pair_index():
    """{pair: number} of the two-letter glyphs (tools/pairs.py; empty without pairs.txt)."""
    global _PAIR_INDEX
    if _PAIR_INDEX is None:
        import pairs
        _PAIR_INDEX = pairs.index()
    return _PAIR_INDEX


# ------------------------------------------------------------------ widths

_WIDTHS = None
# Glyphs the English font tightens: drawn flush left, advance = ink width + 1 (digits keep their
# fixed width so number columns stay aligned)
TIGHT = [chr(c) for c in range(0x21, 0x7F) if not chr(c).isdigit()] + ['“', '”', '’']
NARROW = set('ilIj!')     # thin letters: one pixel on each side, so "illi" doesn't run together


def original_widths():
    d = (paths.EXTRACTED / '1ST.BIN').read_bytes()
    o = WIDTH_TABLE - BASES['1ST.BIN']
    return bytearray(d[o:o + FIXED_ABOVE + 1])


def original_font():
    sbl = (paths.EXTRACTED / 'FPS.SBL').read_bytes()
    o, n = struct.unpack_from('>II', sbl, FONT_ENTRY * 8)
    return sbl[o:o + n]


def english_font(pairs=True):
    """(font resource bytes, width table) with the TIGHT glyphs shifted left and their advances
    set to ink + 1, and (pairs=True) the two-letter glyphs of tools/pairs.py - what the build
    writes to FPS.SBL resource 68 and 0x0603B098."""
    font, w = bytearray(original_font()), original_widths()
    tbl, data = struct.unpack_from('>HH', font, 0)
    done = set()
    for c in TIGHT:
        try:
            b = full(c)
        except UnicodeEncodeError:
            continue
        g = glyph_number(b[0], b[1])
        if not 0 <= g <= FIXED_ABOVE:
            continue
        k = struct.unpack_from('>H', font, (tbl + g) * 2)[0]
        if k == 0 or k in done:
            continue
        done.add(k)
        o = data * 2 + k * 24
        bits = int.from_bytes(font[o:o + 24], 'big')
        rows = [(bits >> (180 - 12 * y)) & 0xFFF for y in range(16)]
        ink = 0
        for r in rows:
            ink |= r
        if not ink:
            continue
        left = next(x for x in range(12) if ink & (0x800 >> x))
        right = max(x for x in range(12) if ink & (0x800 >> x))
        pad = 1 if c in NARROW else 0         # a thin letter keeps a pixel on its left too
        rows = [((r << left) >> pad) & 0xFFF for r in rows]
        bits = 0
        for r in rows:
            bits = (bits << 12) | r
        font[o:o + 24] = bits.to_bytes(24, 'big')
        w[g] = right - left + 2 + 2 * pad
    if pairs:
        import pairs as pairs_mod
        font, w = pairs_mod.font_with_pairs(font, w)
    return bytes(font), w


def widths():
    global _WIDTHS
    if _WIDTHS is None:
        _WIDTHS = english_font()[1]
    return _WIDTHS


def glyph_number(lead, trail):
    """0x06020930: Shift-JIS -> glyph number."""
    t = trail - 1 if trail >= 0x80 else trail
    if lead <= 0x87:
        return (lead - 0x81) * 0xBC + t - 0x40
    row = (lead + 120) & 0xFF if not lead & 0x40 else (lead + 56) & 0xFF
    return row * 0xBC + t + 0x252


def char_width(sjis):
    lead, trail = sjis
    if lead == 0x81 and trail == 0x40:
        return 12
    g = glyph_number(lead, trail)
    return widths()[g] if g <= FIXED_ABOVE else 12


def line_widths(text, english=True):
    """Pixel width of each line ({n} splits lines; x/p codes are not followed)."""
    out, x = [], 0
    for m in TOKEN.finditer(text):
        tok = m.group(0)
        if tok == '{n}':
            out.append(x)
            x = 0
        elif m.group(1) or m.group(2) or tok == '{t}':
            continue
        else:
            c = m.group(3)
            if c == ' ':
                x += SPACE_WIDTH
            else:
                b = encode(c, english)
                if len(b) == 1 and 0xA6 <= b[0] <= 0xDD:
                    b = kana_table_entry(b[0], english)
                x += char_width(b) if len(b) == 2 else 0
    out.append(x)
    return out


def glyph_count(text):
    """Glyphs the renderer draws for `text` - one 16x16 VDP1 cell each (spaces, codes and new
    lines take none; a two-letter glyph is one). Text redrawn into a reserved slot must fit its
    room (tools/slots.py)."""
    b, n, i = encode(text), 0, 0
    while i < len(b):
        c = b[i]
        if 0x81 <= c <= 0x9F or 0xE0 <= c <= 0xEF:
            n += b[i:i + 2] != b'\x81\x40'
            i += 2
            continue
        if 0x61 <= c <= 0x7A and _code_end(b, i):
            i = _code_end(b, i)
            continue
        n += 0xA6 <= c <= 0xDD
        i += 1
    return n


def kana_table_entry(byte, english=True):
    """The 2-byte code a single byte A6-DD is drawn as (the English table, or the original)."""
    if english:
        return full(LETTERS[byte - 0xA6])
    d = (paths.EXTRACTED / '1ST.BIN').read_bytes()
    o = KANA_TABLE - BASES['1ST.BIN'] + (byte - 0xA6) * 2
    return d[o:o + 2]


FONT_ENTRY = 68                 # FPS.SBL resource holding the font
_FONT = None


def has_glyph(sjis):
    """True if the font draws this 2-byte character (a missing one draws glyph 0, a crossed box)."""
    global _FONT
    if _FONT is None:
        sbl = (paths.EXTRACTED / 'FPS.SBL').read_bytes()
        o, n = struct.unpack_from('>II', sbl, FONT_ENTRY * 8)
        _FONT = sbl[o:o + n]
    tbl = struct.unpack_from('>H', _FONT, 0)[0]
    if sjis == b'\x81\x40':
        return True
    g = glyph_number(sjis[0], sjis[1])
    data = struct.unpack_from('>H', _FONT, 2)[0]
    return 0 <= g < data - tbl and struct.unpack_from('>H', _FONT, (tbl + g) * 2)[0] != 0


def missing_glyphs(text):
    """Characters of `text` the font can't draw."""
    out = []
    for m in TOKEN.finditer(text):
        c = m.group(3)
        if c and c not in BYTE_OF and c != ' ' and not '\uff61' <= c <= '\uff9f' and c not in _extras():
            try:
                b = full(c)
            except UnicodeEncodeError:
                out.append(c)
                continue
            if len(b) == 2 and not has_glyph(b):
                out.append(c)
    return out


def kana_table():
    """The English kana table: 56 x 2 bytes for 0x0604FA48."""
    return b''.join(full(c) for c in LETTERS)


# ------------------------------------------------------------------ pointed strings

def _is_text(b):
    i, n = 0, 0
    while i < len(b):
        c = b[i]
        if 0x81 <= c <= 0x9F or 0xE0 <= c <= 0xEF:
            if i + 1 >= len(b) or not 0x40 <= b[i + 1] <= 0xFC or b[i + 1] == 0x7F:
                return False
            n += 1
            i += 2
        elif 0xA6 <= c <= 0xDF:
            n += 1
            i += 1
        elif c in (9, 10) or 0x20 <= c <= 0x7E:
            i += 1
        else:
            return False
    return n > 0


# Fixed-slot record tables whose base address the code loads (they look like a pointed string):
# written by tools/textins.py records(), never relocated
# Areas of fixed records, not strings to move: the promotion long and short names; the name-entry
# keyboard rows (32 bytes each, reached by address from row to row - moving them hung the game
# on the first DOWN press, seen in the emulator 2026-10-27)
RECORD_AREAS = {'1ST.BIN': [(0x0603E03C, 0x0603E294)], '2ND.BIN': [(0x060AC6A0, 0x060ADE80)]}


class Pointed:
    """The strings of a code file that aligned 32-bit words point at.

    .strings: {address: (offset, length without NUL)}; .refs: {address: [offset of each pointer]}
    """

    def __init__(self, name, data=None):
        self.name, self.base = name, BASES[name]
        self.data = data if data is not None else (paths.EXTRACTED / name).read_bytes()
        d, base = self.data, self.base
        words = {}
        for o in range(0, len(d) - 3, 4):
            v = struct.unpack_from('>I', d, o)[0]
            if base <= v < base + len(d):
                words.setdefault(v, []).append(o)
        pools = set()           # literal-pool words: targets of mov.l @(disp,PC)
        for o in range(0, len(d) - 1, 2):
            if d[o] >> 4 == 0xD:
                pools.add(((o & ~3) + 4 + d[o + 1] * 4))

        def pointer_like(o):
            near = (struct.unpack_from('>I', d, x)[0] for x in (o - 4, o + 4) if 0 <= x <= len(d) - 4)
            return o in pools or any(base <= v < base + len(d) for v in near)
        self.strings, self.refs = {}, {}
        for v, offs in sorted(words.items()):
            o = v - base
            if o and d[o - 1] != 0:
                # not after a NUL: only a 4-aligned start that code loads or a pointer table holds
                # (string literals are aligned; this keeps out u16 data that looks like an address)
                if o % 4 or not any(pointer_like(r) for r in offs):
                    continue
            e = d.find(b'\0', o)
            if e <= o or not _is_text(d[o:e]):
                continue
            if any(lo <= v < hi for lo, hi in RECORD_AREAS.get(name, [])):
                continue
            t = decode(d[o:e])
            if '{$' in t or (len(t) == 1 and 'ｦ' <= t <= 'ﾟ'):
                continue        # data that happens to decode (raw bytes, a lone half-width byte)
            self.strings[v] = (o, e - o)
            self.refs[v] = offs

    def text(self, addr):
        o, n = self.strings[addr]
        return decode(self.data[o:o + n])

    def tables(self, min_len=3):
        """Runs of consecutive pointer words (NULL words allowed inside): [(offset, [address or 0])]."""
        at = {o: v for v, offs in self.refs.items() for o in offs if v in self.strings}
        out, cur, start = [], [], None
        for o in range(0, len(self.data) - 3, 4):
            v = at.get(o)
            if v is None and cur and struct.unpack_from('>I', self.data, o)[0] == 0:
                v = 0
            if v is None:
                while cur and cur[-1] == 0:
                    cur.pop()
                if len(cur) >= min_len:
                    out.append((start, cur))
                cur = []
                continue
            if not cur:
                start = o
            cur.append(v)
        return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], epilog=paths.FOLDER_HELP,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('decode')
    p.add_argument('file')
    p.add_argument('address', type=lambda s: int(s, 16))
    p = sub.add_parser('width')
    p.add_argument('text')
    p = sub.add_parser('pointed')
    p.add_argument('file')
    sub.add_parser('roundtrip')
    args = ap.parse_args(paths.configure(sys.argv[1:] if argv is None else argv))
    if args.cmd == 'decode':
        d = (paths.EXTRACTED / args.file).read_bytes()
        o = args.address - BASES[args.file]
        print(decode(d[o:d.find(b'\0', o)]))
    elif args.cmd == 'width':
        print(line_widths(args.text.replace('\\n', '{n}')))
    elif args.cmd == 'pointed':
        pt = Pointed(args.file)
        for a in pt.strings:
            print(f'{a:08X} {len(pt.refs[a]):2d}  {pt.text(a)}')
    else:
        bad = 0
        for name in BASES:
            pt = Pointed(name)
            for a, (o, n) in pt.strings.items():
                raw = pt.data[o:o + n]
                if encode(decode(raw), english=False) != raw:
                    bad += 1
                    print(f'{name} {a:08X}: {raw.hex()} -> {decode(raw)!r} -> {encode(decode(raw), False).hex()}')
            print(f'{name}: {len(pt.strings)} pointed strings')
        print('round trip:', 'ok' if not bad else f'{bad} differ')
        return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
