#!/usr/bin/env python3
"""Check the translation text: python3 tools/lint.py [--missing] [--warnings] [file...]

Errors (check.py and the build fail on these):
  source       source-language characters (kana, kanji) left in the English (not in a block with
               a `# keep: why` comment - text kept as the original on purpose, e.g. staff credits)
  codes        control codes in the source missing from the English, or extra ones (CODE)
  lines        more lines than a block file's `# limit lines=N`
  chars        a line longer than `# limit chars=N` (characters; pixel widths need the game's
               own layout check)
  bytes        English longer than a fixed table string's max_bytes (refs == 0), as encoded by
               encoded_length() - adjust it to how the build stores English
Warnings (shown with --warnings; counted by status.py):
  glossary     the source contains a glossary term but the English doesn't use its translation
               (translation/glossary.csv: japanese, english, notes; several accepted English forms
               separated by ' | '; put [glossary-ok] in a block comment or row note to silence)
  spacing      trailing spaces or double spaces in the English (leading spaces are left alone:
               continuation lines are often indented)
--missing also lists untranslated entries (status.py counts them).
"""
import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402
import textdb  # noqa: E402

SOURCE_CHARS = re.compile(r'[぀-ヿ㐀-䶿一-鿿ｦ-ﾟ]')
CODE = re.compile(r'\{[^{}]*\}')  # the game's control codes: {n} {t} {s3} {p8,32,} ... (tools/fpstext.py)

# Room in bytes of the fixed fields (wrestler and promotion tables), by column
ROOM = {'wrestlers.csv': {'name1': 13, 'name2': 19, 'nick': 23}, 'promotions.csv': {'long': 25, 'short': 13},
        'save_titles.csv': {'japanese': 10}}


def encoded_length(text):
    """Bytes the build stores for `text`: letters 1, space 1, codes as written, anything else 2."""
    import fpstext
    try:
        return len(fpstext.encode(text))
    except ValueError:
        return 999


MAX_GLYPHS = 46       # glyphs one text slot record holds (0x06070BB0, 0xDE bytes): the 47th stops the game (seen 2026-10-27)
_ROOMS = None


def rooms():
    """{id: (count, px, screen)} from translation/text/rooms.csv (the kit's format; count = glyphs,
    measured with tools/slots.py or the kit's testing/drive.py and tools/probe.py)."""
    global _ROOMS
    if _ROOMS is None:
        _ROOMS = {}
        p = paths.TEXT / 'rooms.csv'
        if p.exists():
            with open(p, encoding='utf-8', newline='') as f:
                for r in csv.DictReader(ln for ln in f if not ln.startswith('#')):
                    _ROOMS[r['id']] = (int(r['count']) if r.get('count') else None,
                                       int(r['px']) if r.get('px') else None, r.get('screen', ''))
    return _ROOMS


def room_for(e):
    """The rooms.csv row for an entry: its block id, a range holding it, or its table column."""
    rel = f'{e.file.parent.name}/{e.file.name}'
    if f'{rel}|{e.key}' in rooms():
        return rooms()[f'{rel}|{e.key}']
    if e.file.suffix == '.csv':
        col = e.key.partition(':')[2] or textdb.SOURCE_COLUMN
        if f'{e.file.name}:{col}' in rooms():
            return rooms()[f'{e.file.name}:{col}']
    m = re.match(r'(\w+):([0-9A-Fa-f]+)$', e.key)
    if m:
        for k, v in rooms().items():
            r = re.match(rf'{re.escape(rel)}\|(\w+):([0-9A-Fa-f]+)-([0-9A-Fa-f]+)$', k)
            if r and r.group(1) == m.group(1) and int(r.group(2), 16) <= int(m.group(2), 16) <= int(r.group(3), 16):
                return v
    return None


def game_checks(e):
    """This game's own checks: name tokens, encodable English, interview lines and widths (both name
    builds), fixed field room."""
    import fpstext
    import names
    out = []
    try:
        variants = [names.resolve(e.english, v) for v in ('real', 'parody')]
        for en in variants:
            fpstext.encode(en)
    except ValueError as x:
        return [('error', 'chars', str(x))]
    gone = fpstext.missing_glyphs(variants[0])
    if gone:
        out.append(('error', 'chars', f'not in the font: {"".join(sorted(set(gone)))}'))
    lines = e.english.split('\n')
    if e.file.parent.name == 'script':
        if len(lines) > e.source.count('\n') + 1:
            out.append(('error', 'lines', f'{len(lines)} EN lines for {e.source.count(chr(10)) + 1} JP lines'))
    if 'px' in e.limits:
        for en in variants:
            for ln in en.split('\n'):
                w = fpstext.line_widths(ln)[0]
                if w > e.limits['px']:
                    out.append(('error', 'px', f'{w} px, limit {e.limits["px"]}: {ln!r}'))
    strings = lines if e.file.parent.name == 'script' else [e.english]
    for en in variants:                    # one text object holds at most 47 glyphs (48 per slot
        parts = en.split('\n') if e.file.parent.name == 'script' else [en]   # record): more hangs
        n = max(fpstext.glyph_count(t) for t in parts)
        if n > MAX_GLYPHS:
            out.append(('error', 'glyphs', f'{n} glyphs in one string: the game stops past {MAX_GLYPHS} '
                        '(0x06021C54 error 3)'))
            break
    col = e.key.partition(':')[2]
    slot = room_for(e)                     # (glyphs, px, screen)
    if slot:
        if e.file.name == 'wrestlers.csv':            # both builds' short names: real and parody columns
            with open(e.file, encoding='utf-8') as f:
                lines = f.read().split('\n')
            row = next(csv.DictReader([ln for ln in lines if ln.startswith('idx,')] + [lines[e.line - 1]]))
            variants = [row['en_' + col], row['parody_' + col]]
        n = max(map(fpstext.glyph_count, variants))
        if slot[0] is not None and n > slot[0]:
            out.append(('error', 'glyphs', f'{n} glyphs, its text slot holds {slot[0]} ({slot[2]})'))
        w = max(fpstext.line_widths(v)[0] for v in variants)
        if slot[1] and w > slot[1]:
            out.append(('error', 'px', f'{w} px, room for {slot[1]} ({slot[2]})'))
    room = ROOM.get(e.file.name, {}).get(col)
    if room and max(map(encoded_length, variants)) > room:
        out.append(('error', 'bytes', f'{max(map(encoded_length, variants))} bytes, room for {room} ({col})'))
    return out


