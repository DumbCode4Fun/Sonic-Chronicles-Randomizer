"""
Elemental Chao overhaul — give each elemental Chao its matching resistance, and
fill a gap the vanilla game left open.

Findings this is built on (see REVERSE_ENGINEERING_LOG.md):
  * Chao are ordinary items (type 3 in `Items.GDA`, each with its own `.itm`).
  * **Attack** Chao 10-15 cover six elements across three tiers:
        tier 1 element only | tier 2 element + POW+1 | tier 3 element + POW+2
  * **Resistance** Chao 16-20 cover only **five** - Fire, Water, Lightning, Wind,
    Earth. There is **no Ice resistance Chao**, and no item grants Ice resistance
    either, so stat 80 is a defined stat with no source anywhere in the game.

The change: every elemental attack Chao also grants the resistance for its own
element, at the same strength the vanilla resistance Chao use (`Data=50`). Each
elemental Chao becomes a coherent package - "the Fire Chao" both deals and
resists Fire - and Chao 13 finally makes Ice resistance obtainable.

Existing rows are untouched: the attack element and the tier's `POW+` are kept, so
this is additive. Descriptions are rewritten through the `Items.GDA` description
strrefs so the items still describe themselves accurately.

Scope note: this **redefines existing Chao**; it cannot create new ones. Adding a
Chao would need a new archive resource (not supported - it changes the resource
table length) and, more fundamentally, the garden/egg system would have to know
how to hand it out.

Usage:
    py build_elemental_chao.py <rom.nds> [--out-dir build]
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

# attack affinity id -> (element name, matching resistance id)
ELEMENTS = {
    107: ('Fire', 75),
    108: ('Water', 76),
    109: ('Earth', 77),
    110: ('Wind', 78),
    111: ('Lightning', 79),
    112: ('Ice', 80),          # the one with no vanilla source
}
RESIST_STRENGTH = '50'        # matches the vanilla resistance Chao


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

    g = GFF4(herf.read('Items.GDA'))
    cols, rows = read_gda(g)
    K = sorted(rows[0].keys())
    lower = {n.lower(): n for n in herf.names.values()}

    print()
    print("=" * 70)
    print("STAGE 2  add matching resistance to every elemental attack Chao")
    print("=" * 70)
    changed = []
    for r in rows:
        iid, nref, dref, typ, sub, base = (r[K[i]] for i in range(6))
        if typ != 3 or not base or base == 'None':
            continue
        key = lower.get(str(base).lower())
        if not key:
            continue
        raw = herf.read(key)
        t = parse_2da(raw)

        attack_ids = []
        resist_ids = []
        for lbl, v in t.rows:
            if lbl in ('SpellData', 'CollectionData_Equip', 'CollectionData_Use'):
                continue
            try:
                sid = int(v['SData1'])
            except (TypeError, ValueError):
                continue
            if sid in ELEMENTS:
                attack_ids.append(sid)
            elif sid in {r for _, r in ELEMENTS.values()}:
                resist_ids.append(sid)
        if not attack_ids:
            continue

        added = []
        for sid in attack_ids:
            name, resist_id = ELEMENTS[sid]
            if resist_id in resist_ids:
                continue
            raw, _ = add_row(raw, 'ELEMENT', {'EffectId': '1', 'Data': RESIST_STRENGTH,
                                              'SData1': str(resist_id), 'SData2': '0',
                                              'SData3': '0', 'Pulse': '-1'})
            added.append(name)
        if not added:
            continue
        herf.replace(key, raw)

        pow_rows = [v['Data'] for l, v in parse_2da(herf.read(key)).rows if l == 'POW+']
        tier = f" (+POW {pow_rows[0]})" if pow_rows else ''
        elname = ELEMENTS[attack_ids[0]][0]
        desc = (f"Bonded character's attacks do {elname} damage, "
                f"and it resists {elname} damage.")
        try:
            tlk.set_string(tlk.index_of_id(dref), desc)
        except KeyError:
            desc = '(description strref not uniquely resolvable)'
        print(f"  id={iid:<4} {str(r[K[1]]) and elname:<10} +{elname} resistance{tier}")
        changed.append({'id': iid, 'file': key, 'element': elname,
                        'added_resistance': added, 'tier_pow': pow_rows})

    print(f"  elemental Chao updated: {len(changed)}")
    if len(changed) != 18:
        fail('stage 2', f'expected 18 elemental attack Chao (6 elements x 3 tiers), got {len(changed)}')
    ice = [c for c in changed if c['element'] == 'Ice']
    print(f"  of which Ice (previously had NO resistance source in the game): {len(ice)}")

    probs = herf.validate()
    if probs:
        fail('stage 2', f'archive invalid: {probs[:3]}')

    print()
    print("=" * 70)
    print("STAGE 3  rebuild + verify from the rebuilt ROM")
    print("=" * 70)
    new_rom, br = rom.build({herf_fid: herf.serialize(), tlk_fid: tlk.serialize()})
    out_rom = os.path.join(out_dir, 'sonic_chronicles_elemchao.nds')
    with open(out_rom, 'wb') as f:
        f.write(new_rom)
    print(f"  wrote {out_rom}  (CRC32 {zlib.crc32(new_rom) & 0xFFFFFFFF:08X}, "
          f"files moved {br['moved_files']})")

    rebuilt = Rom(new_rom)
    rb = HerfFile(rebuilt.file_bytes(rebuilt.file_id(ARCHIVE)))
    resist_ids = {r for _, r in ELEMENTS.values()}
    for c in changed:
        t = parse_2da(rb.read(c['file']))
        sids = set()
        for lbl, v in t.rows:
            try:
                sids.add(int(v['SData1']))
            except (TypeError, ValueError):
                pass
        att = sids & set(ELEMENTS)
        res = sids & resist_ids
        want_res = {ELEMENTS[a][1] for a in att}
        if res != want_res:
            fail('stage 3', f"item {c['id']} has resistances {res}, expected {want_res}")
    print(f"  all {len(changed)} elemental Chao carry their matching resistance: OK")

    # Ice resistance now has a source where it previously had none
    ice_sources = 0
    for i, n in rb.names.items():
        if n.lower().endswith('.itm'):
            try:
                t = parse_2da(rb.read(i))
            except Exception:
                continue
            for lbl, v in t.rows:
                try:
                    if int(v['SData1']) == 80:
                        ice_sources += 1
                        break
                except (TypeError, ValueError):
                    pass
    print(f"  items granting Ice resistance (stat 80), was 0 in vanilla: {ice_sources}")
    if ice_sources == 0:
        fail('stage 3', 'Ice resistance still has no source')

    bad = [n for i, n in rb.names.items()
           if n.lower().endswith(('.itm', '.spl')) and not _ok(rb, i)]
    print(f"  all .itm/.spl tables still parse: {not bad}")
    if bad:
        fail('stage 3', f'{len(bad)} tables broke')

    print()
    print("=" * 70)
    print("STAGE 4  patch")
    print("=" * 70)
    patch = bps.create(original, new_rom, json.dumps({'kind': 'elemental Chao overhaul'}).encode())
    out_patch = os.path.join(out_dir, 'sonic_chronicles_elemchao.bps')
    with open(out_patch, 'wb') as f:
        f.write(patch)
    if bps.apply(original, patch) != new_rom:
        fail('stage 4', 'patch does not reproduce the ROM')
    print(f"  wrote {out_patch} ({len(patch)} bytes), verified")

    with open(os.path.join(out_dir, 'build_report_elemchao.json'), 'w', encoding='utf-8') as f:
        json.dump({'generated': time.strftime('%Y-%m-%d %H:%M:%S'),
                   'mod': 'every elemental Chao also grants its own resistance',
                   'chao_updated': changed, 'ice_resistance_sources': ice_sources,
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
