"""
Phase 8, first real mod: rebalance the footwear chain, and demonstrate combined
effects on a single item.

The problem (measured, see REVERSE_ENGINEERING_LOG.md): 20 of 21 stat-bearing
footwear items are **strictly dominated** — another item in the slot is equal or
better on every stat. The slot is a linear upgrade chain with no decision in it.

The design: footwear comes in four families that read as tiers —
**Slippers < Hydraulics < Sneakers < Boots** — each with five items. Keep the
progression *between* families, but give each family five **distinct roles** so
there is a real choice *within* a tier:

    role       profile at tier T          reads as
    Balanced   DEF +T,  GRT +T            all-rounder
    Guardian   GRT +3T, DEF -T            maximum armor, poor defense
    Swift      SPD +3T, GRT -T            speed at the cost of armor
    Striker    POW +3T, DEF -T            damage at the cost of defense
    Armor      DEF +3T, GRT -T            defense at the cost of armor

No role dominates another within a tier: each trades a strength for a weakness,
and Swift/Striker use stats the others do not touch. Later families remain
stronger than earlier ones, which is ordinary progression rather than the absence
of choice.

Roles are assigned to match each item's existing name, so the rebalance still
reads sensibly ("Tough Slippers" stays the armor one, "Speedy Sneakers" the fast
one) and the descriptions are rewritten to match the new numbers via the item's
`description` strref in `Items.GDA`.

**Combination demonstration:** Speedy Sneakers additionally gain a Fire elemental
attack row (`ELEMENT=1`, stat 107) — the same effect the Fire Ring grants. This
proves effects are freely composable across item categories: an item's `.itm` is
simply a list of effect records, so a "combined" accessory is just one carrying
more rows. Nothing about the engine restricts a footwear item to footwear-ish
effects.

Usage:
    py build_footwear.py <rom.nds> [--out-dir build]
"""
import json
import os
import re
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
from twoda_write import set_cell, add_row  # noqa: E402
from twoda import parse_2da  # noqa: E402
from gff4 import GFF4, read_gda  # noqa: E402

ARCHIVE = '/test.herf'
TLK_PATH = '/strings.tlk'

# stat ids
SPD, ATK, DEF, POW, GRT, LCK = 21, 22, 23, 25, 26, 27
FIRE_ATTACK = 107

# item id -> (family tier, role).  Roles chosen to match the existing names.
TIERS = {'slippers': 1, 'hydraulics': 2, 'sneakers': 3, 'boots': 4}
PLAN = {
    22: ('slippers', 'Balanced'), 23: ('slippers', 'Guardian'),
    24: ('slippers', 'Swift'),    25: ('slippers', 'Striker'),
    26: ('slippers', 'Armor'),
    27: ('hydraulics', 'Swift'),  28: ('hydraulics', 'Guardian'),
    29: ('hydraulics', 'Armor'),  30: ('hydraulics', 'Striker'),
    31: ('hydraulics', 'Balanced'),
    32: ('sneakers', 'Balanced'), 33: ('sneakers', 'Guardian'),
    34: ('sneakers', 'Swift'),    35: ('sneakers', 'Striker'),
    36: ('sneakers', 'Armor'),
    37: ('boots', 'Balanced'),    38: ('boots', 'Guardian'),
    39: ('boots', 'Swift'),       40: ('boots', 'Striker'),
    41: ('boots', 'Armor'),
}
ROLE_TEXT = {
    'Balanced': 'A dependable all-rounder. Modestly increases defense and armor.',
    'Guardian': 'Heavily reinforced. Greatly increases armor at the cost of defense.',
    'Swift':    'Built for speed. Greatly increases speed at the cost of armor.',
    'Striker':  'Weighted for impact. Greatly increases damage at the cost of defense.',
    'Armor':    'Plated and solid. Greatly increases defense at the cost of armor.',
}


