#!/usr/bin/env python3
"""Roster data for the player's guide: every wrestler's profile, parameters and move set.

  python3 tools/guidedata.py                  write the data block of docs/guide/index.html
  python3 tools/guidedata.py --check          exit 1 if the page's data is out of date
  python3 tools/guidedata.py --json FILE      also dump the data to FILE (indented) for inspection
  python3 tools/guidedata.py --page PATH      another page (default docs/guide/index.html)

Reads the ORIGINAL game data (extracted/1ST.BIN, 2ND.BIN) and the English from translation/
(wrestlers.csv, promotions.csv, moves.csv, menus.txt, messages.txt), so the page always shows the
patch's names; both name versions are kept (fields *_real / *_parody, or a *_parody field next to a
value only where the parody build differs). Written with tools/pagedata.write().

Where each value comes from (all *from the code* unless noted; docs/TECHNICAL.md has the roster):
- Roster: 1ST 0x0603E680, 160 records of 0x1AC bytes. Wrestler Select order: byte table
  0x0603E540 (160 roster ids); entries 136-159 are the 24 hidden wrestlers (unlocked by the
  Victory Road flag or by beating them). Each promotion page lists, in that order, the records
  whose +0x44 is the page (list builder 0x0601BFFC / 0x0601C06C): pages 0-12 the promotions,
  13 HIDE (Legends).
- Profile (Wrestler Edit, 2ND 0x06094EF8 draws field f; record offset u16 table 0x060BF854 + 2f,
  value kind 0x060BFA94 + 2f, value labels 0x060BFAD8): +0 class (1 Heavy, 2 Jr. Heavy, 3 Free -
  also the class mask of the select lists), +0x3E height cm, +0x3F weight kg, +0x40 hometown
  (1ST 0x0603DFB8), +0x41 birth year - 1900 (255 = unknown), +0x42 month, +0x43 day, +0x44
  promotion, +0x45 fighting style (0x060BF9E4), +0x46 reversal type (0x060BF9B0), +0x54 critical
  type (shown as 0x060BFA20[0x060BFB68[raw]]), +0x47..+0x53, +0x55, +0x56 skills, +0x57 theme
  (0x060BE444).
- Parameters: +0x5E + i attack, i = Punch, Kick, Throw, Lock, Choke, Power, Speed, Arm, Offense,
  Rough (move info panel 0x060B3A7C shows byte - 2, so 1-10); +0x68 + i the defence values in the
  parameter screen's row order (Strike, Kick, Throw, Lock, Hold, Slam, Aerial, vs. Lariat, Defense,
  vs. Rough - label table 0x060BE078 beside the attack table 0x060BE048; the byte pairing is by row,
  not traced further).
- Moves: 55 u16 words from record +0x72 (the Edit Moves screen points 0x060CAD6C at record + 114);
  slot n (1-55) has the label 2ND 0x060C61A4[n]; id = word & 0xFFF; 0x2000 = F (finisher, 必),
  0x1000 = S (signature, 得), 0x4000 / 0x8000 = shout V1 / V2 (0x060B38E0). Checked against
  Wrestler Select's "Move" (the F move) in screenshots: Fujinami Dragon Sleeper, Misawa Tiger
  Driver, Axe Doogan (Hogan) Doogan Hammer, Rikiozan Kesagiri Chop; every wrestler has one F.
  Id 0 is an empty slot.
"""
import argparse
import json
import re
import struct
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blocks  # noqa: E402
import dumprecords as dr  # noqa: E402
import names  # noqa: E402
import pagedata  # noqa: E402
import paths  # noqa: E402

B1, B2 = 0x06004000, 0x06080000
ORDER, HIDDEN_FROM = 0x0603E540, 136
PAGES = 14                                   # promotions 0-12 + 13 HIDE (Legends)

# 2ND tables of string pointers (value labels)
CLASS_TABLE = 0x060BF918                     # [1] Heavy [2] Jr. Heavy [3] Free
HOMETOWN_TABLE = 0x0603DFB8                  # in 1ST
STYLE_TABLE, REVERSAL_TABLE = 0x060BF9E4, 0x060BF9B0
CRIT_TABLE, CRIT_ORDER = 0x060BFA20, 0x060BFB68
THEME_TABLE = 0x060BE444
MOVE_LABELS, MOVE_SLOTS, MOVES_AT = 0x060C61A4, 55, 0x72
ATTACK_LABELS, DEFENSE_LABELS = 0x060BE048, 0x060BE078     # rows 1-10
ATTACK_AT, DEFENSE_AT = 0x5E, 0x68
FINISHER, SIGNATURE = 0x2000, 0x1000

