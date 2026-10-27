#!/usr/bin/env python3
"""Build the translated image from the original. Standard library only.

  python3 build.py [--name NAME] [--unlocks all|none|GROUP,...] [--clean]
      -> build/NAME.<ext> (default NAME: "<game> (English)")

Steps (default folders shown; move any of them with the folder options - see --help):
  1. verify the original in rom/ (size + SHA-1; --skip-verify skips the hash)
  2. prepare build/NAME: a fresh copy of the original, or - much faster for big images - the last
     build with every range it wrote restored from the original (tools/image.py; --clean copies)
  3. text: translation/script/ and translation/text/ into the game's files (TEXT_STEPS)
  4. code patches picked by --unlocks (CODE_PATCHES, tools/codepatch.py; debug-* groups only when named)
  5. images: for every catalogued image the English file the catalogue picks (hand-made >
     approved > rendered), imported by tools/gfx.py; the final set is copied to review/images-english/
  6. write every changed file back into the image (files that fit in place first)

Wrestler names: --names real (default) or parody - the two English releases. Text steps that hold
names read NAMES (set from --names) to pick the column.

Test builds: --boot PART starts the game straight in PART (BOOT_PATCHES, once known);
--no-translation skips text and images, and gameplay patches unless --unlocks is given - on its
own the result is byte-identical to the original (tools/check.py --control proves it).
Developer flags (never for releases): --no-text FILE skips one text file.
"""
import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'tools'))
import catalog  # noqa: E402
import codepatch  # noqa: E402
import disc  # noqa: E402
import gfx  # noqa: E402
import image  # noqa: E402
import paths  # noqa: E402
import textins  # noqa: E402

# Gameplay patches: (group, file, address, original, new, description) - see tools/codepatch.py.
# Groups named debug-* are developer extras (debug menus, cheat windows): never in "all" or the
# default, only when named, never in a release variant.
# SH-2 code is big-endian: original and new are bytes. Found by 32bits (docs/HIDDEN_CONTENT.md).
CODE_PATCHES = [
    # --- unlock: everything a full game clear unlocks, from the start (released: "(Unlocked)") ---
    # The game-clear flag (save byte 0x00212B49, RAM copy 0x060682E8; set when both Victory Road
    # singles titles have champions) is tested in seven places; each `mov.b @rN,r1` that loads it
    # becomes `mov #1,r1`, so the game behaves as after a clear without changing the save.
    ('unlock', '/1ST.BIN', 0x0601C09E, bytes.fromhex('6110'), bytes.fromhex('e101'), 'hidden roster wrestlers listed'),
    ('unlock', '/1ST.BIN', 0x0601B82C, bytes.fromhex('6110'), bytes.fromhex('e101'), 'hidden wrestler groups'),
    ('unlock', '/2ND.BIN', 0x0608E430, bytes.fromhex('6110'), bytes.fromhex('e101'), 'Music Test range 2-36'),
    ('unlock', '/2ND.BIN', 0x06081F18, bytes.fromhex('6110'), bytes.fromhex('e101'), 'One Night Match players (1)'),
    ('unlock', '/2ND.BIN', 0x06082494, bytes.fromhex('6110'), bytes.fromhex('e101'), 'One Night Match players (2)'),
    ('unlock', '/2ND.BIN', 0x0608F02A, bytes.fromhex('6110'), bytes.fromhex('e101'), 'Edit points 200 (entry)'),
    ('unlock', '/2ND.BIN', 0x0608F60C, bytes.fromhex('012c'), bytes.fromhex('e101'), 'Edit points 200 (reload)'),
    # Wrestler Edit's point pool (+0x170 of the edit wrestler) is 255 only when all five title
    # records are set (2ND 0x0608F028 on entry, 0x0608F602 on reload); the skip after each
    # "all five held?" loop becomes a no-op, so the pool is always 255.
    ('unlock', '/2ND.BIN', 0x0608F058, bytes.fromhex('8902'), bytes.fromhex('0009'), 'Edit points 255 (entry)'),
    ('unlock', '/2ND.BIN', 0x0608F63E, bytes.fromhex('a086'), bytes.fromhex('0009'), 'Edit points 255 (reload)'),
    # Wrestler Edit's base-character list (Appearance, Face) ends at the count byte 0x060C4E0A
    # (204); a fixed 213 also lists the hidden presets 204-212 - the preset tables hold exactly
    # 160-212, so 213+ (32bits used 232) read other data as colours and labels.
    ('unlock', '/2ND.BIN', 0x060B2C2C, bytes.fromhex('6220'), bytes.fromhex('e2d5'), 'hidden presets in Wrestler Edit'),
    # Wrestler Edit's Theme field (field 27) runs 11-34 (u16 min/max at 0x060BF8FE/0x060BF900);
    # 37 is the secret G Gundam theme (FPS.STR streams 40-41), otherwise only in the debug
    # sound test (35 and 36 are also unused by the roster).
    ('unlock', '/2ND.BIN', 0x060BF900, bytes.fromhex('0022'), bytes.fromhex('0025'), 'Edit theme field reaches 37 (G Gundam theme)'),
    # --- developer options (debug-*: build options only, never released) ---
    # The boot code stores 0 to the mode value 0x0605629C (the game); with 1, 2ND.BIN returns at
    # once and 1ST.BIN shows PROCESS SELECT (HARAKI_PROCESS leads to the normal Mode Select).
    ('debug-menu', '/1ST.BIN', 0x06024E28, bytes.fromhex('e100'), bytes.fromhex('e101'), 'boot into the debug menu'),
    # The developers' in-match monitor 1ST 0x06016398 is never called. The paused-match loop's
    # call (pool word 0x0600A430 -> 0x06027D44) goes through a hook in the unused helper at
    # 0x060242B4: call the monitor, then the original. Pause, R = page, L = wrestler in focus.
    ('debug-monitor', '/1ST.BIN', 0x060242B4,
     bytes.fromhex('2f862f962fa62fe64f226ef36853d91b6143218b21188d076a63972b'),
     bytes.fromhex('4f22d004400b0009d003400b00094f26000b00090601639806027d44'), 'monitor hook'),
    ('debug-monitor', '/1ST.BIN', 0x0600A430, bytes.fromhex('06027d44'), bytes.fromhex('060242b4'),
     'paused loop calls the monitor hook'),
]
UNLOCK_GROUPS =sorted({p[0] for p in CODE_PATCHES})
PLAYER_GROUPS = [g for g in UNLOCK_GROUPS if not g.startswith('debug-')]

