"""
NDS ROM rebuilder — the write side of the pipeline.

Takes an original ROM plus a set of replacement file contents, and emits a new
ROM. **Never writes to the input.** The original is opened read-only and all work
happens on an in-memory copy.

Layout rules, confirmed against this game's ROM (see REVERSE_ENGINEERING_LOG.md):
  * every file in the NitroROM FAT starts on a **512-byte boundary**;
  * the space between a file's end and the next boundary is padded with **0xFF**;
  * header field 0x80 (`total_used_rom_size`) equals the end offset of the last
    file;
  * the header CRC16 at 0x15E is **CRC-16/MODBUS over bytes 0x000..0x15D**
    (verified: recomputing it reproduces the stored 0xE370 for the EU ROM).

The guarantee this module is built around: **a rebuild with no replacements must
reproduce the input byte-for-byte.** `verify_noop()` asserts exactly that, and
should be run before trusting any real edit.

Usage:
    py rom_build.py <rom.nds> --verify
    py rom_build.py <rom.nds> --replace <path-in-rom>=<file> [...] --out <new.nds>
"""
import os
import struct
import sys

SECTOR = 512
PAD = 0xFF


def crc16_modbus(buf) -> int:
    crc = 0xFFFF
    for b in buf:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def align_up(n, a=SECTOR):
    return (n + a - 1) // a * a


class Rom:
    def __init__(self, data: bytes):
        self.data = bytes(data)
        h = {}
        (h['arm9_rom_offset'], h['arm9_entry'], h['arm9_ram'], h['arm9_size']) = struct.unpack_from('<IIII', data, 0x20)
        (h['arm7_rom_offset'], h['arm7_entry'], h['arm7_ram'], h['arm7_size']) = struct.unpack_from('<IIII', data, 0x30)
        (h['fnt_offset'], h['fnt_size']) = struct.unpack_from('<II', data, 0x40)
        (h['fat_offset'], h['fat_size']) = struct.unpack_from('<II', data, 0x48)
        (h['total_used_rom_size'],) = struct.unpack_from('<I', data, 0x80)
        self.header = h
        self.num_files = h['fat_size'] // 8
        self.fat = [struct.unpack_from('<II', data, h['fat_offset'] + i * 8)
                    for i in range(self.num_files)]
        self.paths = self._walk_fnt()

    def _walk_fnt(self):
        """file_id -> path, by walking the FNT directory tree."""
        d = self.data
        fnt = self.header['fnt_offset']
        paths = {}

        def walk(dir_id, prefix):
            base = fnt + (dir_id & 0xFFF) * 8
            subtable_off, first_file_id, _ = struct.unpack_from('<IHH', d, base)
            pos = fnt + subtable_off
            fid = first_file_id
            while True:
                tl = d[pos]
                pos += 1
                if tl == 0x00:
                    break
                if 0x01 <= tl <= 0x7F:
                    name = d[pos:pos + tl].decode('ascii', 'replace')
                    pos += tl
                    paths[fid] = prefix + name
                    fid += 1
                elif 0x81 <= tl <= 0xFF:
                    nl = tl & 0x7F
                    name = d[pos:pos + nl].decode('ascii', 'replace')
                    pos += nl
                    (sub,) = struct.unpack_from('<H', d, pos)
                    pos += 2
                    walk(sub, prefix + name + '/')
                else:
                    break

        walk(0xF000, '/')
        return paths

    def file_id(self, path):
        for fid, p in self.paths.items():
            if p == path:
                return fid
        raise KeyError(f"no such file in ROM: {path}")

    def file_bytes(self, fid):
        s, e = self.fat[fid]
        return self.data[s:e]

    def build(self, replacements=None):
        """Return (new_rom_bytes, report). `replacements` maps file_id -> bytes."""
        replacements = dict(replacements or {})
        region_start = min(s for s, e in self.fat)

        # Everything before the first file (header, ARM9, ARM7, FNT, FAT, banner)
        # is preserved verbatim; we only patch FAT entries and header fields in it.
        out = bytearray(self.data[:region_start])

        # Preserve the original physical ordering so an unchanged rebuild lands
        # every file back at its original offset.
        order = sorted(range(self.num_files), key=lambda i: self.fat[i][0])

        new_fat = [None] * self.num_files
        cursor = region_start
        changed = []
        for fid in order:
            content = replacements.get(fid)
            if content is None:
                content = self.file_bytes(fid)
            else:
                changed.append(fid)
            start = align_up(cursor)
            if len(out) < start:
                out.extend(bytes([PAD]) * (start - len(out)))
            out.extend(content)
            end = start + len(content)
            new_fat[fid] = (start, end)
            cursor = end

        total_used = cursor

        # Patch the FAT (it lives inside the preserved prefix).
        fat_off = self.header['fat_offset']
        for fid, (s, e) in enumerate(new_fat):
            struct.pack_into('<II', out, fat_off + fid * 8, s, e)

        struct.pack_into('<I', out, 0x80, total_used)

        # Pad the image out to the original total length (cartridge capacity),
        # but only if we still fit — a grown ROM may legitimately exceed it.
        if len(out) < len(self.data):
            out.extend(bytes([PAD]) * (len(self.data) - len(out)))

        # Header 0x14 is the device capacity as a shift: the chip holds 128 KiB << cap.
        # A ROM that outgrows it still runs, because DeSmuME raises the size itself and
        # says so ("The ROM header is invalid. The device size has been increased..."),
        # but that warning is alarming on every launch and real hardware is entitled to
        # refuse. Vanilla ships 128 MiB with only ~3.8 MB spare, and appending TLK
        # strings for randomized item descriptions is enough to cross it. The file is
        # not padded up to the new capacity — the declared chip size may exceed the
        # image, and padding would double the file for nothing.
        old_cap = out[0x14]
        cap = old_cap
        while (128 * 1024) << cap < len(out) and cap < 0x0F:
            cap += 1
        if cap != old_cap:
            out[0x14] = cap

        struct.pack_into('<H', out, 0x15E, crc16_modbus(out[0:0x15E]))

        report = {
            'files': self.num_files,
            'replaced': [(fid, self.paths.get(fid, '?'),
                          self.fat[fid][1] - self.fat[fid][0],
                          new_fat[fid][1] - new_fat[fid][0]) for fid in changed],
            'total_used_rom_size': total_used,
            'original_total_used': self.header['total_used_rom_size'],
            'image_size': len(out),
            'original_image_size': len(self.data),
            'device_capacity': (128 * 1024) << cap,
            'device_capacity_raised': cap != old_cap,
            'moved_files': sum(1 for i in range(self.num_files)
                               if new_fat[i][0] != self.fat[i][0]),
        }
        return bytes(out), report