def glossary():
    if not paths.GLOSSARY.exists():
        return []
    with open(paths.GLOSSARY, encoding='utf-8', newline='') as f:
        return [(r['japanese'].strip(), [e.strip() for e in r['english'].split(' | ') if e.strip()])
                for r in csv.DictReader(f) if (r.get('japanese') or '').strip() and (r.get('english') or '').strip()]


PEN_MOVE = re.compile(r'\{[xy]-?\d+,\}')


def check_entry(e, terms):
    """[(severity, kind, message)] for one entry."""
    out = []
    en = e.english
    if not en:
        return out
    m = SOURCE_CHARS.search(en)
    if m and '# keep:' not in (e.notes or ''):     # `# keep:` = left as the original on purpose
        out.append(('error', 'source', f'source-language text left in the English: {m.group()!r}'))
    a, b = Counter(CODE.findall(e.source)), Counter(CODE.findall(en))
    if '# layout:' in (e.notes or ''):     # deliberate English spacing: pen moves may differ
        a, b = (Counter({k: v for k, v in c.items() if not PEN_MOVE.match(k)}) for c in (a, b))
    if a != b:
        miss, extra = list((a - b).elements()), list((b - a).elements())
        out.append(('error', 'codes', 'control codes ' + '; '.join(
            x for x in (f'missing {miss}' if miss else '', f'extra {extra}' if extra else '') if x)))
    lines = en.split('\n')
    if 'lines' in e.limits and len(lines) > e.limits['lines']:
        out.append(('error', 'lines', f'{len(lines)} lines, limit {e.limits["lines"]}'))
    if 'chars' in e.limits:
        for ln in lines:
            plain = CODE.sub('', ln)
            if len(plain) > e.limits['chars']:
                out.append(('error', 'chars', f'{len(plain)} characters, limit {e.limits["chars"]}: {ln!r}'))
    if 'max_bytes' in e.limits and e.limits.get('refs', 0) == 0 and encoded_length(en) > e.limits['max_bytes']:
        out.append(('error', 'bytes', f'{encoded_length(en)} bytes, room for {e.limits["max_bytes"]} (fixed string)'))
    out += game_checks(e)
    if any(ln != ln.rstrip() or '  ' in ln.strip() for ln in lines) and e.file.name != 'wrestlers.csv':
        out.append(('warning', 'spacing', f'trailing or double spaces: {en!r}'))
    for jp, accepted in terms:
        if jp in e.source and not any(x.lower() in en.lower() for x in accepted):
            out.append(('warning', 'glossary', f'{jp} should be "{" | ".join(accepted)}"'))
    return out


def run(files=None, missing=False):
    """{'error': n, 'warning': n, 'missing': n, 'total': n} plus the printed lines."""
    terms = glossary()
    ents = []
    for p in files or textdb.text_files():
        ents += textdb.read_file(p)
    report, counts = [], Counter()
    for e in ents:
        counts['total'] += 1
        if not e.english:
            counts['missing'] += 1
            if missing:
                report.append(('missing', e, 'no English yet'))
            continue
        name_table = e.file.name in ('wrestlers.csv', 'promotions.csv')    # the names themselves
        for sev, kind, msg in check_entry(e, [] if '[glossary-ok]' in e.notes or name_table else terms):
            counts[sev] += 1
            report.append((sev, e, f'{kind}: {msg}'))
    return counts, report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], epilog=paths.FOLDER_HELP,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('files', nargs='*', type=Path, help='only these text files (default: all)')
    ap.add_argument('--missing', action='store_true', help='also list untranslated entries')
    ap.add_argument('--warnings', action='store_true', help='also list warnings')
    args = ap.parse_args(paths.configure(sys.argv[1:] if argv is None else argv))
    counts, report = run(args.files or None, args.missing)
    for sev, e, msg in report:
        if sev == 'warning' and not args.warnings:
            continue
        print(f'{e.where}: {"! " if sev == "error" else ""}{msg}')
    print(f'{counts["total"]} entries, {counts["total"] - counts["missing"]} translated: '
          f'{counts["error"]} error(s), {counts["warning"]} warning(s)'
          + ('' if args.warnings or not counts['warning'] else ' (--warnings to list them)'))
    return 1 if counts['error'] else 0


if __name__ == '__main__':
    sys.exit(main())
