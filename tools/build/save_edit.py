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

Known field offsets (established by diffing a save before/after levelling). **These are
for one particular save and do not transfer** — a different save had every one of them
reading zero. Prefer `--party`, which finds the blocks by their shape.

    0x0263D speed   0x02641 attack  0x02645 defense  0x02649 hp
    0x0264D power   0x02651 grit    0x02655 luck     0x02661 pp
    0x026B9 level   0x026E1 movement-ability slot 1  0x026E5 slot 2

**Party stat blocks.** Each recruited character has a 0x214-byte block holding its stats
as seven consecutive `uint32`s, in the same order as the `Adv_*.GDA` columns:

    +0x000 speed  +0x004 attack  +0x008 defense  +0x00C hp
    +0x010 power  +0x014 grit    +0x018 luck     +0x024 pp

`find_party` locates them by looking for that run of seven plausible stat values and
then walking the 0x214 stride. In the save it was developed against, Sonic sat at
0x01582 and Amy at 0x01796 — and the run included **power 8 and grit 2**, two stats the
game never puts on screen, which is what makes the match trustworthy rather than lucky.

**Why this matters.** A character's stats live in the *save*, not in the progression
table: editing `Adv_Sonic.GDA` changes what the next level-up grants and does nothing to
a character who has already passed that level. A `stat_curve` profile therefore has no
effect on a save in progress, which is exactly how it looked when one was built to make
a playtest party unkillable and the party stayed killable.

Usage:
    py save_edit.py <save.dsv> --check
    py save_edit.py <save.dsv> --party
    py save_edit.py <save.dsv> --godmode            # every found character, maxed
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


BLOCK_STRIDE = 0x214
#: offsets of the stat fields inside one character block
BLOCK_FIELDS = [(0x000, 'speed'), (0x004, 'attack'), (0x008, 'defense'),
                (0x00C, 'hp'), (0x010, 'power'), (0x014, 'grit'),
                (0x018, 'luck'), (0x024, 'pp')]
#: what `--godmode` writes. Deliberately not absurd: grit at or above 999 is the
#: sentinel the creature table uses for "cannot be hurt", so stay well clear of it.
GODMODE = {'speed': 150, 'attack': 255, 'defense': 200, 'hp': 500,
           'power': 255, 'grit': 200, 'luck': 50, 'pp': 99}


def _looks_like_stats(data, off):
    """Seven consecutive uint32s that could be one character's stat line.

    Every value at least 2 — which is what rejects the two sliding-window artifacts a
    looser test picks up, both of which contain a 1 — and hp at least 20, which no
    character has ever had.
    """
    try:
        v = struct.unpack_from('<7I', data, off)
    except struct.error:
        return False
    return all(2 <= x <= 999 for x in v) and v[3] >= 20


def find_party(data):
    """[(offset, {stat: value})] for every character stat block in the save.

    Scanning for the shape beats walking a stride. The blocks are *mostly* 0x214 apart
    but not reliably — one late-game save spaces its first two by 0x220 — and the same
    save carries a **second complete copy** of its party a few tens of KB further on,
    which a stride walk from the first block would never reach. Blocks closer together
    than 0x100 are collapsed, since a stat line matches at a couple of neighbouring
    offsets when the surrounding values happen to line up.
    """
    out = []
    off, last = 0, None
    while off < len(data) - 32:
        if _looks_like_stats(data, off):
            if last is None or off - last >= 0x100:
                out.append((off, {name: struct.unpack_from('<I', data, off + d)[0]
                                  for d, name in BLOCK_FIELDS}))
                last = off
            off += 4
        else:
            off += 1
    return out


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

    party = find_party(data)
    if party:
        print(f"  party blocks: {len(party)} (stride 0x{BLOCK_STRIDE:X})")
        for off, stats in party:
            line = '  '.join(f"{k} {v}" for k, v in stats.items())
            print(f"    0x{off:05X}  {line}")

    if '--check' in sys.argv or ('--set' not in sys.argv
                                 and '--godmode' not in sys.argv):
        return

    out = bytearray(data)
    args = sys.argv[2:]

    if '--godmode' in args:
        if not party:
            print("  !! no party blocks found; nothing to boost")
            sys.exit(1)
        for off, _ in party:
            for d, name in BLOCK_FIELDS:
                struct.pack_into('<I', out, off + d, GODMODE[name])
            print(f"  maxed the character at 0x{off:05X}")
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