def verify_noop(rom_path):
    with open(rom_path, 'rb') as f:
        original = f.read()
    rom = Rom(original)
    rebuilt, report = rom.build()
    ok = rebuilt == original
    print(f"files: {report['files']}  moved: {report['moved_files']}")
    print(f"image size: {report['image_size']} (original {report['original_image_size']})")
    if report.get('device_capacity_raised'):
        print(f"device capacity raised to {report['device_capacity']} "
              f"(the image outgrew the declared chip size)")
    print(f"total_used_rom_size: {report['total_used_rom_size']} "
          f"(original {report['original_total_used']})")
    print(f"NO-OP REBUILD BYTE-IDENTICAL: {ok}")
    if not ok:
        n = min(len(rebuilt), len(original))
        diffs = [i for i in range(n) if rebuilt[i] != original[i]]
        print(f"  byte differences: {len(diffs)}; first few at "
              f"{['0x%X' % d for d in diffs[:10]]}")
        if diffs:
            d = diffs[0]
            print(f"  at 0x{d:X}: original {original[d]:#04x} != rebuilt {rebuilt[d]:#04x}")
    return ok


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    rom_path = sys.argv[1]
    if '--verify' in sys.argv:
        sys.exit(0 if verify_noop(rom_path) else 1)

    with open(rom_path, 'rb') as f:
        rom = Rom(f.read())
    replacements = {}
    args = sys.argv[2:]
    out_path = None
    i = 0
    while i < len(args):
        if args[i] == '--replace':
            spec = args[i + 1]
            in_rom, local = spec.split('=', 1)
            with open(local, 'rb') as f:
                replacements[rom.file_id(in_rom)] = f.read()
            i += 2
        elif args[i] == '--out':
            out_path = args[i + 1]
            i += 2
        else:
            i += 1
    if not out_path:
        print("--out is required")
        sys.exit(1)
    new_rom, report = rom.build(replacements)
    with open(out_path, 'wb') as f:
        f.write(new_rom)
    print(f"wrote {out_path}")
    for fid, path, old, new in report['replaced']:
        print(f"  replaced {path} (fid {fid}): {old} -> {new} bytes")
    print(f"  files moved: {report['moved_files']}")
    print(f"  total_used_rom_size: {report['total_used_rom_size']}")


if __name__ == '__main__':
    main()
