"""
Custom Chao — repurpose the five now-redundant resistance Chao.

The elemental-Chao build gave every attack Chao (10-15) its own matching
resistance, which makes the five resistance-only Chao (16-20) redundant: they
grant a resistance you can now get from the elemental Chao that also deals that
element, plus a small `GRT+`.

That redundancy is valuable, because those five Chao are **already obtainable in
game**. We cannot create new Chao — adding one needs a new archive resource
(unsupported) and the garden/egg system would have to know how to hand it out —
but redefining five existing, reachable ones gives us five genuinely new Chao for
free.

Each is built only from mechanics already confirmed in this project, and spans the
three existing tiers:

    Chao 16  Prism    all six attack elements          (+POW by tier)
    (names are bare, like every other Chao in the game - "Seggo", "Baki" - rather
     than "Prism Chao", which reads oddly in the inventory list)
    Chao 17  Aegis    all six resistances              (strength by tier)
    Chao 18  Fortune  heavy LCK (critical hits)
    Chao 19  Tempo    speed, and +1 action per turn     (stat 123)
    Chao 20  Thrift   cheaper POW moves (stat 122) and more PP

Existing effect rows are neutralised (set to 0) rather than deleted, and the new
rows appended — the 2DA reader is positional by `SData1`, so a zeroed row is inert.
Names and descriptions are rewritten through the `Items.GDA` strrefs.

Note on balance: `NUMACTIONS+` (an extra action every turn) appears on only three
abilities in the whole vanilla game and is probably the strongest effect available.
Tempo is deliberately the standout; treat it as a design choice to revisit rather
than a balanced default.

Usage:
    py build_custom_chao.py <rom.nds> [--out-dir build]
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
from twoda_write import set_cell, add_row  # noqa: E402
from twoda import parse_2da  # noqa: E402
from gff4 import GFF4, read_gda  # noqa: E402

ARCHIVE = '/test.herf'
TLK_PATH = '/strings.tlk'

ATTACK_ELEMENTS = [107, 108, 109, 110, 111, 112]
RESIST_ELEMENTS = [75, 76, 77, 78, 79, 80]
SPD, ATK, DEF, POW, GRT, LCK, PP = 21, 22, 23, 25, 26, 27, 28
COMBODISCOUNT, NUMACTIONS = 122, 123

# Chao display-name group -> (new name, builder(tier) -> [(label, stat, value)], description)
def prism(t):
    return [('ELEMENT', e, 1) for e in ATTACK_ELEMENTS] + [('POW+', POW, t)]

def aegis(t):
    return [('ELEMENT', e, 25 * t) for e in RESIST_ELEMENTS]

def fortune(t):
    # LCK is the most under-served stat the vanilla roster covers: only 3 Chao
    # grant it, none above +3. Luck drives critical hits, so this is a real niche
    # rather than a fifth damage Chao.
    return [('LCK+', LCK, 4 * t)]

def tempo(t):
    return [('SPD+', SPD, 2 * t), ('NUMACTIONS+', NUMACTIONS, 1)]

def thrift(t):
    return [('COMBODISCOUNT+', COMBODISCOUNT, t), ('FP+', PP, 2 * t)]

PLAN = {
    'Chao 16': ('Prism', prism,
                "Bonded character's attacks carry every element at once."),
    'Chao 17': ('Aegis', aegis,
                "Bonded character resists every element."),
    'Chao 18': ('Fortune', fortune,
                "Bonded character lands critical hits far more often."),
    'Chao 19': ('Tempo', tempo,
                "Bonded character is faster and acts an extra time each turn."),
    'Chao 20': ('Thrift', thrift,
                "Bonded character's POW Moves cost less, and it has more PP."),
}
TIER_BY_ID = {}      # filled in from the item ids: 106-110 = t1, 146-150 = t2, 186-190 = t3


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
    strings = {}
    gt = GFF4(rom.file_bytes(tlk_fid))
    for e in gt.root()[19001]:
        if e[19003]:
            strings[e[19002]] = e[19003]

    # Chao display names come from Chaos.GDA (the species table), NOT Items.GDA.
    # Map tier-1 item id -> that species' name strref so renaming actually shows.
    cg = GFF4(herf.read('Chaos.GDA'))
    ccols, crows = read_gda(cg)
    CK = sorted(crows[0].keys())
    species_nameref = {}
    for cr in crows:
        v = [cr[k] for k in CK]
        for item_id in (v[6], v[7], v[8]):
            species_nameref[item_id] = v[1]

    targets = []
    for r in rows:
        iid, nref, dref, typ, sub, base = (r[K[i]] for i in range(6))
        name = strings.get(nref, '')
        if typ == 3 and name in PLAN and base and base != 'None':
            key = lower.get(str(base).lower())
            if key:
                tier = 1 if iid < 140 else (2 if iid < 180 else 3)
                targets.append((iid, name, key, nref, dref, tier))
    targets.sort()
    print(f"  redundant resistance Chao found: {len(targets)}")
    if len(targets) != 15:
        fail('stage 1', f'expected 15 (5 types x 3 tiers), got {len(targets)}')

    print()
    print("=" * 70)
    print("STAGE 2  redefine them")
    print("=" * 70)
    changed = []
    renamed = set()
    for iid, oldname, key, nref, dref, tier in targets:
        newname, builder, desc = PLAN[oldname]
        raw = herf.read(key)
        t = parse_2da(raw)
        # Neutralise existing effect rows
        for lbl, v in t.rows:
            if lbl in ('SpellData', 'CollectionData_Equip', 'CollectionData_Use'):
                continue
            if v.get('Data') not in (None, '0'):
                raw, _ = set_cell(raw, lbl, 'Data', '0', allow_noop=True)
        # Append the new effect set
        spec = builder(tier)
        for lbl, stat, val in spec:
            raw, _ = add_row(raw, lbl, {'EffectId': '1', 'Data': str(val),
                                        'SData1': str(stat), 'SData2': '0',
                                        'SData3': '0', 'Pulse': '-1'})
        herf.replace(key, raw)
        # description comes from the item; name comes from the species table
        tlk.set_string(tlk.index_of_id(dref), desc)
        sref = species_nameref.get(iid)
        if sref is not None and sref not in renamed:
            tlk.set_string(tlk.index_of_id(sref), newname)
            renamed.add(sref)
        pretty = ', '.join(f'{l}{v:+d}' if l != 'ELEMENT' else f'el{stat}={v}'
                           for l, stat, v in spec)
        print(f"  id={iid:<4} {oldname:<8} -> {newname} {tier:<2} : {pretty[:62]}")
        changed.append({'id': iid, 'was': oldname, 'now': f'{newname} {tier}',
                        'effects': [(l, s, v) for l, s, v in spec]})

    probs = herf.validate()
    if probs:
        fail('stage 2', f'archive invalid: {probs[:3]}')

    print()
    print("=" * 70)
    print("STAGE 3  rebuild + verify from the rebuilt ROM")
    print("=" * 70)
    new_rom, br = rom.build({herf_fid: herf.serialize(), tlk_fid: tlk.serialize()})
    out_rom = os.path.join(out_dir, 'sonic_chronicles_customchao.nds')
    with open(out_rom, 'wb') as f:
        f.write(new_rom)
    print(f"  wrote {out_rom}  (CRC32 {zlib.crc32(new_rom) & 0xFFFFFFFF:08X}, "
          f"files moved {br['moved_files']})")

    rebuilt = Rom(new_rom)
    rb = HerfFile(rebuilt.file_bytes(rebuilt.file_id(ARCHIVE)))
    for c in changed:
        key = next(k for i, n, k, a, b, t in targets if i == c['id'])
        t2 = parse_2da(rb.read(key))
        live = {}
        for lbl, v in t2.rows:
            if lbl in ('SpellData', 'CollectionData_Equip', 'CollectionData_Use'):
                continue
            try:
                sid, val = int(v['SData1']), int(v['Data'])
            except (TypeError, ValueError):
                continue
            if val != 0:
                live[sid] = val
        want = {s: v for l, s, v in c['effects']}
        if live != want:
            fail('stage 3', f"item {c['id']} reads {live}, expected {want}")
    print(f"  all {len(changed)} redefined Chao read back correctly")

    gt2 = GFF4(rebuilt.file_bytes(rebuilt.file_id(TLK_PATH)))
    s2 = {e[19002]: e[19003] for e in gt2.root()[19001] if e[19003]}
    print('  species renamed (as shown in game):')
    for iid, oldname, key, nref, dref, tier in targets:
        sref = species_nameref.get(iid)
        if sref is not None and tier == 1:
            print(f"     item {iid}: {s2.get(sref)!r}  desc {s2.get(dref, '')[:48]!r}")

    bad = [n for i, n in rb.names.items()
           if n.lower().endswith(('.itm', '.spl')) and not _ok(rb, i)]
    print(f"  all .itm/.spl tables still parse: {not bad}")
    if bad:
        fail('stage 3', f'{len(bad)} tables broke')

    print()
    print("=" * 70)
    print("STAGE 4  patch")
    print("=" * 70)
    patch = bps.create(original, new_rom, json.dumps({'kind': 'custom Chao'}).encode())
    out_patch = os.path.join(out_dir, 'sonic_chronicles_customchao.bps')
    with open(out_patch, 'wb') as f:
        f.write(patch)
    if bps.apply(original, patch) != new_rom:
        fail('stage 4', 'patch does not reproduce the ROM')
    print(f"  wrote {out_patch} ({len(patch)} bytes), verified")

    with open(os.path.join(out_dir, 'build_report_customchao.json'), 'w', encoding='utf-8') as f:
        json.dump({'generated': time.strftime('%Y-%m-%d %H:%M:%S'),
                   'mod': 'redundant resistance Chao redefined as five custom Chao',
                   'chao': changed, 'output_rom': os.path.abspath(out_rom),
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