# Skills: (guide label, record offset, value-label table or None for a plain number)
SPEED3, BREATH, SPIRIT, DURAB = 0x060BFA38, 0x060BFA44, 0x060BFA50, 0x060BFA5C
SPEED5, CLIMB = 0x060BFA68, 0x060BFA88
SKILLS = [
    ('Recovery', 0x47, SPEED3), ('Recovery (bleeding)', 0x48, SPEED3),
    ('Breathing', 0x49, BREATH), ('Breathing (bleeding)', 0x4A, BREATH),
    ('Spirit', 0x4B, SPIRIT), ('Spirit (bleeding)', 0x4C, SPIRIT),
    ('Neck durability', 0x4D, DURAB), ('Arm durability', 0x4E, DURAB),
    ('Waist durability', 0x4F, DURAB), ('Leg durability', 0x50, DURAB),
    ('Movement speed', 0x51, SPEED5), ('In/out of ring speed', 0x52, SPEED5),
    ('Corner climbing', 0x53, CLIMB), ('Ring-out return count', 0x55, None),
    ('Tag work', 0x56, SPEED3),
]
CODES = re.compile(r'\{[^{}]*\}')


def u16(d, a, base):
    return struct.unpack_from('>H', d, a - base)[0]


def u32(d, a, base):
    return struct.unpack_from('>I', d, a - base)[0]


def clean(s):
    """Game text -> page text: control codes dropped, full-width letters made plain."""
    return ' '.join(unicodedata.normalize('NFKC', CODES.sub('', s)).split())


class Text:
    """English (or the Japanese, if untranslated) of the pointed strings, per build variant."""

    def __init__(self):
        self.src = {}
        for f in ('menus.txt', 'messages.txt'):
            p = paths.TEXT / f
            if not p.exists():
                sys.exit(f'{paths.show(p)} missing - run tools/dumptext.py first')
            bf = blocks.BlockFile(p)
            for b in bf.blocks:
                self.src[b.id] = ''.join(b.english) if b.english else ''.join(bf.source(b))
        self.maps = {v: names.mapping(v) for v in ('real', 'parody')}

    def resolve(self, text, variant):
        m = self.maps[variant]

        def sub(mo):
            if mo.group(1) not in m:
                raise SystemExit(f'unknown name token <{mo.group(1)}> in {text!r} - fix the translation (tools/lint.py)')
            return m[mo.group(1)]
        return names.TOKEN.sub(sub, text)

    def both(self, text):
        """(real, parody) of a text with <tokens>."""
        return tuple(clean(self.resolve(text, v)) for v in ('real', 'parody'))

    def at(self, file, addr):
        key = f'{file}:{addr:08X}'
        if key not in self.src:
            raise SystemExit(f'no string {key} in translation/text - run tools/dumptext.py')
        return self.both(self.src[key])


def put(obj, key, pair):
    """obj[key] = the real-names text; obj[key + '_parody'] only where the parody build differs."""
    obj[key] = pair[0]
    if pair[1] != pair[0]:
        obj[key + '_parody'] = pair[1]


def table_label(text, d, base, file, table, i):
    ptr = u32(d, table + 4 * i, base)
    return text.at(file, ptr) if ptr else ('', '')


