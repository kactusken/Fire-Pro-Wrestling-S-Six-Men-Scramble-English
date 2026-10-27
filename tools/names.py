#!/usr/bin/env python3
"""Wrestler and promotion names in the text: <tokens> resolved per build (real or parody names).

  names.py list [--names real|parody]      every token and what it becomes
  names.py glossary                        (re)write the name rows of translation/glossary.csv

English text writes a name that differs between the two builds as a token in angle brackets, in
the game's own (parody) form: <Yamato> (short name), <Fighter Yamato> (full name), <View Japan>,
<VJP>. The build replaces each token with the real name (default) or the parody name. Tokens come
from translation/text/wrestlers.csv and promotions.csv, plus translation/text/name_tokens.csv
(token, real, parody, japanese, notes) for anyone else - factions, a word that differs (<Panther*>:
Panther / Tiger); parody defaults to the token itself. Lint reports unknown tokens.
"""
import argparse
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402

TOKEN = re.compile(r'<([^<>]+)>')
GLOSSARY_TAG = '[name]'          # glossary rows written by this tool (replaced on every run)


def _rows(name):
    p = paths.TEXT / name
    if not p.exists():
        return []
    with open(p, encoding='utf-8', newline='') as f:
        return list(csv.DictReader(ln for ln in f if not ln.startswith('#')))


def full_name(r, prefix):
    """The whole name as the game builds it (0x0601B114) from a wrestlers.csv row (prefix en_ or
    parody_): name1 name2 in order 1-2, name2 name1 in order 2-1, a space between."""
    n1, n2 = r[prefix + 'name1'], r[prefix + 'name2']
    if r[prefix + 'order'] == '1+2':                # a split short name: joined, no separator
        return n1 + n2
    parts = [n1, n2] if r[prefix + 'order'] == '1-2' else [n2, n1]
    return ' '.join(p for p in parts if p)


def short_name(r, prefix):
    """The short name for prose: name1, or the whole joined name when it was split for the grid."""
    return r[prefix + 'name1'] + r[prefix + 'name2'] if r[prefix + 'order'] == '1+2' else r[prefix + 'name1']


def entries():
    """[(token, real, parody, japanese forms, note)]."""
    out = []
    for r in _rows('wrestlers.csv'):
        if not r['parody_name1']:
            continue
        jp_full = r['name2'] + r['name1'] if r['jp_order'] == '2-1' else r['name1'] + r['name2']
        full = r.get('parody_full') or full_name(r, 'parody_')
        out.append((full, r.get('en_full') or full_name(r, 'en_'), full, [jp_full], f'wrestler {r["idx"]}'))
        short = short_name(r, 'parody_')
        if short != full:                   # a one-part parody name (Pentagon) is its full name
            out.append((short, short_name(r, 'en_'), short, [r['name1']], f'wrestler {r["idx"]} (short)'))
    for r in _rows('promotions.csv'):
        if r['parody_long']:
            out.append((r['parody_long'], r['en_long'], r['parody_long'], [r['long']], f'promotion {r["idx"]}'))
            out.append((r['parody_short'], r['en_short'], r['parody_short'], [r['short']], f'promotion {r["idx"]} (short)'))
    for r in _rows('name_tokens.csv'):
        out.append((r['token'], r['real'], r.get('parody') or r['token'], [r['japanese']] if r.get('japanese') else [],
                    r.get('notes', '')))
    return out


def mapping(variant='real'):
    """{token: English} for a build; tokens claimed by two different names are left out (ambiguous)."""
    seen, out, bad = {}, {}, set()
    for tok, real, parody, _, _ in entries():
        val = real if variant == 'real' else parody
        if tok in seen and seen[tok] != val:
            bad.add(tok)
        seen[tok] = val
        out[tok] = val
    for tok in bad:
        out.pop(tok)
    return out


def ambiguous():
    real, parody = {}, {}
    out = set()
    for tok, r, p, _, _ in entries():
        if real.setdefault(tok, r) != r or parody.setdefault(tok, p) != p:
            out.add(tok)
    return out


def resolve(text, variant='real'):
    """Replace every <token>; unknown tokens raise ValueError."""
    m = mapping(variant)

    def sub(mo):
        if mo.group(1) not in m:
            raise ValueError(f'unknown name token <{mo.group(1)}>' + (' (ambiguous: use the full name)'
                                                                       if mo.group(1) in ambiguous() else ''))
        return m[mo.group(1)]
    return TOKEN.sub(sub, text)


def write_glossary():
    p = paths.GLOSSARY
    rows = []
    if p.exists():
        with open(p, encoding='utf-8', newline='') as f:
            rows = [r for r in csv.DictReader(f) if GLOSSARY_TAG not in (r.get('notes') or '')]
    amb = ambiguous()
    seen = set()
    for tok, real, parody, jps, note in entries():
        for jp in jps:
            if len(jp) < 2 or (jp, tok) in seen or tok in amb:
                continue
            seen.add((jp, tok))
            rows.append({'japanese': jp, 'english': f'<{tok}>',
                         'notes': f'{GLOSSARY_TAG} {note}: real {real}' + ('' if real != parody else ' (same in both)')})
    with open(p, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, ['japanese', 'english', 'notes'], lineterminator='\n')
        w.writeheader()
        w.writerows(rows)
    print(f'{paths.show(p)}: {len(seen)} name rows ({len(amb)} ambiguous tokens left out: {", ".join(sorted(amb))})')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], epilog=paths.FOLDER_HELP,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('list')
    p.add_argument('--names', choices=('real', 'parody'), default='real')
    sub.add_parser('glossary')
    args = ap.parse_args(paths.configure(sys.argv[1:] if argv is None else argv))
    if args.cmd == 'list':
        for tok, val in sorted(mapping(args.names).items()):
            print(f'<{tok}> -> {val}')
    else:
        write_glossary()


if __name__ == '__main__':
    main()
