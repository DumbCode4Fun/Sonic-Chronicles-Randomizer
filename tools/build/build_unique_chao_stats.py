"""
Can a code-driven Chao also carry data-driven stat bonuses?

The ten Unique Chao have **no effect rows at all** — their behaviour (Spartoi's
instant-KO, Ferox's guaranteed POW moves) lives in ARM9, keyed by item id. So they
cannot be retuned by data editing.

But the coded effect fires from the **item id**, while ordinary stat bonuses come
from the item's **effect rows**. Those are independent mechanisms, so appending
stat rows should stack a bonus on top of the special behaviour without disturbing
it. This build tests exactly that.

Targets, both hatchable Uniques (obtainability is flagged by `Chaos.GDA` column
`#3678486078`, which is 0 for these):

    Spartoi   items 130 / 170 / 210   basic attacks may instantly KO
    Ferox     item  128 (all levels)  POW moves automatically succeed

Bonuses are deliberately built from **visible** stats (ATK, DEF, LCK, SPD) so the
result can be read straight off the character panel — POW and GRT would be
invisible and leave the test ambiguous.

    Spartoi  ATK +4/8/12 and LCK +4/8/12   (fits a precision-strike Chao)
    Ferox    SPD +10 and ATK +5            (single item, so it cannot scale)

Reading the result:
  * special effect still fires AND the stats appear -> they stack; Uniques can be
    buffed without losing what makes them interesting
  * stats appear but the special effect stops -> adding rows displaces the coded
    behaviour, and Uniques must be left alone
  * no stat change -> Chao bonuses are read differently from equipment

Usage:
    py build_unique_chao_stats.py <rom.nds> [--out-dir build]
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
from tlk_write import TlkFile  # noqa: E402
from twoda_write import add_row  # noqa: E402
from twoda import parse_2da  # noqa: E402
from gff4 import GFF4, read_gda  # noqa: E402

ARCHIVE = '/test.herf'
TLK_PATH = '/strings.tlk'
SPD, ATK, DEF, POW, GRT, LCK = 21, 22, 23, 25, 26, 27

# item id -> (label, stat, value) rows to append
PLAN = {
    130: [('ATK+', ATK, 4), ('LCK+', LCK, 4)],
    170: [('ATK+', ATK, 8), ('LCK+', LCK, 8)],
    210: [('ATK+', ATK, 12), ('LCK+', LCK, 12)],
    128: [('SPD+', SPD, 10), ('ATK+', ATK, 5)],
}
DESC = {
    'Spartoi': "Bonded character's basic attacks may cause instant KO against enemies, "
               "and its attack and luck are raised.",
    'Ferox': "Bonded character automatically succeeds using their POW moves, "
             "and is faster and more accurate.",
}
META = ('SpellData', 'CollectionData_Equip', 'CollectionData_Use')


def fail(stage, msg):
    print(f"\n!! ABORTED at {stage}: {msg}")
    sys.exit(1)


def effect_rows(table):
    """Live (non-metadata, non-zero, non-VFX) rows as {stat: value}."""
    out = {}
    for lbl, v in table.rows:
        if lbl in META:
            continue
        try:
            sid, val = int(v['SData1']), int(v['Data'])
        except (TypeError, ValueError):
            continue
        if sid == 38 or val == 0:
            continue
        out[sid] = val
    return out


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    rom_path = sys.argv[1]
    out_dir = 'build'
    if '--out-dir' in sys.argv:
        out_dir = sys.argv[sys.argv.index('--out-dir') + 1]
    os.makedirs(out_dir, exist_ok=True)

    print("=" * 70)
    print("STAGE 1  validate")
    print("=" * 70)
    with open(rom_path, 'rb') as f:
        original = f.read()
    rom = Rom(original)
    print(f"  source CRC32 {zlib.crc32(original) & 0xFFFFFFFF:08X}")
    if not verify_noop(rom_path):
        fail('stage 1', 'no-op rebuild is not byte-identical')
    hf = rom.file_id(ARCHIVE)
    herf = HerfFile(rom.file_bytes(hf))
    tf = rom.file_id(TLK_PATH)
    tlk = TlkFile(rom.file_bytes(tf))
    if herf.serialize() != rom.file_bytes(hf) or tlk.serialize() != rom.file_bytes(tf):
        fail('stage 1', 'a no-op serialize differs from input')

    g = GFF4(herf.read('Items.GDA'))
    cols, rows = read_gda(g)
    K = sorted(rows[0].keys())
    lower = {n.lower(): n for n in herf.names.values()}
    info = {}
    for r in rows:
        iid, nref, dref, typ, sub, base = (r[K[i]] for i in range(6))
        if iid in PLAN and base and base != 'None':
            key = lower.get(str(base).lower())
            if key:
                info[iid] = (key, nref, dref)
    missing = set(PLAN) - set(info)
    if missing:
        fail('stage 1', f'item ids not found: {missing}')

    print()
    print("=" * 70)
    print("STAGE 2  append stat rows (nothing existing is touched)")
    print("=" * 70)
    changed = []
    for iid, spec in sorted(PLAN.items()):
        key, nref, dref = info[iid]
        raw = herf.read(key)
        before = effect_rows(parse_2da(raw))
        if before:
            fail('stage 2', f'item {iid} unexpectedly already has effect rows: {before}')
        for lbl, stat, val in spec:
            raw, _ = add_row(raw, lbl, {'EffectId': '1', 'Data': str(val),
                                        'SData1': str(stat), 'SData2': '0',
                                        'SData3': '0', 'Pulse': '-1'})
        herf.replace(key, raw)
        after = effect_rows(parse_2da(herf.read(key)))
        print(f"  item {iid:<4} ({key:<13}) had no effect rows -> now {after}")
        changed.append({'item': iid, 'file': key, 'added': after})

    # descriptions
    for name, text in DESC.items():
        pass
    for iid, (key, nref, dref) in info.items():
        name = 'Spartoi' if iid in (130, 170, 210) else 'Ferox'
        try:
            tlk.set_string(tlk.index_of_id(dref), DESC[name])
        except KeyError:
            pass
    print("  descriptions updated")

    probs = herf.validate()
    if probs:
        fail('stage 2', f'archive invalid: {probs[:3]}')

    print()
    print("=" * 70)
    print("STAGE 3  rebuild + verify from the rebuilt ROM")
    print("=" * 70)
    new_rom, br = rom.build({hf: herf.serialize(), tf: tlk.serialize()})
    out_rom = os.path.join(out_dir, 'sonic_chronicles_uniquechao.nds')
    with open(out_rom, 'wb') as f:
        f.write(new_rom)
    print(f"  wrote {out_rom}  (CRC32 {zlib.crc32(new_rom) & 0xFFFFFFFF:08X}, "
          f"files moved {br['moved_files']})")

    rebuilt = Rom(new_rom)
    rb = HerfFile(rebuilt.file_bytes(rebuilt.file_id(ARCHIVE)))
    for c in changed:
        got = effect_rows(parse_2da(rb.read(c['file'])))
        if got != c['added']:
            fail('stage 3', f"item {c['item']} reads {got}, expected {c['added']}")
    print(f"  all {len(changed)} items read back correctly")

    bad = [n for i, n in rb.names.items()
           if n.lower().endswith(('.itm', '.spl')) and not _ok(rb, i)]
    print(f"  all .itm/.spl tables still parse: {not bad}")
    if bad:
        fail('stage 3', f'{len(bad)} tables broke')

    print()
    print("=" * 70)
    print("STAGE 4  patch")
    print("=" * 70)
    patch = bps.create(original, new_rom,
                       json.dumps({'kind': 'stat rows on code-driven Unique Chao'}).encode())
    out_patch = os.path.join(out_dir, 'sonic_chronicles_uniquechao.bps')
    with open(out_patch, 'wb') as f:
        f.write(patch)
    if bps.apply(original, patch) != new_rom:
        fail('stage 4', 'patch does not reproduce the ROM')
    print(f"  wrote {out_patch} ({len(patch)} bytes), verified")

    with open(os.path.join(out_dir, 'build_report_uniquechao.json'), 'w', encoding='utf-8') as f:
        json.dump({'generated': time.strftime('%Y-%m-%d %H:%M:%S'),
                   'experiment': 'do stat rows stack on top of a Chao whose effect is coded in ARM9?',
                   'items': changed, 'output_rom': os.path.abspath(out_rom),
                   'patch_bytes': len(patch)}, f, indent=2)
    print("\nALL STAGES PASSED")


def _ok(rb, i):
    try:
        parse_2da(rb.read(i))
        return True
    except Exception:
        return False


if __name__ == '__main__':
    main()
