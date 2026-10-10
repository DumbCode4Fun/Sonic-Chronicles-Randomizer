"""
Grant Shadow Dash III — and confirm the movement-ability-level model.

Model (established in REVERSE_ENGINEERING_LOG.md):
  * `creatures.GDA` gives each character up to **three movement-ability slots**
    (columns `#1588449107`, `#2147880983`, `#1885680587`), each holding a
    movement-ability id from `movement.GDA`;
  * `Adv_<Character>.GDA` columns **12, 13, 14** hold the *level* of slots 1, 2
    and 3 at each character level.

Shadow's slot 1 is Dash, and his column 12 runs `111222222…` — it reaches 2 and
stops, which is why he has **Dash II**. Sonic's runs `111222233333…`, reaching 3.

This build rewrites Shadow's column 12 to follow Sonic's curve (level 1-3 → 1,
4-7 → 2, 8+ → 3), which should give him **Dash III** from character level 8.

`movement.GDA` already declares Dash `maxlevel 3`, so this asks for nothing the
engine does not already support — it only changes when Shadow qualifies.

If this works in game it confirms the whole model, and the same one-column edit
generalises to any character/ability pair (including raising `maxlevel` itself for
abilities currently capped at 1).

Usage:
    py build_dash3.py <rom.nds> [--out-dir build]
"""
import json
import os
import sys
import time
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'recon'))

import bps  # noqa: E402
from rom_build import Rom, verify_noop  # noqa: E402
from herf_write import HerfFile  # noqa: E402
from gda_write import set_int_cell, ROW_FIELD_BASE  # noqa: E402
from gff4 import GFF4, read_gda  # noqa: E402

ARCHIVE = '/test.herf'
TARGET = 'Adv_Shadow.GDA'
SLOT1_LEVEL_COL = 12          # positional column index
# Sonic's curve: levels 1-3 -> 1, 4-7 -> 2, 8+ -> 3
def curve(level):
    return 1 if level <= 3 else (2 if level <= 7 else 3)


def fail(stage, msg):
    print(f"\n!! ABORTED at {stage}: {msg}")
    sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    rom_path = sys.argv[1]
    out_dir = 'build'
    if '--out-dir' in sys.argv:
        out_dir = sys.argv[sys.argv.index('--out-dir') + 1]
    os.makedirs(out_dir, exist_ok=True)

    with open(rom_path, 'rb') as f:
        original = f.read()
    rom = Rom(original)
    print(f"source CRC32 {zlib.crc32(original) & 0xFFFFFFFF:08X}")
    if not verify_noop(rom_path):
        fail('validate', 'no-op rebuild is not byte-identical')

    fid = rom.file_id(ARCHIVE)
    herf = HerfFile(rom.file_bytes(fid))
    if herf.serialize() != rom.file_bytes(fid):
        fail('validate', 'no-op archive serialize differs')

    raw = herf.read(TARGET)
    cols, rows = read_gda(GFF4(raw))
    before = [r[ROW_FIELD_BASE + SLOT1_LEVEL_COL] for r in rows]
    levels = [r[ROW_FIELD_BASE + 1] for r in rows]
    print(f"\n{TARGET} slot-1 (Dash) level by character level, before:")
    print('  ' + ''.join(str(x) for x in before))

    for i, lv in enumerate(levels):
        want = curve(lv)
        if before[i] != want:
            raw, _ = set_int_cell(raw, i, SLOT1_LEVEL_COL, want)
    note = herf.replace(TARGET, raw)

    cols2, rows2 = read_gda(GFF4(herf.read(TARGET)))
    after = [r[ROW_FIELD_BASE + SLOT1_LEVEL_COL] for r in rows2]
    print(f"{TARGET} slot-1 (Dash) level, after:")
    print('  ' + ''.join(str(x) for x in after))
    print(f"  [{note}]")
    if max(after) != 3:
        fail('edit', f'slot-1 level maxes at {max(after)}, expected 3')

    probs = herf.validate()
    if probs:
        fail('edit', f'archive invalid: {probs[:3]}')

    new_rom, br = rom.build({fid: herf.serialize()})
    out_rom = os.path.join(out_dir, 'sonic_chronicles_dash3.nds')
    with open(out_rom, 'wb') as f:
        f.write(new_rom)
    print(f"\nwrote {out_rom}  (CRC32 {zlib.crc32(new_rom) & 0xFFFFFFFF:08X}, "
          f"files moved {br['moved_files']})")

    rebuilt = Rom(new_rom)
    rb = HerfFile(rebuilt.file_bytes(rebuilt.file_id(ARCHIVE)))
    _, rows3 = read_gda(GFF4(rb.read(TARGET)))
    chk = [r[ROW_FIELD_BASE + SLOT1_LEVEL_COL] for r in rows3]
    if chk != after:
        fail('verify', 'edit did not survive the rebuild')
    print("  read back from the rebuilt ROM: OK")

    bad = []
    for i, n in rb.names.items():
        if n.lower().endswith('.gda'):
            try:
                read_gda(GFF4(rb.read(i)))
            except Exception as e:
                bad.append(n)
    print(f"  all GDA tables still decode: {not bad}")
    if bad:
        fail('verify', f'{len(bad)} tables broke')

    patch = bps.create(original, new_rom, json.dumps({'kind': 'Shadow Dash III'}).encode())
    out_patch = os.path.join(out_dir, 'sonic_chronicles_dash3.bps')
    with open(out_patch, 'wb') as f:
        f.write(patch)
    if bps.apply(original, patch) != new_rom:
        fail('patch', 'patch does not reproduce the ROM')
    print(f"  wrote {out_patch} ({len(patch)} bytes), verified")

    with open(os.path.join(out_dir, 'build_report_dash3.json'), 'w', encoding='utf-8') as f:
        json.dump({'generated': time.strftime('%Y-%m-%d %H:%M:%S'),
                   'experiment': 'does Adv_<char> column 12 control movement-ability level?',
                   'target': TARGET, 'before': before, 'after': after,
                   'output_rom': os.path.abspath(out_rom)}, f, indent=2)
    print("\nALL CHECKS PASSED — Shadow should have Dash III from character level 8")


if __name__ == '__main__':
    main()
