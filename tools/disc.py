#!/usr/bin/env python3
"""Sega Saturn disc image (platform pack saturn): the MODE1/2352 data track of a BIN/CUE with ISO9660.

  disc.py list    <bin>
  disc.py extract <bin> <outdir>
  disc.py inject  <bin> <iso_path> <file>   overwrite a file in place (must fit in its allocated sectors)
  disc.py verify  <bin> [iso_path...]       check EDC/ECC (of the given files, or every sector - slow)
  disc.py header  <bin>                     the system ID (IP.BIN): product number, version, date, area, title
  disc.py tracks  <cue>                     the tracks of a cue sheet

The image the project works on is the data track (Track 1); audio tracks are separate BIN files
that are never changed - companion_files() copies them next to a build and writes the .cue.
Sectors 0-15 hold IP.BIN (the system ID and the boot code the BIOS checks): never written here.
The PVD's volume size counts the whole disc, audio tracks included, so it is larger than the data
track: sizes come from the BIN file, not the PVD.

Writing regenerates EDC/ECC for every written sector and updates the directory record (size, and
LBA when a file that outgrew its slot is relocated into free sectors - or, on a packed disc, to
new sectors appended at the end of the data track). Saturn games usually open
files by name through the SBL/SGL file system (GFS), which reads the directory once at boot; some
address files by LBA or by their index in the directory - check before relocating anything.

Interface shared by every platform's disc.py (build.py and extract.py use only this):
  SECTOR                        data bytes per sector
  Disc(path or file, writable)  .files(), .find(path), .read_file(e), .write_file(e, data, relocate),
                                .allocated_sectors(e), .is_empty(e), .extract_file(e, out), .close()
  companion_files(image, original)  write what an emulator needs next to the image (the .cue, audio tracks)
"""
import re
import shutil
import struct
import sys
from pathlib import Path

RAW = 2352
SECTOR = USER = 2048
DATA = 16        # user data offset in a MODE1 sector

# ---------------------------------------------------------------- EDC / ECC

EDC_LUT = []
for i in range(256):
    e = i
    for _ in range(8):
        e = (e >> 1) ^ (0xD8018001 if e & 1 else 0)
    EDC_LUT.append(e)

ECC_F = [0] * 256
ECC_B = [0] * 256
for i in range(256):
    j = (i << 1) ^ (0x11D if i & 0x80 else 0)
    ECC_F[i] = j
    ECC_B[i ^ j] = i


def edc(data):
    e = 0
    for b in data:
        e = (e >> 8) ^ EDC_LUT[(e ^ b) & 0xFF]
    return e


def _ecc_block(src, major_count, minor_count, major_mult, minor_inc):
    size = major_count * minor_count
    out = bytearray(major_count * 2)
    for major in range(major_count):
        index = (major >> 1) * major_mult + (major & 1)
        a = b = 0
        for _ in range(minor_count):
            t = src[index]
            index += minor_inc
            if index >= size:
                index -= size
            a ^= t
            b ^= t
            a = ECC_F[a]
        a = ECC_B[ECC_F[a] ^ b]
        out[major] = a
        out[major + major_count] = a ^ b
    return out


def fix_sector(sec):
    """Recompute EDC and ECC of a mode 1 sector in place (the header is part of both)."""
    struct.pack_into('<I', sec, 0x810, edc(sec[0:0x810]))
    sec[0x814:0x81C] = bytes(8)
    sec[0x81C:0x8C8] = _ecc_block(memoryview(sec)[0xC:], 86, 24, 2, 86)
    sec[0x8C8:0x930] = _ecc_block(memoryview(sec)[0xC:], 52, 43, 86, 88)


# ---------------------------------------------------------------- cue sheets

def cue_tracks(cue):
    """[(file name, track number, mode)] of a cue sheet, in order."""
    out, cur = [], None
    for line in Path(cue).read_text(errors='replace').splitlines():
        m = re.match(r'\s*FILE\s+"(.*)"\s+\w+', line) or re.match(r'\s*FILE\s+(\S+)\s+\w+', line)
        if m:
            cur = m.group(1)
            continue
        m = re.match(r'\s*TRACK\s+(\d+)\s+(\S+)', line)
        if m:
            out.append((cur, int(m.group(1)), m.group(2).upper()))
    return out


def find_cue(image):
    """The .cue next to `image` that names it, or None."""
    image = Path(image)
    for cue in sorted(image.parent.glob('*.cue')):
        if any(f == image.name for f, _, _ in cue_tracks(cue)):
            return cue
    return None


# ---------------------------------------------------------------- ISO9660