def profile(tier, role):
    """Return {stat_id: delta} for a role at a tier."""
    t = TIERS[tier]
    return {
        'Balanced': {DEF: t, GRT: t},
        'Guardian': {GRT: 3 * t, DEF: -t},
        'Swift':    {SPD: 3 * t, GRT: -t},
        'Striker':  {POW: 3 * t, DEF: -t},
        'Armor':    {DEF: 3 * t, GRT: -t},
    }[role]


LABEL = {SPD: 'SPD', ATK: 'ATK', DEF: 'DEF', POW: 'POW', GRT: 'GRT', LCK: 'LCK'}


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

    # Map item id -> (.itm resource, name, description strref) via Items.GDA
    size, off = herf.entry(herf.index_of('Items.GDA'))[1], 0
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

    print()
    print("=" * 70)
    print("STAGE 2  rebalance footwear")
    print("=" * 70)
    changed = []
    for iid, (tier, role) in sorted(PLAN.items()):
        if iid not in info:
            fail('stage 2', f'item {iid} not found in Items.GDA')
        rec = info[iid]
        raw = herf.read(rec['file'])
        table = parse_2da(raw)
        name = (table.get('SpellData') or {}).get('Data', '?')
        want = profile(tier, role)

        # Rewrite the stat rows this item already has; add any that are missing.
        existing = {}
        for lbl, v in table.rows:
            if lbl in ('SpellData', 'CollectionData_Equip', 'CollectionData_Use'):
                continue
            try:
                sid = int(v['SData1'])
            except (TypeError, ValueError):
                continue
            if sid in LABEL:
                existing.setdefault(sid, lbl)

        for sid, delta in want.items():
            if sid in existing:
                lbl = existing[sid]
                raw, _ = set_cell(raw, lbl, 'Data', str(delta), allow_noop=True)
            else:
                lbl = LABEL[sid] + ('+' if delta >= 0 else '-')
                if any(l == lbl for l, _ in parse_2da(raw).rows):
                    lbl = LABEL[sid] + '_' + role[:3]
                raw, _ = add_row(raw, lbl, {'EffectId': '1', 'Data': str(delta),
                                            'SData1': str(sid), 'SData2': '0',
                                            'SData3': '0', 'Pulse': '-1'})
        # Neutralise any stat rows the new profile does not use.
        for sid, lbl in existing.items():
            if sid not in want:
                raw, _ = set_cell(raw, lbl, 'Data', '0', allow_noop=True)

        # The combination demonstration rides on Speedy Sneakers.
        combo = ''
        if iid == 34:
            raw, _ = add_row(raw, 'ELEMENT', {'EffectId': '1', 'Data': '1',
                                              'SData1': str(FIRE_ATTACK),
                                              'SData2': '0', 'SData3': '0', 'Pulse': '-1'})
            combo = ' + Fire attack'

        herf.replace(rec['file'], raw)

        # Rewrite the description to match the new numbers.
        desc = ROLE_TEXT[role]
        if combo:
            desc += ' Infused with the power of inferno: gives Fire damage to basic attacks.'
        try:
            didx = tlk.index_of_id(rec['desc_ref'])
            tlk.set_string(didx, desc)
        except KeyError:
            desc = '(description strref not uniquely resolvable; left unchanged)'

        got = {}
        for lbl, v in parse_2da(herf.read(rec['file'])).rows:
            if lbl in ('SpellData', 'CollectionData_Equip', 'CollectionData_Use'):
                continue
            try:
                sid = int(v['SData1'])
            except (TypeError, ValueError):
                continue
            if sid in LABEL and int(v['Data']) != 0:
                got[LABEL[sid]] = int(v['Data'])
        print(f"  {iid:<4} {name:<20} {tier:<11} {role:<9} -> {got}{combo}")
        changed.append({'id': iid, 'name': name, 'tier': tier, 'role': role,
                        'stats': got, 'combo': bool(combo)})

    probs = herf.validate()
    if probs:
        fail('stage 2', f'archive invalid: {probs[:3]}')

    print()
    print("=" * 70)
    print("STAGE 3  check the chain is no longer dominated")
    print("=" * 70)
    ALL = ['SPD', 'ATK', 'DEF', 'POW', 'GRT', 'LCK']
    byfam = {}
    for c in changed:
        byfam.setdefault(c['tier'], []).append(c)
    total_dom = 0
    for fam, items in byfam.items():
        dom = set()
        for a in items:
            for b in items:
                if a is b:
                    continue
                va = [a['stats'].get(s, 0) for s in ALL]
                vb = [b['stats'].get(s, 0) for s in ALL]
                if all(x >= y for x, y in zip(va, vb)) and any(x > y for x, y in zip(va, vb)):
                    dom.add(b['id'])
        print(f"  {fam:<11} {len(items)} items, {len(dom)} dominated within the family")
        total_dom += len(dom)
    print(f"  within-family domination total: {total_dom} (was effectively total before)")
    if total_dom:
        fail('stage 3', 'the rebalance still leaves dominated items within a family')

    print()
    print("=" * 70)
    print("STAGE 4  rebuild + verify from the rebuilt ROM")
    print("=" * 70)
    new_rom, br = rom.build({herf_fid: herf.serialize(), tlk_fid: tlk.serialize()})
    out_rom = os.path.join(out_dir, 'sonic_chronicles_footwear.nds')
    with open(out_rom, 'wb') as f:
        f.write(new_rom)
    print(f"  wrote {out_rom}  (CRC32 {zlib.crc32(new_rom) & 0xFFFFFFFF:08X}, "
          f"files moved {br['moved_files']})")

    rebuilt = Rom(new_rom)
    rb = HerfFile(rebuilt.file_bytes(rebuilt.file_id(ARCHIVE)))
    for c in changed:
        rec = info[c['id']]
        got = {}
        for lbl, v in parse_2da(rb.read(rec['file'])).rows:
            if lbl in ('SpellData', 'CollectionData_Equip', 'CollectionData_Use'):
                continue
            try:
                sid = int(v['SData1'])
            except (TypeError, ValueError):
                continue
            if sid in LABEL and int(v['Data']) != 0:
                got[LABEL[sid]] = int(v['Data'])
        if got != c['stats']:
            fail('stage 4', f"item {c['id']} reads back {got}, expected {c['stats']}")
    print(f"  all {len(changed)} footwear items read back correctly")

    t34 = parse_2da(rb.read(info[34]['file']))
    el = [v for l, v in t34.rows if l == 'ELEMENT']
    print(f"  Speedy Sneakers ELEMENT row: {el[0] if el else 'MISSING'}")
    if not el or el[0]['SData1'] != str(FIRE_ATTACK):
        fail('stage 4', 'the combined Fire attack row did not survive')

    gt = GFF4(rebuilt.file_bytes(rebuilt.file_id(TLK_PATH)))
    strings = {e[19002]: e[19003] for e in gt.root()[19001] if e[19003]}
    print(f"  Speedy Sneakers description: {strings.get(info[34]['desc_ref'], '')[:88]!r}")

    bad = [n for i, n in rb.names.items() if n.lower().endswith(('.itm', '.spl'))
           and not _ok(rb, i)]
    print(f"  all .itm/.spl tables still parse: {not bad}")
    if bad:
        fail('stage 4', f'{len(bad)} tables broke')

    print()
    print("=" * 70)
    print("STAGE 5  patch")
    print("=" * 70)
    patch = bps.create(original, new_rom,
                       json.dumps({'kind': 'footwear rebalance + combo demo'}).encode())
    out_patch = os.path.join(out_dir, 'sonic_chronicles_footwear.bps')
    with open(out_patch, 'wb') as f:
        f.write(patch)
    if bps.apply(original, patch) != new_rom:
        fail('stage 5', 'patch does not reproduce the ROM')
    print(f"  wrote {out_patch} ({len(patch)} bytes), verified")

    with open(os.path.join(out_dir, 'build_report_footwear.json'), 'w', encoding='utf-8') as f:
        json.dump({'generated': time.strftime('%Y-%m-%d %H:%M:%S'),
                   'mod': 'footwear rebalance + combined-effect demonstration',
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
