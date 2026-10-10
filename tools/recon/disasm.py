"""
Targeted ARM9 disassembler for this project (capstone-backed).

The ARM9 binary loads at RAM `0x02000000` and lives at ROM offset `0x4000`, so:
    ARM9 file offset = RAM address - 0x02000000
    ROM offset       = ARM9 file offset + 0x4000

This game is compiled largely as **THUMB** (function pointers in vtables have bit
0 set), so THUMB is the default mode; pass `--arm` for ARM-mode code.

Usage:
    py disasm.py <rom.nds> <ram_address> [count] [--arm] [--back N]
    py disasm.py <rom.nds> --xref <ram_address>     # find pointers to an address
"""
import struct
import sys

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_ARM

ARM9_ROM_OFF = 0x4000
ARM9_RAM = 0x02000000
ARM9_SIZE = 0x110DD8


def load(rom_path):
    with open(rom_path, 'rb') as f:
        data = f.read()
    return data[ARM9_ROM_OFF:ARM9_ROM_OFF + ARM9_SIZE]


def disasm(arm9, ram_addr, count=40, thumb=True, back=0):
    off = (ram_addr & ~1) - ARM9_RAM - back
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB if thumb else CS_MODE_ARM)
    md.detail = False
    code = arm9[off:off + count * 4 + back]
    out = []
    for ins in md.disasm(code, ARM9_RAM + off):
        out.append(f"  {ins.address:08X}  {ins.bytes.hex(' '):<12} {ins.mnemonic:<8} {ins.op_str}")
        if len(out) >= count:
            break
    return out


def xrefs(arm9, ram_addr):
    """Every 4-byte-aligned word in ARM9 equal to this address (literal pools, tables)."""
    needle = struct.pack('<I', ram_addr)
    hits = []
    start = 0
    while True:
        i = arm9.find(needle, start)
        if i < 0:
            break
        hits.append(ARM9_RAM + i)
        start = i + 1
    return hits


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    arm9 = load(sys.argv[1])
    if sys.argv[2] == '--xref':
        addr = int(sys.argv[3], 16)
        hits = xrefs(arm9, addr)
        print(f"words equal to 0x{addr:08X}: {len(hits)}")
        for h in hits[:40]:
            print(f"  0x{h:08X}")
        return
    addr = int(sys.argv[2], 16)
    count = int(sys.argv[3]) if len(sys.argv) > 3 and not sys.argv[3].startswith('-') else 40
    thumb = '--arm' not in sys.argv
    back = 0
    if '--back' in sys.argv:
        back = int(sys.argv[sys.argv.index('--back') + 1])
    print(f"ARM9 @ RAM 0x{addr:08X}  ({'THUMB' if thumb else 'ARM'})")
    for line in disasm(arm9, addr, count, thumb, back):
        print(line)


if __name__ == '__main__':
    main()