class Entry:
    def __init__(self, path, lba, size, is_dir, rec_sector, rec_offset):
        self.path, self.lba, self.size, self.is_dir = path, lba, size, is_dir
        self.rec_sector, self.rec_offset = rec_sector, rec_offset  # where the dir record lives

    @property
    def sectors(self):
        return (self.size + USER - 1) // USER


class Disc:
    def __init__(self, path, writable=False):
        self.own = not hasattr(path, 'read')
        self.f = open(path, 'r+b' if writable else 'rb') if self.own else path
        self.f.seek(0, 2)
        self.total_sectors = self.f.tell() // RAW
        self.entries = []
        assert self.read_raw(16)[15] == 1, 'not a MODE1/2352 data track'
        pvd = self.read_user(16)
        assert pvd[1:6] == b'CD001', 'no ISO9660 PVD'
        root = pvd[156:190]
        self._walk(struct.unpack('<I', root[2:6])[0], struct.unpack('<I', root[10:14])[0], '/')
        self.entries.sort(key=lambda e: e.lba)

    def close(self):
        if self.own:
            self.f.close()

    def read_raw(self, lba):
        self.f.seek(lba * RAW)
        return bytearray(self.f.read(RAW))

    def write_raw(self, lba, sec):
        self.f.seek(lba * RAW)
        self.f.write(sec)

    def read_user(self, lba):
        return bytes(self.read_raw(lba)[DATA:DATA + USER])

    def header(self):
        """The system ID at the start of IP.BIN (sector 0)."""
        s = self.read_user(0)
        text = lambda a, b: s[a:b].decode('ascii', 'replace').strip()
        return {'hardware': text(0, 16), 'maker': text(16, 32), 'product': text(32, 42), 'version': text(42, 48),
                'date': text(48, 56), 'device': text(56, 64), 'area': text(64, 74), 'peripherals': text(80, 96),
                'title': text(96, 208), 'ip_size': struct.unpack('>I', s[0xE0:0xE4])[0],
                'first_read': f"{struct.unpack('>I', s[0xF0:0xF4])[0]:#010x}"}

    def _walk(self, lba, size, path):
        for s in range((size + USER - 1) // USER):
            data = self.read_user(lba + s)
            i = 0
            while i < USER:
                ln = data[i]
                if ln == 0:
                    break
                r = data[i:i + ln]
                name = r[33:33 + r[32]]
                if name not in (b'\0', b'\1'):
                    e = Entry(path + name.decode('ascii').split(';')[0],
                              struct.unpack('<I', r[2:6])[0], struct.unpack('<I', r[10:14])[0],
                              bool(r[25] & 2), lba + s, i)
                    self.entries.append(e)
                    if e.is_dir:
                        self._walk(e.lba, e.size, e.path + '/')
                i += ln

    def files(self):
        return [e for e in self.entries if not e.is_dir]

    def find(self, path):
        path = '/' + path.lstrip('/')
        for e in self.entries:
            if e.path.upper() == path.upper():
                return e
        raise KeyError(path)

    def allocated_sectors(self, e):
        """Sectors available before the next thing on disc (or the end of the data track)."""
        later = [x.lba for x in self.entries if x.lba > e.lba]
        nxt = min(later) if later else self.total_sectors
        return nxt - e.lba

    def read_file(self, e):
        out = bytearray()
        for s in range(e.sectors):
            out += self.read_user(e.lba + s)
        return bytes(out[:e.size])

    def is_empty(self, e, samples=64):
        """True if the file looks like zero padding (checks up to `samples` spread-out sectors)."""
        step = max(1, e.sectors // samples)
        return e.size > 0 and not any(any(self.read_user(e.lba + s)) for s in range(0, e.sectors, step))

    def extract_file(self, e, out):
        Path(out).write_bytes(self.read_file(e))

    def find_free(self, need, start=24):
        """First run of `need` empty sectors not used by any file or directory."""
        used = sorted((x.lba, x.lba + max(x.sectors, 1)) for x in self.entries)
        cur = start
        for a, b in used + [(self.total_sectors, self.total_sectors)]:
            while a - cur >= need:
                busy = next((l for l in range(cur, cur + need) if any(self.read_user(l))), None)
                if busy is None:
                    return cur
                cur = busy + 1
            cur = max(cur, b)
        return None

    def append_sectors(self, n):
        """Add n empty MODE1 sectors (sync, header, zero data, EDC/ECC) at the end of the track."""
        for lba in range(self.total_sectors, self.total_sectors + n):
            sec = bytearray(RAW)
            sec[0:12] = b'\x00' + b'\xff' * 10 + b'\x00'
            m, rest = divmod(lba + 150, 75 * 60)
            sec_, frame = divmod(rest, 75)
            sec[12:16] = bytes(int(str(v), 16) for v in (m, sec_, frame)) + b'\x01'
            fix_sector(sec)
            self.write_raw(lba, sec)
        self.total_sectors += n

    def _patch_record(self, e, offset, value):
        """Write a both-endian 32-bit field of e's directory record."""
        sec = self.read_raw(e.rec_sector)
        o = DATA + e.rec_offset
        struct.pack_into('<I', sec, o + offset, value)
        struct.pack_into('>I', sec, o + offset + 4, value)
        fix_sector(sec)
        self.write_raw(e.rec_sector, sec)

    def write_file(self, e, data, relocate=False):
        need = (len(data) + USER - 1) // USER
        avail = self.allocated_sectors(e)
        if need > avail:
            if not relocate:
                raise ValueError(f'{e.path}: {len(data)} bytes needs {need} sectors, only {avail} available')
            new = self.find_free(need)
            if new is None:          # a packed disc: grow the data track (the audio tracks are separate files)
                new = self.total_sectors
                self.append_sectors(need)
            print(f'  relocating {e.path}: LBA {e.lba} -> {new} ({need} sectors)')
            e.lba = new
            self._patch_record(e, 2, new)
        for s in range(need):
            sec = self.read_raw(e.lba + s)
            sec[DATA:DATA + USER] = data[s * USER:(s + 1) * USER].ljust(USER, b'\0')
            fix_sector(sec)
            self.write_raw(e.lba + s, sec)
        self._patch_record(e, 10, len(data))
        e.size = len(data)


def companion_files(image, original=None):
    """The .cue an emulator loads, next to the image, and copies of the original's other tracks
    (audio is never changed). Without the original's cue: a one-track cue."""
    image = Path(image)
    cue = find_cue(original) if original else None
    if cue is None:
        image.with_suffix('.cue').write_text(f'FILE "{image.name}" BINARY\n  TRACK 01 MODE1/2352\n    INDEX 01 00:00:00\n')
        return
    lines = []
    for line in cue.read_text(errors='replace').splitlines():
        m = re.match(r'(\s*FILE\s+)"?(.*?)"?(\s+\w+\s*)$', line)
        if m and m.group(2) == Path(original).name:
            line = f'{m.group(1)}"{image.name}"{m.group(3)}'
        elif m:
            src = cue.parent / m.group(2)
            num = re.search(r'\(Track (\d+)\)', m.group(2))
            name = f'{image.stem} (Track {num.group(1)}){src.suffix}' if num else f'{image.stem} - {src.name}'
            dst = image.parent / name
            if not dst.exists() or dst.stat().st_size != src.stat().st_size:
                shutil.copyfile(src, dst)
            line = f'{m.group(1)}"{name}"{m.group(3)}'
        lines.append(line)
    image.with_suffix('.cue').write_text('\n'.join(lines) + '\n')


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    cmd = argv[0]
    if cmd == 'list':
        d = Disc(argv[1])
        for e in d.files():
            print(f'{e.lba:7d} {e.size:10d} {d.allocated_sectors(e):6d}  {e.path}')
    elif cmd == 'header':
        for k, v in Disc(argv[1]).header().items():
            print(f'{k:12} {v}')
    elif cmd == 'tracks':
        for f, n, mode in cue_tracks(argv[1]):
            print(f'{n:2d} {mode:12} {f}')
    elif cmd == 'extract':
        d = Disc(argv[1])
        out = Path(argv[2])
        for e in d.files():
            p = out / e.path.lstrip('/')
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(d.read_file(e))
            print('extracted', e.path)
    elif cmd == 'inject':
        d = Disc(argv[1], writable=True)
        e = d.find(argv[2])
        data = Path(argv[3]).read_bytes()
        d.write_file(e, data)
        print(f'injected {argv[3]} -> {e.path} ({len(data)} bytes)')
    elif cmd == 'verify':
        d = Disc(argv[1])
        bad = 0
        if len(argv) > 2:
            lbas = [lba for p in argv[2:] for e in [d.find(p)] for lba in range(e.lba, e.lba + e.sectors)]
        else:
            lbas = range(d.total_sectors)
        for lba in lbas:
            sec = d.read_raw(lba)
            if sec[15] != 1:
                continue
            ref = bytearray(sec)
            fix_sector(ref)
            if ref != sec:
                bad += 1
                if bad <= 10:
                    print('bad sector', lba)
        print('bad sectors:', bad)
        return 1 if bad else 0
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
