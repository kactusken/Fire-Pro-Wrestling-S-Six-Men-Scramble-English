#!/usr/bin/env python3
"""Write the fixed-size name tables of 1ST.BIN into translation/text/ (English already there is kept).

  dumprecords.py [--suggest DIR]

  wrestlers.csv    the 160 roster records (0x0603E680, 0x1AC bytes each): name fields and nickname
  promotions.csv   the 15 promotions: long name (26-byte slots) and short name (14-byte slots)
  moves.csv        the move names (table 0x06050898 -> packed pool): one row per distinct name

--suggest DIR: a Fire Pro Wrestling G project (same engine and stand-in roster) - its wrestler,
promotion and move translations fill empty English cells, marked `[from FPG]` in the notes.
"""
import argparse
import csv
import struct
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fpstext as ft  # noqa: E402
import paths  # noqa: E402

ROSTER, ROSTER_STRIDE, ROSTER_COUNT = 0x0603E680, 0x1AC, 160
NAME1, NAME2, NICK = (0x02, 14), (0x10, 20), (0x24, 24)        # (offset, size) in a record
PROMO_LONG, PROMO_SHORT, PROMO_COUNT = (0x0603E03C, 26), (0x0603E1C2, 14), 15
MOVE_TABLE, MOVE_COUNT = 0x06050898, 2130

WRESTLER_HEAD = '''# Roster (1ST.BIN 0x0603E680: 160 records of 0x1AC bytes). Two English versions of every name:
#   en_* - the real wrestler (default build); parody_* - the game's own stand-in name, romanized
#   (build.py --names parody). en_nick is used by both.
# name1 is the short name the game shows alone (lists). The full name (0x0601B114) is name1 +
#   name2 in order 1-2, name2 + name1 in order 2-1 (record byte +1, bit 0x80), with the separator
#   from the low 4 bits of that byte (0 space, 1 ・, 2 ＝, 3 none). The English sets both per build:
#   en_order / parody_order, a space when both parts are there; so the names hold no spaces at
#   their ends. Order `1+2` joins them with no separator: a short name too long for the Wrestler
#   Select grid (7 glyphs, 52 px) is split - name1 "Fujinam" + name2 "i" = "Fujinami" (owner,
#   2026-10-27; the full name is then the family name alone). en_full / parody_full keep the
#   whole name for the text (<Fighter Yamato> tokens); they are not written to the game. English reads given name first: 2-1 name2 "Keiji", name1 "Mutoh" -> "Keiji Mutoh",
#   short "Mutoh"; 1-2 for western names written that way in the Japanese (Big Schteiner).
# Room (single-byte letters; digits and other symbols count 2): name1 13, name2 19, nick 23.
'''
PROMO_HEAD = '''# Promotions (1ST.BIN): long names in 26-byte slots (0x0603E03C), short names in 14-byte slots
# (0x0603E1C2). en_* is the real promotion (default build), parody_* the game's stand-in name.
# Room: long 25, short 13 (single-byte letters; digits and other symbols count 2).
'''
MOVE_HEAD = '''# Move names (1ST.BIN: table of 2130 u16 offsets at 0x06050898 -> packed pool). One row per
# distinct Japanese name; ids lists the table entries that use it. Half-width katakana is the
# same text as full-width. The pool holds 10,859 bytes: English, deduplicated, must fit (the build
# checks; aim for the length of the Japanese, single-byte letters).
'''


def norm(s):
    return unicodedata.normalize('NFKC', s)


def field(d, o, size):
    raw = d[o:o + size].split(b'\0')[0]
    return ft.decode(raw)


def read_csv(path):
    if not path.exists():
        return []
    with open(path, encoding='utf-8', newline='') as f:
        lines = [ln for ln in f if not ln.startswith('#')]
    return list(csv.DictReader(lines))


def write_csv(path, head, cols, rows):
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(head)
        w = csv.DictWriter(f, cols, lineterminator='\n')
        w.writeheader()
        w.writerows(rows)
    print(f'{paths.show(path)}: {len(rows)} rows')


def keep(rows, old, key, cols):
    by = {r[key]: r for r in old}
    for r in rows:
        o = by.get(r[key])
        if o:
            for c in cols:
                if o.get(c):
                    r[c] = o[c]


def fpg_tables(root):
    """(names {(n1,n2): (real, parody, nick)}, promotions [(real_full, real_short)], moves {norm jp: en})."""
    names, moves = {}, {}
    real = {r['idx']: r for r in read_csv(root / 'text/wrestlers.csv')}
    fake = {r['idx']: r for r in read_csv(root / 'text/fake_roster.csv')}
    for i, r in real.items():
        names[(norm(r['jp_short']), norm(r['jp_name']))] = (r['en_full'], fake.get(i, {}).get('full', ''), r['en_nick'])
    with open(root / 'text/moves.csv', encoding='utf-8') as f:
        for row in csv.reader(ln for ln in f if not ln.startswith('#')):
            if len(row) >= 3 and row[0].isdigit():
                moves.setdefault(norm(row[1]), row[2])
    return names, moves


