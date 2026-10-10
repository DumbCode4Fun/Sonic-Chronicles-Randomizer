"""
Targeted experiment: does the item tooltip ever render stat 26 (GRT / "Armor"),
and does it render more than one stat row?

Background: SpeedySneakers (`Item34.ITM`) carries `SPD+3` (stat 21) and `GRT+1`
(stat 26). In game the tooltip shows only "Speed +99" after a buff build — Grit
never appears, in vanilla or modded. Two hypotheses could explain that:

    H1  the tooltip renders only ONE stat row (the first one)
    H2  the tooltip renders every stat row EXCEPT stat 26

The item's two rows are byte-for-byte identical in structure apart from `SData1`,
so nothing in the item data distinguishes them — it has to be UI behaviour.

This build swaps the two rows' target stats so one ROM distinguishes both
hypotheses at once:

    row "SPD+"  SData1 21 -> 26   (now targets Grit; first row)
    row "GRT+"  SData1 26 -> 22   (now targets Attack; second row)

Both magnitudes set to 99. Reading the tooltip then gives an unambiguous answer:

    "Attack +99" only  -> stat 26 is hidden, and non-first rows DO render  => H2
    nothing at all     -> only the first row renders AND stat 26 is hidden
    "Armor/Grit +99"   -> stat 26 does render; the original behaviour had
                          another cause entirely

Note the row *labels* stay "SPD+" and "GRT+" and are now actively misleading —
which is a live demonstration of an earlier finding: row labels are comments, the
engine keys off `SData1`.

Usage:
    py build_stat_test.py <rom.nds> [--out-dir build]
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
from twoda_write import set_cell  # noqa: E402
from twoda import parse_2da  # noqa: E402

ARCHIVE = '/test.herf'
ITEM = 'Item34.ITM'          # SpeedySneakers
STAT_GRIT, STAT_ATTACK = '26', '22'


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

    raw = herf.read(ITEM)
    before = {lbl: dict(v) for lbl, v in parse_2da(raw).rows if lbl in ('SPD+', 'GRT+')}
    print(f"\n{ITEM} before:")
    for lbl, v in before.items():
        print(f"  {lbl:5} Data={v['Data']:>3}  SData1={v['SData1']} ")

    for label, stat in (('SPD+', STAT_GRIT), ('GRT+', STAT_ATTACK)):
        raw, n = set_cell(raw, label, 'SData1', stat)
        print(f"  {n}")
        raw, n = set_cell(raw, label, 'Data', '99')
        print(f"  {n}")

    after = {lbl: dict(v) for lbl, v in parse_2da(raw).rows if lbl in ('SPD+', 'GRT+')}
    print(f"\n{ITEM} after:")
    for lbl, v in after.items():
        stat = {'21': 'Speed', '22': 'Attack', '26': 'Grit/Armor'}.get(v['SData1'], v['SData1'])
        print(f"  {lbl:5} Data={v['Data']:>3}  SData1={v['SData1']} -> {stat}")

    note = herf.replace(ITEM, raw)
    probs = herf.validate()
    if probs:
        fail('edit', f'archive invalid: {probs[:3]}')
    print(f"\nstored: {note}")

    new_rom, br = rom.build({fid: herf.serialize()})
    out_rom = os.path.join(out_dir, 'sonic_chronicles_stattest.nds')
    with open(out_rom, 'wb') as f:
        f.write(new_rom)
    print(f"wrote {out_rom}  (CRC32 {zlib.crc32(new_rom) & 0xFFFFFFFF:08X}, "
          f"files moved {br['moved_files']})")

    # verify from the rebuilt ROM
    rebuilt = Rom(new_rom)
    rb = HerfFile(rebuilt.file_bytes(rebuilt.file_id(ARCHIVE)))
    t = parse_2da(rb.read(ITEM))
    got = {lbl: (v['Data'], v['SData1']) for lbl, v in t.rows if lbl in ('SPD+', 'GRT+')}
    ok = got.get('SPD+') == ('99', STAT_GRIT) and got.get('GRT+') == ('99', STAT_ATTACK)
    print(f"read back from rebuilt ROM: {got}  -> {'OK' if ok else 'MISMATCH'}")
    if not ok:
        fail('verify', 'edit did not survive the rebuild')

    bad = [n for i, n in rb.names.items()
           if n.lower().endswith(('.itm', '.spl')) and not _parses(rb, i)]
    print(f"all .itm/.spl tables still parse: {not bad}")
    if bad:
        fail('verify', f'{len(bad)} tables broke')

    patch = bps.create(original, new_rom, json.dumps({'kind': 'stat display test'}).encode())
    out_patch = os.path.join(out_dir, 'sonic_chronicles_stattest.bps')
    with open(out_patch, 'wb') as f:
        f.write(patch)
    if bps.apply(original, patch) != new_rom:
        fail('patch', 'patch does not reproduce the ROM')
    print(f"wrote {out_patch} ({len(patch)} bytes), verified")

    with open(os.path.join(out_dir, 'build_report_stattest.json'), 'w', encoding='utf-8') as f:
        json.dump({'generated': time.strftime('%Y-%m-%d %H:%M:%S'),
                   'experiment': 'does the item tooltip render stat 26 (Grit/Armor)?',
                   'item': ITEM, 'before': before, 'after': after,
                   'output_rom': os.path.abspath(out_rom),
                   'patch_bytes': len(patch)}, f, indent=2)
    print("\nALL CHECKS PASSED")


def _parses(rb, i):
    try:
        parse_2da(rb.read(i))
        return True
    except Exception:
        return False


if __name__ == '__main__':
    main()
