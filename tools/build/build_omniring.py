"""
The Omni Ring — a combined accessory granting all six elemental attacks, and the
experiment that answers whether the engine honours more than one `ELEMENT` row.

Background: the six elemental Rings (items 68-73) each carry exactly three effect
rows — two `VFX` rows and one `ELEMENT` row whose `SData1` is the element's attack
affinity id (107 Fire, 108 Water, 109 Earth, 110 Wind, 111 Lightning, 112 Ice).
An item's `.itm` is just a list of effect records, so writing all six into one item
is trivially possible. **Whether the engine applies all six, or only the first, is
unknown** — that is what this build tests.

Target: item 74, "Kron Hammer" (internal name `PowerRing`, an accessory). Chosen
because it is already equipped in the test save, so the result is observable
immediately. Its existing `POW+5` is **kept**, so the item is a strict upgrade
rather than a trade — any elemental behaviour observed is purely additive.

The item is renamed to "Omni Ring" and its description rewritten, using the
`name`/`description` strrefs from `Items.GDA` and the TLK writer.

Reading the result:
  * basic attacks show several elemental effects, or are effective against
    everything -> the engine honours multiple ELEMENT rows
  * only Fire (the first row) appears -> it takes one element and ignores the rest
  * attacks lose elemental behaviour entirely -> conflicting rows cancel out

Any of the three is a useful answer about how composable item effects really are.

Usage:
    py build_omniring.py <rom.nds> [--out-dir build]
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
TARGET_ITEM_ID = 74           # Kron Hammer / PowerRing
RING_ITEM_IDS = [68, 69, 70, 71, 72, 73]

ELEMENT_NAMES = {107: 'Fire', 108: 'Water', 109: 'Earth',
                 110: 'Wind', 111: 'Lightning', 112: 'Ice'}

NEW_NAME = 'Omni Ring'
NEW_DESC = ("A ring humming with every element at once. Gives Fire, Water, Earth, "
            "Wind, Lightning and Ice damage to basic attacks. Very greatly increases damage.")


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

    print("=" * 70)
    print("STAGE 1  validate")
    print("=" * 70)
    with open(rom_path, 'rb') as f:
        original = f.read()
    rom = Rom(original)
    print(f"  source CRC32 {zlib.crc32(original) & 0xFFFFFFFF:08X}")
    if not verify_noop(rom_path):
        fail('stage 1', 'no-op rebuild is not byte-identical')

    herf_fid = rom.file_id(ARCHIVE)
    herf = HerfFile(rom.file_bytes(herf_fid))
    tlk_fid = rom.file_id(TLK_PATH)
    tlk = TlkFile(rom.file_bytes(tlk_fid))
    if herf.serialize() != rom.file_bytes(herf_fid) or tlk.serialize() != rom.file_bytes(tlk_fid):
        fail('stage 1', 'a no-op serialize differs from input')

    # Resolve item id -> (.itm resource, name strref, description strref)
    g = GFF4(herf.read('Items.GDA'))
    cols, rows = read_gda(g)
    K = sorted(rows[0].keys())
    lower = {n.lower(): n for n in herf.names.values()}
    info = {}
    for r in rows:
        iid, nref, dref, typ, sub, base = (r[K[i]] for i in range(6))
        if base and base != 'None':
            key = lower.get(str(base).lower())
            if key:
                info[iid] = {'file': key, 'name_ref': nref, 'desc_ref': dref}
    for iid in RING_ITEM_IDS + [TARGET_ITEM_ID]:
        if iid not in info:
            fail('stage 1', f'item {iid} not found in Items.GDA')

    print()
    print("=" * 70)
    print("STAGE 2  harvest the six rings' effect rows")
    print("=" * 70)
    harvested = []
    for iid in RING_ITEM_IDS:
        t = parse_2da(herf.read(info[iid]['file']))
        for lbl, v in t.rows:
            if lbl in ('VFX', 'ELEMENT'):
                harvested.append((lbl, {'EffectId': v['EffectId'], 'Data': v['Data'],
                                        'SData1': v['SData1'], 'SData2': v['SData2'],
                                        'SData3': v['SData3'], 'Pulse': v['Pulse']}))
        el = [v['SData1'] for lbl, v in t.rows if lbl == 'ELEMENT']
        print(f"  item {iid:<3} {info[iid]['file']:<12} ELEMENT -> "
              f"{', '.join(ELEMENT_NAMES.get(int(e), e) for e in el)}")
    elements = [h for h in harvested if h[0] == 'ELEMENT']
    vfx = [h for h in harvested if h[0] == 'VFX']
    print(f"  harvested {len(elements)} ELEMENT rows and {len(vfx)} VFX rows")
    if len(elements) != 6:
        fail('stage 2', f'expected 6 ELEMENT rows, got {len(elements)}')

    print()
    print("=" * 70)
    print("STAGE 3  build the Omni Ring")
    print("=" * 70)
    rec = info[TARGET_ITEM_ID]
    raw = herf.read(rec['file'])
    before = [(l, v['Data'], v['SData1']) for l, v in parse_2da(raw).rows]
    print(f"  base item: {rec['file']}  rows before: {[b[0] for b in before]}")

    for lbl, vals in vfx + elements:
        raw, _ = add_row(raw, lbl, vals)
    storage = herf.replace(rec['file'], raw)

    t = parse_2da(herf.read(rec['file']))
    got_el = sorted(int(v['SData1']) for l, v in t.rows if l == 'ELEMENT')
    got_pow = [v['Data'] for l, v in t.rows if l == 'POW+']
    print(f"  rows after : {len(t.rows)} total")
    print(f"  ELEMENT ids: {got_el}  -> {[ELEMENT_NAMES[e] for e in got_el]}")
    print(f"  POW+ kept  : {got_pow}")
    print(f"  [{storage}]")
    if got_el != sorted(ELEMENT_NAMES):
        fail('stage 3', f'element set is {got_el}, expected {sorted(ELEMENT_NAMES)}')
    if got_pow != ['5']:
        fail('stage 3', f'POW+ is {got_pow}, expected 5 (it must be preserved)')

    # Rename + redescribe
    tlk.set_string(tlk.index_of_id(rec['name_ref']), NEW_NAME)
    tlk.set_string(tlk.index_of_id(rec['desc_ref']), NEW_DESC)
    print(f"  renamed to {NEW_NAME!r}, description rewritten")

    probs = herf.validate()
    if probs:
        fail('stage 3', f'archive invalid: {probs[:3]}')

    print()
    print("=" * 70)
    print("STAGE 4  rebuild + verify from the rebuilt ROM")
    print("=" * 70)
    new_rom, br = rom.build({herf_fid: herf.serialize(), tlk_fid: tlk.serialize()})
    out_rom = os.path.join(out_dir, 'sonic_chronicles_omniring.nds')
    with open(out_rom, 'wb') as f:
        f.write(new_rom)
    print(f"  wrote {out_rom}  (CRC32 {zlib.crc32(new_rom) & 0xFFFFFFFF:08X}, "
          f"files moved {br['moved_files']})")

    rebuilt = Rom(new_rom)
    rb = HerfFile(rebuilt.file_bytes(rebuilt.file_id(ARCHIVE)))
    t2 = parse_2da(rb.read(rec['file']))
    el2 = sorted(int(v['SData1']) for l, v in t2.rows if l == 'ELEMENT')
    pow2 = [v['Data'] for l, v in t2.rows if l == 'POW+']
    print(f"  read back: ELEMENT {el2}, POW+ {pow2}")
    if el2 != sorted(ELEMENT_NAMES) or pow2 != ['5']:
        fail('stage 4', 'the Omni Ring did not survive the rebuild')

    gt = GFF4(rebuilt.file_bytes(rebuilt.file_id(TLK_PATH)))
    strings = {e[19002]: e[19003] for e in gt.root()[19001] if e[19003]}
    print(f"  name       : {strings.get(rec['name_ref'])!r}")
    print(f"  description: {strings.get(rec['desc_ref'], '')[:78]!r}")
    if strings.get(rec['name_ref']) != NEW_NAME:
        fail('stage 4', 'rename did not survive')

    bad = [n for i, n in rb.names.items()
           if n.lower().endswith(('.itm', '.spl')) and not _ok(rb, i)]
    print(f"  all .itm/.spl tables still parse: {not bad}")
    if bad:
        fail('stage 4', f'{len(bad)} tables broke')

    print()
    print("=" * 70)
    print("STAGE 5  patch")
    print("=" * 70)
    patch = bps.create(original, new_rom, json.dumps({'kind': 'Omni Ring'}).encode())
    out_patch = os.path.join(out_dir, 'sonic_chronicles_omniring.bps')
    with open(out_patch, 'wb') as f:
        f.write(patch)
    if bps.apply(original, patch) != new_rom:
        fail('stage 5', 'patch does not reproduce the ROM')
    print(f"  wrote {out_patch} ({len(patch)} bytes), verified")

    with open(os.path.join(out_dir, 'build_report_omniring.json'), 'w', encoding='utf-8') as f:
        json.dump({'generated': time.strftime('%Y-%m-%d %H:%M:%S'),
                   'experiment': 'does the engine honour more than one ELEMENT row on an item?',
                   'target_item': TARGET_ITEM_ID, 'file': rec['file'],
                   'elements': el2, 'pow_kept': pow2,
                   'output_rom': os.path.abspath(out_rom),
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