def split_name(full, western=False):
    """'Tatsumi Fujinami' -> (order, name1, name2), given name first, name1 the short name.
    western: the Japanese is a foreign name already in given-family order with the given name as
    its short name (ジミー ホーク), so the English keeps that order."""
    if not full:
        return '', '', ''
    first, _, last = full.rpartition(' ')
    if not first:
        return '1-2', full, ''
    if western:
        first, _, last = full.partition(' ')
        return '1-2', first, last
    return '2-1', last, first


def katakana(s):
    return bool(s) and all('゠' <= c <= 'ヿ' or 'ｦ' <= c <= 'ﾟ' or c in '・ー' for c in s)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], epilog=paths.FOLDER_HELP,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--suggest', type=Path, metavar='DIR')
    args = ap.parse_args(paths.configure(sys.argv[1:] if argv is None else argv))
    d = (paths.EXTRACTED / '1ST.BIN').read_bytes()
    base = ft.BASES['1ST.BIN']
    fnames, fmoves = fpg_tables(args.suggest) if args.suggest else ({}, {})

    rows = []
    for i in range(ROSTER_COUNT):
        o = ROSTER - base + i * ROSTER_STRIDE
        flags = struct.unpack_from('>H', d, o)[0]
        r = {'idx': str(i), 'jp_order': '2-1' if flags & 0x80 else '1-2', 'name1': field(d, o + NAME1[0], NAME1[1]),
             'name2': field(d, o + NAME2[0], NAME2[1]), 'nick': field(d, o + NICK[0], NICK[1]),
             'en_order': '', 'en_name1': '', 'en_name2': '', 'parody_order': '', 'parody_name1': '',
             'parody_name2': '', 'en_full': '', 'parody_full': '', 'en_nick': '', 'notes': ''}
        hit = fnames.get((norm(r['name1']), norm(r['name2']))) or fnames.get((norm(r['name2']), norm(r['name1'])))
        if hit:
            west = r['jp_order'] == '1-2' and katakana(r['name1'])
            r['en_order'], r['en_name1'], r['en_name2'] = split_name(hit[0], west)
            r['parody_order'], r['parody_name1'], r['parody_name2'] = split_name(hit[1], west)
            r['en_nick'] = hit[2]
            r['notes'] = f'[from FPG] real: {hit[0]}; parody: {hit[1]}'
        rows.append(r)
    path = paths.TEXT / 'wrestlers.csv'
    cols = list(rows[0])
    keep(rows, read_csv(path), 'idx', ['en_order', 'en_name1', 'en_name2', 'parody_order', 'parody_name1',
                                       'parody_name2', 'en_full', 'parody_full', 'en_nick', 'notes'])
    write_csv(path, WRESTLER_HEAD, cols, rows)

    rows = []
    for i in range(PROMO_COUNT):
        lo = PROMO_LONG[0] - base + i * PROMO_LONG[1]
        so = PROMO_SHORT[0] - base + i * PROMO_SHORT[1]
        rows.append({'idx': str(i), 'long': field(d, lo, PROMO_LONG[1]), 'short': field(d, so, PROMO_SHORT[1]),
                     'en_long': '', 'en_short': '', 'parody_long': '', 'parody_short': '', 'notes': ''})
    path = paths.TEXT / 'promotions.csv'
    keep(rows, read_csv(path), 'idx', ['en_long', 'en_short', 'parody_long', 'parody_short', 'notes'])
    write_csv(path, PROMO_HEAD, list(rows[0]), rows)

    t = MOVE_TABLE - base
    names = {}
    for i in range(MOVE_COUNT):
        p = t + struct.unpack_from('>H', d, t + 2 * i)[0]
        names.setdefault(d[p:d.index(b'\0', p)], []).append(i)
    rows = []
    for raw, ids in names.items():
        jp = ft.decode(raw)
        en = fmoves.get(norm(jp), '')
        rows.append({'id': str(ids[0]), 'ids': ' '.join(map(str, ids)), 'japanese': jp, 'english': en,
                     'notes': '[from FPG]' if en else ''})
    path = paths.TEXT / 'moves.csv'
    keep(rows, read_csv(path), 'id', ['english', 'notes'])
    write_csv(path, MOVE_HEAD, list(rows[0]), rows)
    print(f'from FPG: {sum(1 for r in rows if r["english"])} of {len(rows)} moves')


if __name__ == '__main__':
    main()
