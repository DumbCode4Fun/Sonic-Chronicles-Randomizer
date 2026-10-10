"""
Diagnostic build: a deliberately unmissable, inventory-independent test of
whether the engine actually reads the item tables we can now edit.

Why this exists: the targeted demonstration mod changed one item (LightSlippers),
which is useless as a test if the player doesn't happen to own it. This instead
sets **every positive stat bonus on every item** to a single obvious value, so
whatever the player has equipped or carries will show it.

It also keeps the dialogue edit, giving two independent signals from one ROM: if
the dialogue line changes but no item does, the loose-file write path works and
the archive path does not — which would be a far more useful result than a vague
"nothing happened".

This is a **test build, not a mod** — the values are intentionally absurd. It
exists to answer one question and should not be played seriously.

Safety: source ROM read-only, output to --out-dir (default `build/`).

Usage:
    py build_diagnostic.py <rom.nds> [--value 99] [--out-dir build]
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
from tlk_write import TlkFile  # noqa: E402
from herf_write import HerfFile  # noqa: E402
from twoda_write import set_cell  # noqa: E402
from twoda import parse_2da  # noqa: E402
from gff4 import GFF4  # noqa: E402

ARCHIVE = '/test.herf'
TLK_PATH = '/strings.tlk'
DIALOGUE_ID = 6676
DIALOGUE_TEXT = "Don't worry. Those are just drones. They won't fight. [MODDED]"

# Positive stat-modifier row labels seen across the item tables. Negative rows
# (ATK-, DEF-) and non-stat rows are left alone: the point is an obvious buff.
BUFF_LABELS = {
    'ATK+', 'ATK++', 'DEF+', 'DEF++', 'SPD+', 'LCK+', 'POW+', 'POW++',
    'GRT+', 'GRT++', 'MAXHP+', 'MAXHP++', 'MAXFP+', 'FPMAX+', 'HPMAX+',
    'HP+', 'FP+', 'AP+',
}


def fail(stage, msg):
    print(f"\n!! ABORTED at {stage}: {msg}")
    sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    rom_path = sys.argv[1]
    value = '99'
    out_dir = 'build'
    if '--value' in sys.argv:
        value = sys.argv[sys.argv.index('--value') + 1]
    if '--out-dir' in sys.argv:
        out_dir = sys.argv[sys.argv.index('--out-dir') + 1]
    os.makedirs(out_dir, exist_ok=True)

    report = {'generated': time.strftime('%Y-%m-%d %H:%M:%S'),
              'source_rom': os.path.abspath(rom_path),
              'kind': 'diagnostic test build', 'buff_value': value}

    print("=" * 70)
    print("STAGE 1  validate source")
    print("=" * 70)
    with open(rom_path, 'rb') as f:
        original = f.read()
    rom = Rom(original)
    print(f"  source: {len(original)} bytes, CRC32 {zlib.crc32(original) & 0xFFFFFFFF:08X}")
    if not verify_noop(rom_path):
        fail('stage 1', 'no-op rebuild is not byte-identical')

    print()
    print("=" * 70)
    print(f"STAGE 2  set every positive item stat bonus to {value}")
    print("=" * 70)
    herf_fid = rom.file_id(ARCHIVE)
    herf = HerfFile(herf_fid and rom.file_bytes(herf_fid))
    items = sorted(n for n in herf.names.values() if n.lower().endswith('.itm'))
    changed_rows = 0
    changed_items = []
    grew = 0
    for name in items:
        raw = herf.read(name)
        table = parse_2da(raw)
        touched = []
        for label, vals in table.rows:
            if label in BUFF_LABELS and vals.get('Data') not in (None, value):
                try:
                    raw, note = set_cell(raw, label, 'Data', value)
                    touched.append(label)
                    changed_rows += 1
                except Exception as e:
                    fail('stage 2', f'{name} {label}: {e}')
        if touched:
            storage = herf.replace(name, raw)
            if 'append' in storage:
                grew += 1
            changed_items.append({'item': name, 'rows': touched})
    print(f"  items examined : {len(items)}")
    print(f"  items changed  : {len(changed_items)}")
    print(f"  stat rows set  : {changed_rows}")
    print(f"  items needing the append path (grew): {grew}")

    probs = herf.validate()
    if probs:
        fail('stage 2', f'archive invalid after edits: {probs[:3]}')
    new_archive = herf.serialize()
    print(f"  archive: {len(rom.file_bytes(herf_fid))} -> {len(new_archive)} bytes, validation clean")
    report['items_changed'] = len(changed_items)
    report['stat_rows_changed'] = changed_rows

    print()
    print("=" * 70)
    print("STAGE 3  dialogue edit (second, independent signal)")
    print("=" * 70)
    tlk_fid = rom.file_id(TLK_PATH)
    tlk = TlkFile(rom.file_bytes(tlk_fid))
    idx = tlk.index_of_id(DIALOGUE_ID)
    note = tlk.set_string(idx, DIALOGUE_TEXT)
    new_tlk = tlk.serialize()
    print(f"  dialogue id {DIALOGUE_ID}: [{note}]")

    print()
    print("=" * 70)
    print("STAGE 4  rebuild + verify")
    print("=" * 70)
    new_rom_bytes, br = rom.build({herf_fid: new_archive, tlk_fid: new_tlk})
    out_rom = os.path.join(out_dir, 'sonic_chronicles_diagnostic.nds')
    with open(out_rom, 'wb') as f:
        f.write(new_rom_bytes)
    print(f"  wrote {out_rom}")
    print(f"  CRC32 {zlib.crc32(new_rom_bytes) & 0xFFFFFFFF:08X}, files moved {br['moved_files']}")

    rebuilt = Rom(new_rom_bytes)
    rb = HerfFile(rebuilt.file_bytes(rebuilt.file_id(ARCHIVE)))
    if rb.count != herf.count:
        fail('stage 4', 'resource count changed')
    # spot-check a sample of changed items by reading them back
    sample = [c['item'] for c in changed_items[:6]]
    for name in sample:
        t = parse_2da(rb.read(name))
        got = {lbl: v['Data'] for lbl, v in t.rows if lbl in BUFF_LABELS}
        bad = {k: v for k, v in got.items() if v != value}
        nm = next((n for n, r in [(c['item'], c['rows']) for c in changed_items] if n == name), name)
        print(f"  {nm:14} buffs read back: {got}  {'OK' if not bad else 'MISMATCH ' + str(bad)}")
        if bad:
            fail('stage 4', f'{name} did not read back correctly')
    # every item table must still parse
    bad_items = []
    for i, name in rb.names.items():
        if name.lower().endswith(('.itm', '.spl')):
            try:
                parse_2da(rb.read(i))
            except Exception as e:
                bad_items.append((name, str(e)))
    print(f"  all .itm/.spl tables still parse: {not bad_items} "
          f"({'none failed' if not bad_items else bad_items[:3]})")
    if bad_items:
        fail('stage 4', f'{len(bad_items)} tables broke')
    g = GFF4(rebuilt.file_bytes(rebuilt.file_id(TLK_PATH)))
    got = g.root()[19001][idx][19003]
    print(f"  dialogue reads back: {got == DIALOGUE_TEXT}")
    if got != DIALOGUE_TEXT:
        fail('stage 4', 'dialogue edit did not survive')

    print()
    print("=" * 70)
    print("STAGE 5  patch")
    print("=" * 70)
    patch = bps.create(original, new_rom_bytes,
                       json.dumps({'kind': 'diagnostic', 'buff': value}).encode())
    out_patch = os.path.join(out_dir, 'sonic_chronicles_diagnostic.bps')
    with open(out_patch, 'wb') as f:
        f.write(patch)
    if bps.apply(original, patch) != new_rom_bytes:
        fail('stage 5', 'patch does not reproduce the ROM')
    print(f"  wrote {out_patch} ({len(patch)} bytes), verified")
    report['output_rom'] = os.path.abspath(out_rom)
    report['output_patch'] = os.path.abspath(out_patch)
    report['patch_bytes'] = len(patch)

    with open(os.path.join(out_dir, 'build_report_diagnostic.json'), 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)

    print()
    print("=" * 70)
    print("ALL STAGES PASSED")
    print("=" * 70)
    print(f"  diagnostic ROM: {out_rom}")
    print(f"  {changed_rows} stat rows across {len(changed_items)} items set to {value}")


if __name__ == '__main__':
    main()