def build():
    d1 = (paths.EXTRACTED / '1ST.BIN').read_bytes()
    d2 = (paths.EXTRACTED / '2ND.BIN').read_bytes()
    text = Text()
    lab = lambda table, i: table_label(text, d2, B2, '2ND', table, i)  # noqa: E731

    # move names: real / parody (moves.csv; untranslated ids keep the Japanese)
    move_en = {}
    for r in dr.read_csv(paths.TEXT / 'moves.csv'):
        for i in r['ids'].split():
            move_en[int(i)] = r['english'] or r['japanese']
    pool = dr.MOVE_TABLE
    move_jp = {}

    def move_name(i):
        if i not in move_en and i not in move_jp:
            o = pool - B1 + u16(d1, pool + 2 * i, B1)
            move_jp[i] = dr.ft.decode(d1[o:d1.index(b'\0', o)])
        return text.both(move_en.get(i) or move_jp[i])

    wrestlers_csv = {int(r['idx']): r for r in dr.read_csv(paths.TEXT / 'wrestlers.csv')}
    promos_csv = {int(r['idx']): r for r in dr.read_csv(paths.TEXT / 'promotions.csv')}
    order = list(d1[ORDER - B1:ORDER - B1 + dr.ROSTER_COUNT])
    if sorted(order) != list(range(dr.ROSTER_COUNT)):
        sys.exit('extracted/1ST.BIN: the roster order table is not a permutation - is this the original?')

    used_moves = {}
    pages = []
    for p in range(PAGES):
        r = promos_csv[p]
        pages.append({'index': p, 'name_real': r['en_long'] or clean(r['long']), 'name_parody': r['parody_long'] or clean(r['long']),
                      'short_real': r['en_short'] or clean(r['short']), 'short_parody': r['parody_short'] or clean(r['short']),
                      'japanese': clean(r['long']), 'wrestlers': []})

    for pos, ident in enumerate(order):
        o = dr.ROSTER - B1 + ident * dr.ROSTER_STRIDE
        rec = d1[o:o + dr.ROSTER_STRIDE]
        row = wrestlers_csv[ident]
        jp = clean(row['name2'] + row['name1'] if row['jp_order'] == '2-1' else row['name1'] + ' ' + row['name2'])
        w = {'id': ident, 'order': pos, 'hidden': pos >= HIDDEN_FROM}
        for v, pre in (('real', 'en_'), ('parody', 'parody_')):
            if row[pre + 'name1'] or row[pre + 'name2']:
                w['name_' + v] = row.get(pre + 'full') or names.full_name(row, pre)
                w['short_' + v] = names.short_name(row, pre)
            else:                                     # untranslated: the game keeps the Japanese
                w['name_' + v], w['short_' + v] = jp, clean(row['name1'])
        w['japanese'] = jp
        nick = text.both(row['en_nick']) if row['en_nick'] else (clean(row['nick']),) * 2
        w['nick_real'], w['nick_parody'] = nick
        w['class'] = lab(CLASS_TABLE, rec[0])[0]
        w['height'], w['weight'] = rec[0x3E], rec[0x3F]
        w['born'] = None if rec[0x41] == 255 else f'{1900 + rec[0x41]:04}-{rec[0x42]:02}-{rec[0x43]:02}'
        put(w, 'from', table_label(text, d1, B1, '1ST', HOMETOWN_TABLE, rec[0x40]))
        put(w, 'style', lab(STYLE_TABLE, rec[0x45]))
        put(w, 'reversal', lab(REVERSAL_TABLE, rec[0x46]))
        put(w, 'critical', lab(CRIT_TABLE, d2[CRIT_ORDER - B2 + rec[0x54]]))
        put(w, 'theme', lab(THEME_TABLE, rec[0x57]))
        w['attack'] = [rec[ATTACK_AT + i] - 2 for i in range(10)]
        w['defense'] = [rec[DEFENSE_AT + i] - 2 for i in range(10)]
        w['skills'] = [lab(t, rec[off])[0] if t else rec[off] for _, off, t in SKILLS]
        moves = []
        for n in range(MOVE_SLOTS):
            word = struct.unpack_from('>H', rec, MOVES_AT + 2 * n)[0]
            mid = word & 0xFFF
            used_moves[mid] = move_name(mid)
            moves.append([mid, 'F' if word & FINISHER else 'S' if word & SIGNATURE else ''])
        w['moves'] = moves
        fin = [m[0] for m in moves if m[1] == 'F']
        w['finisher'] = fin[0] if fin else None
        pages[rec[0x44]]['wrestlers'].append(w)

    move_labels = [lab(MOVE_LABELS, n)[0] for n in range(1, MOVE_SLOTS + 1)]
    real, par = names.mapping('real'), names.mapping('parody')
    data = {
        'source': 'Fire Pro Wrestling S - 6Men Scramble (Saturn): roster read from the original game data; '
                  'English names from the fan translation (tools/guidedata.py)',
        'promotions': pages,
        'hidden_count': dr.ROSTER_COUNT - HIDDEN_FROM,
        'move_labels': move_labels,
        'attack_labels': [lab(ATTACK_LABELS, i)[0] for i in range(1, 11)],
        'defense_labels': [lab(DEFENSE_LABELS, i)[0] for i in range(1, 11)],
        'skill_labels': [s[0] for s in SKILLS],
        'moves': {str(i): n[0] for i, n in sorted(used_moves.items())},
        'moves_parody': {str(i): n[1] for i, n in sorted(used_moves.items()) if n[1] != n[0]},
        # the page's Names switch: every name token that differs between the builds, [real, parody]
        'names': {t: [r, par[t]] for t, r in sorted(real.items()) if t in par and par[t] != r},
        # the guide search: one entry per wrestler the player sees from the start (hidden ones would spoil)
        'entries': [{'id': w['id'], 'name': w['name_real'], 'group': p['name_real'],
                     'text': ' '.join(x for x in (w['name_parody'] if w['name_parody'] != w['name_real'] else '',
                                                    w['nick_real'], used_moves[w['finisher']][0] if w['finisher'] is not None else '') if x)}
                    for p in pages for w in p['wrestlers'] if not w['hidden']],
    }
    return data


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], epilog=paths.FOLDER_HELP,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--check', action='store_true', help='only check that the page is up to date')
    ap.add_argument('--json', type=Path, metavar='FILE', help='also write the data to FILE (indented)')
    ap.add_argument('--page', type=Path, help='the page (default docs/guide/index.html)')
    args = ap.parse_args(paths.configure(sys.argv[1:] if argv is None else argv))
    for f in ('1ST.BIN', '2ND.BIN'):
        if not (paths.EXTRACTED / f).exists():
            sys.exit(f'{paths.show(paths.EXTRACTED / f)} missing - run python3 tools/extract.py first')
    data = build()
    if args.json:
        args.json.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
        print(f'{paths.show(args.json)}: {sum(len(p["wrestlers"]) for p in data["promotions"])} wrestlers')
    page = args.page or paths.DOCS / 'guide' / 'index.html'
    if not page.exists():
        if args.json:
            return
        sys.exit(f'{paths.show(page)} missing - create the guide page first (the kit\'s guide/starter.html)')
    if pagedata.write(page, data, check=args.check) and args.check:
        print(f'{paths.show(page)}: up to date')


if __name__ == '__main__':
    main()
