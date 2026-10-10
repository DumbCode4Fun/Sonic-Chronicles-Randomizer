"""
Save-file editor for Sonic Chronicles (DeSmuME `.dsv`) — with correct checksums.

The game validates its save and **wipes the slot** if a byte is wrong, so editing
a save requires recomputing its checksums. Both were recovered by disassembling
the ARM9 CRC routine (see REVERSE_ENGINEERING_LOG.md):

    crc32 routine @ RAM 0x020B7C38 — reflected poly 0xEDB88320,
                    **init = 0, no final XOR** (not the usual convention)

    outer: stored at 0x203 = crc32( save[0x207 : 0x207 + 0x3BF9] )
    inner: stored at 0x234 = crc32( save[0x238 : 0x238 + 0x21]  )

The inner region lies **inside** the outer one, so the inner checksum must be
recomputed first or the outer will be computed over stale bytes.

Known field offsets (established by diffing a save before/after levelling; these
are for the save in hand and may depend on party/slot layout — see KNOWN_MEMORY.md):

    0x0263D speed   0x02641 attack  0x02645 defense  0x02649 hp
    0x0264D power   0x02651 grit    0x02655 luck     0x02661 pp
    0x026B9 level   0x026E1 movement-ability slot 1  0x026E5 slot 2

Usage:
    py save_edit.py <save.dsv> --check
    py save_edit.py <save.dsv> --set <hex_offset>=<value> [...] [--out <file>]
"""
import os
import shutil
import struct
import sys
import zlib

OUTER_STORE, OUTER_DATA, OUTER_LEN = 0x203, 0x207, 0x3BF9
INNER_STORE, INNER_DATA, INNER_LEN = 0x234, 0x238, 0x21

FIELDS = {
    0x0263D: 'speed', 0x02641: 'attack', 0x02645: 'defense', 0x02649: 'hp',
    0x0264D: 'power', 0x02651: 'grit', 0x02655: 'luck', 0x02661: 'pp',
    0x026B9: 'level', 0x026E1: 'move slot 1', 0x026E5: 'move slot 2',
}


def crc(data: bytes) -> int:
    """The game's CRC32: reflected 0xEDB88320, init 0, no final XOR."""
    return zlib.crc32(data, 0xFFFFFFFF) ^ 0xFFFFFFFF


def verify(data: bytes):
    inner_ok = struct.unpack_from('<I', data, INNER_STORE)[0] == crc(data[INNER_DATA:INNER_DATA + INNER_LEN])
    outer_ok = struct.unpack_from('<I', data, OUTER_STORE)[0] == crc(data[OUTER_DATA:OUTER_DATA + OUTER_LEN])
    return inner_ok, outer_ok


def reseal(data: bytes) -> bytes:
    """Recompute both checksums. Inner first — it lives inside the outer range."""
    b = bytearray(data)
    struct.pack_into('<I', b, INNER_STORE, crc(bytes(b[INNER_DATA:INNER_DATA + INNER_LEN])))
    struct.pack_into('<I', b, OUTER_STORE, crc(bytes(b[OUTER_DATA:OUTER_DATA + OUTER_LEN])))
    return bytes(b)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    path = sys.argv[1]
    with open(path, 'rb') as f:
        data = f.read()

    inner_ok, outer_ok = verify(data)
    print(f"{os.path.basename(path)}  ({len(data)} bytes)")
    print(f"  inner checksum @0x234: {'OK' if inner_ok else 'BAD'}")
    print(f"  outer checksum @0x203: {'OK' if outer_ok else 'BAD'}")
    for off, name in sorted(FIELDS.items()):
        print(f"  0x{off:05X} {name:<14} = {struct.unpack_from('<I', data, off)[0]}")

    if '--check' in sys.argv or '--set' not in sys.argv:
        return

    out = bytearray(data)
    args = sys.argv[2:]
    i = 0
    out_path = path
    while i < len(args):
        if args[i] == '--set':
            spec = args[i + 1]
            off_s, val_s = spec.split('=', 1)
            off = int(off_s, 16)
            val = int(val_s, 0)
            old = struct.unpack_from('<I', out, off)[0]
            struct.pack_into('<I', out, off, val)
            print(f"  set 0x{off:05X} ({FIELDS.get(off, '?')}): {old} -> {val}")
            i += 2
        elif args[i] == '--out':
            out_path = args[i + 1]
            i += 2
        else:
            i += 1

    sealed = reseal(bytes(out))
    inner_ok, outer_ok = verify(sealed)
    print(f"  resealed: inner {'OK' if inner_ok else 'BAD'}, outer {'OK' if outer_ok else 'BAD'}")
    if not (inner_ok and outer_ok):
        print("  !! refusing to write — checksums do not validate")
        sys.exit(1)

    if out_path == path and not os.path.exists(path + '.bak'):
        shutil.copy2(path, path + '.bak')
        print(f"  backup: {os.path.basename(path)}.bak")
    with open(out_path, 'wb') as f:
        f.write(sealed)
    print(f"  wrote {out_path}")


if __name__ == '__main__':
    main()
