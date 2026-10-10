"""
ARM9 call graph — every THUMB `BL` in the executable, as target -> callers.

Built while hunting a hook point for runtime enemy scaling. Useful on its own: it
is the only way to ask "what calls this?" in this binary, because the usual trick of
searching for a function's address does not work here (see below).

Three facts about this game's ARM9 that this tool exists to work around:

  * It is **not compressed**. The entry point at 0x02000800 disassembles as ordinary
    ARM, so code and literal pools are readable directly from the ROM.
  * It is almost entirely **THUMB**, and THUMB loads constants with PC-relative
    `LDR`. A 32-bit address therefore appears only inside a literal pool, and
    searching for it finds the pool entry rather than any instruction. Searching for
    an address and getting *zero* hits means the code uses a PC-relative load, not
    that the address is unused.
  * Resource names are **neither strings nor DJB2 hashes** in the code. Searching for
    "creatures.GDA", bare "creatures", or the hash the archive uses all return
    nothing, so GDA loading is driven by table indices rather than names.

    py callgraph.py <rom.nds> [--target 0x020BC2FC] [--hot 20]
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'build'))

from rom_build import Rom  # noqa: E402


def arm9_image(rom_path):
    raw = open(rom_path, 'rb').read()
    h = Rom(raw).header
    off, size = h['arm9_rom_offset'], h['arm9_size']
    return raw[off:off + size], h['arm9_ram']


def bl_edges(a9, base):
    """{target address: [caller addresses]} for every THUMB BL.

    A THUMB BL is two halfwords: the first 0xF000|hi11, the second 0xF800|lo11, and
    the branch is relative to (address + 4). Scanning every even offset will decode
    some data as instructions, but a wrong decode almost never lands on a plausible
    in-image target, so the noise is low and self-evident.
    """
    out = {}
    for i in range(0, len(a9) - 4, 2):
        hi = a9[i] | (a9[i + 1] << 8)
        if (hi & 0xF800) != 0xF000:
            continue
        lo = a9[i + 2] | (a9[i + 3] << 8)
        if (lo & 0xF800) != 0xF800:
            continue
        off = ((hi & 0x7FF) << 12) | ((lo & 0x7FF) << 1)
        if off & 0x400000:
            off -= 0x800000
        out.setdefault(base + i + 4 + off, []).append(base + i)
    return out


def literal_refs(a9, base, value):
    """Every 4-byte occurrence of `value` — i.e. the literal pools that hold it."""
    out, i, needle = [], 0, struct.pack('<I', value & 0xFFFFFFFF)
    while True:
        i = a9.find(needle, i)
        if i < 0:
            break
        out.append(base + i)
        i += 4
    return out


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    a9, base = arm9_image(sys.argv[1])
    edges = bl_edges(a9, base)
    print('ARM9 %d bytes at 0x%08X — %d distinct BL targets, %d call sites'
          % (len(a9), base, len(edges), sum(len(v) for v in edges.values())))
    if '--target' in sys.argv:
        t = int(sys.argv[sys.argv.index('--target') + 1], 0)
        callers = edges.get(t, [])
        print('\n0x%08X has %d callers:' % (t, len(callers)))
        for c in callers[:60]:
            print('   0x%08X' % c)
    n = int(sys.argv[sys.argv.index('--hot') + 1]) if '--hot' in sys.argv else 10
    print('\nmost-called (allocators, string and math helpers dominate):')
    for a, cs in sorted(edges.items(), key=lambda kv: -len(kv[1]))[:n]:
        print('   0x%08X  %5d callers' % (a, len(cs)))


if __name__ == '__main__':
    main()