# --boot: (part, file, address, original, new) - patches that start the game in a given part.
BOOT_PATCHES = {
}


def to_offset(name, addr):
    """File offset of a RAM address: 1ST.BIN loads at 0x06004000, the overlays at 0x06080000."""
    base = {'1ST.BIN': 0x06004000, '2ND.BIN': 0x06080000, '3RD.BIN': 0x06080000}[name.lstrip('/')]
    return addr - base


# Wrestler names: 'real' (the real wrestlers each character stands for) or 'parody' (the game's own
# names, romanized). Set by --names before the text steps run.
NAME_SETS = ('real', 'parody')
NAMES = 'real'

# Text steps: (text file or folder under translation/, function(path, files)). Each inserts the
# English into the game's files through `files` and stops with a clear message if anything doesn't fit.
# Zero-padding files a grown file may take room from when the disc is full (PS2 disc.py
# take_from_padding: their end is cut off) - e.g. ['/DUMMY.DAT']; check they are all zeros.
PADDING_DONORS = []

TEXT_STEPS = [   # tools/textins.py: single-byte letters, repointed strings, name records, move names
    ('text/messages.txt', lambda path, files: textins.step_1st(files, NAMES)),
    ('text/menus.txt', lambda path, files: textins.step_2nd(files, NAMES)),
]


class Files:
    """The game's files for this build: read from the image on first use, written back at the end."""

    def __init__(self, d):
        self.d, self.data, self.changed = d, {}, set()

    def get(self, name):
        if name not in self.data:
            self.data[name] = bytearray(self.d.read_file(self.d.find(name)))
        return self.data[name]

    def put(self, name, data):
        self.data[name] = bytearray(data)
        self.changed.add(name)


def unlock_groups(value):
    if value == 'all':
        return set(PLAYER_GROUPS)
    if value == 'none':
        return set()
    groups = {g.strip() for g in value.split(',') if g.strip()}
    if groups - set(UNLOCK_GROUPS):
        raise argparse.ArgumentTypeError(f'expected all, none or some of {",".join(UNLOCK_GROUPS) or "(no groups yet)"}')
    return groups


def images_step(files):
    final = catalog.final_images()
    missing, changed, _ = catalog.stale()
    if missing or changed:
        print(f'note: {len(missing) + len(changed)} automatic renders are out of date - run tools/render.py '
              f'(building with the frozen files there are)')
    n = gfx.import_images({k: p for k, (tag, p) in final.items()}, files)
    if paths.ENGLISH_IMAGES.exists():
        shutil.rmtree(paths.ENGLISH_IMAGES)
    if final:
        paths.ENGLISH_IMAGES.mkdir(parents=True)
        for name, (tag, p) in final.items():
            shutil.copyfile(p, paths.ENGLISH_IMAGES / f'{name}.png')
        counts = {}
        for tag, _ in final.values():
            counts[tag] = counts.get(tag, 0) + 1
        print(f'images: {n} imported (' + ', '.join(f'{c} {t}' for t, c in sorted(counts.items())) + ')')


def verify_original(original):
    """SHA-1 of the original image, once: the result is remembered with the file's size and
    modification time (build/original.verified), so later builds only re-hash a changed file
    (a DVD image takes ~20 s to hash)."""
    st = original.stat()
    stamp = f'{original.resolve()} {st.st_size} {st.st_mtime_ns} {paths.ORIGINAL["sha1"]}'
    memo = paths.BUILD / 'original.verified'
    if memo.exists() and memo.read_text() == stamp:
        return
    print('verifying the original...')
    if image.sha1(original) != paths.ORIGINAL['sha1']:
        sys.exit(f'{original.name} does not match the expected SHA-1 {paths.ORIGINAL["sha1"]}')
    paths.BUILD.mkdir(parents=True, exist_ok=True)
    memo.write_text(stamp)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], epilog=paths.FOLDER_HELP,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--name', default=f'{paths.GAME_FILE} (English)')
    ap.add_argument('--skip-verify', action='store_true', help="don't hash the original image")
    ap.add_argument('--clean', action='store_true', help='copy the original instead of restoring the last build')
    ap.add_argument('--no-translation', action='store_true', help='skip text and images (alone: identical to the original)')
    ap.add_argument('--unlocks', type=unlock_groups, metavar='all|none|GROUP,...',
                    help='gameplay patches: all (default; debug-* groups only when named), none or some groups; '
                         'none with --no-translation')
    ap.add_argument('--names', choices=NAME_SETS, default='real',
                    help="wrestler names: real (default) or the game's parody names")
    ap.add_argument('--boot', choices=sorted(BOOT_PATCHES), help='TEST BUILD: start the game in this part')
    ap.add_argument('--no-text', action='append', default=[], metavar='FILE',
                    help='developer: leave this text file untranslated (repeatable)')
    args = ap.parse_args(paths.configure(sys.argv[1:] if argv is None else argv))
    global NAMES
    NAMES = args.names
    if args.unlocks is None:
        args.unlocks = set() if args.no_translation else set(PLAYER_GROUPS)

    original = paths.ROM
    if not original.exists():
        sys.exit(f'put the original image in {paths.show(paths.ROM_DIR)} (or pass --rom): {paths.ORIGINAL_NAME}')
    if original.stat().st_size != paths.ORIGINAL['size']:
        sys.exit(f'{original.name}: {original.stat().st_size} bytes, expected {paths.ORIGINAL["size"]} - not the right image')
    if not args.skip_verify:
        verify_original(original)

    out = paths.BUILD / (args.name + original.suffix)
    with image.prepare(original, out, clean=args.clean) as f:
        d = disc.Disc(f, writable=True)
        files = Files(d)

        if not args.no_translation:
            for rel, step in TEXT_STEPS:
                if rel in args.no_text:
                    print(f'text: skipped {rel} (--no-text)')
                    continue
                step(paths.TRANSLATION / rel, files)

        codepatch.apply(files, CODE_PATCHES, args.unlocks, to_offset)

        if not args.no_translation:
            images_step(files)

        if args.boot:
            codepatch.apply(files, [(args.boot, *p, f'TEST BUILD: boots into {args.boot}') for p in BOOT_PATCHES[args.boot]],
                            {args.boot}, to_offset)

        def fits(name):
            return (len(files.data[name]) + disc.SECTOR - 1) // disc.SECTOR <= d.allocated_sectors(d.find(name))
        for name in sorted(files.changed, key=lambda n: (not fits(n), n)):  # fixed order: same disc layout every build
            d.write_file(d.find(name), bytes(files.data[name]), relocate=True,
                         **({'donors': PADDING_DONORS} if PADDING_DONORS else {}))
            print(f'patched {name}')
    disc.companion_files(out, original)
    print(f'done: {paths.show(out)}  ({len(files.changed)} files patched)')
    return out


if __name__ == '__main__':
    main()
