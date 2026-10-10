"""
Combined build: applies **both** a loose-ROM-file edit (dialogue, in
`strings.tlk`) and archive-content edits (inside `/test.herf`) in a single ROM
rebuild, so all four demonstration changes can be tested in one emulator session.

This is the first build that exercises both write paths at once, which is the
case that actually matters: the TLK grows, which shifts later ROM files —
including the archive we also edited. Both replacements go into one
`Rom.build()` call so offsets are resolved together rather than in two passes.

Changes applied:
  1. dialogue id 6676          -> appended "[MODDED]"      (loose file, TLK)
  2. Spell_Tough.spl  GRT+     10 -> 20                    (archive, text 2DA)
  3. Item22.ITM       DEF+     1 -> 5   (LightSlippers)    (archive, text 2DA)
  4. Adv_Shadow.GDA   xp       464/872 -> 200/490          (archive, binary GDA)

Safety: source ROM opened read-only, never written. Output to --out-dir
(default `build/`). Any verification failure aborts.

NOTE (known debt): this is the third driver sharing the same stage scaffolding as
`build.py` and `build_mod.py`. They should eventually collapse into one
profile-driven builder — that is roadmap Phase 17 (mod profiles), deliberately
not built yet.

Usage:
    py build_combined.py <rom.nds> [--out-dir build]
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
from tlk_write import TlkFile, NO_STRING  # noqa: E402
from herf_write import HerfFile  # noqa: E402
from twoda_write import set_cell  # noqa: E402
from gda_write import set_int_cell  # noqa: E402
from twoda import parse_2da  # noqa: E402
from gff4 import GFF4, read_gda  # noqa: E402

TLK_PATH = '/strings.tlk'
ARCHIVE = '/test.herf'
DIALOGUE_ID = 6676
DIALOGUE_TEXT = "Don't worry. Those are just drones. They won't fight. [MODDED]"
CONTROL_RESOURCE = 'Item10.ITM'
TLK_LIST, TLK_ID, TLK_TEXT = 19001, 19002, 19003


def fail(stage, msg):
    print(f"\n!! ABORTED at {stage}: {msg}")
    sys.exit(1)


def load_column_names(path='research/phase0/gda_columns.tsv'):
    names = {}
    if not os.path.exists(path):
        return names
    with open(path, encoding='utf-8') as f:
        next(f)
        for line in f:
            h, nm, cnt, ex = line.rstrip('\n').split('\t')
            if nm:
                names[int(h)] = nm
    return names


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    rom_path = sys.argv[1]
    out_dir = 'build'
    if '--out-dir' in sys.argv:
        out_dir = sys.argv[sys.argv.index('--out-dir') + 1]
    os.makedirs(out_dir, exist_ok=True)
    col_names = load_column_names()
    report = {'generated': time.strftime('%Y-%m-%d %H:%M:%S'),
              'source_rom': os.path.abspath(rom_path), 'stages': {}, 'edits': []}

    print("=" * 70)
    print("STAGE 1  validate source + no-op rebuild")
    print("=" * 70)
    with open(rom_path, 'rb') as f:
        original = f.read()
    rom = Rom(original)
    src_crc = zlib.crc32(original) & 0xFFFFFFFF
    print(f"  source: {len(original)} bytes, CRC32 {src_crc:08X}, {rom.num_files} files")
    if not verify_noop(rom_path):
        fail('stage 1', 'no-op rebuild is not byte-identical')
    report['source_crc32'] = f"{src_crc:08X}"
    report['stages']['noop_rebuild_identical'] = True

    print()
    print("=" * 70)
    print("STAGE 2  edit dialogue (loose ROM file)")
    print("=" * 70)
    tlk_fid = rom.file_id(TLK_PATH)
    tlk_original = rom.file_bytes(tlk_fid)
    tlk = TlkFile(tlk_original)
    if tlk.serialize() != tlk_original:
        fail('stage 2', 'no-op TLK serialize differs from input')
    idx = tlk.index_of_id(DIALOGUE_ID)
    before = tlk.get_string(idx)
    note = tlk.set_string(idx, DIALOGUE_TEXT)
    print(f"  id {DIALOGUE_ID} (index {idx}): {before!r}")
    print(f"                 -> {DIALOGUE_TEXT!r}  [{note}]")
    report['edits'].append({'target': f'{TLK_PATH} id {DIALOGUE_ID}',
                            'change': 'appended [MODDED]', 'storage': note})
    # untouched control entry, to catch collateral damage
    control_idx = next(i for i in range(tlk.count)
                       if tlk.entry_offset(i) != NO_STRING and i != idx and tlk.get_string(i))
    control_id, control_text = tlk.entry_id(control_idx), tlk.get_string(control_idx)
    new_tlk = tlk.serialize()
    print(f"  TLK: {len(tlk_original)} -> {len(new_tlk)} bytes")

    print()
    print("=" * 70)
    print("STAGE 3  edit archive contents")
    print("=" * 70)
    herf_fid = rom.file_id(ARCHIVE)
    archive_original = rom.file_bytes(herf_fid)
    herf = HerfFile(archive_original)
    if herf.serialize() != archive_original:
        fail('stage 3', 'no-op archive serialize differs from input')
    print(f"  {ARCHIVE}: {len(archive_original)} bytes, {herf.count} resources")
    control_res_before = herf.read(CONTROL_RESOURCE)

    spl = 'Spell_Tough.spl'
    new_spl, n = set_cell(herf.read(spl), 'GRT+', 'Data', '20')
    st = herf.replace(spl, new_spl)
    print(f"  [2] {spl}: {n}  [{st}]")
    report['edits'].append({'target': spl, 'change': n, 'storage': st})

    itm = 'Item22.ITM'
    new_itm, n = set_cell(herf.read(itm), 'DEF+', 'Data', '5')
    st = herf.replace(itm, new_itm)
    print(f"  [3] {itm} (LightSlippers): {n}  [{st}]")
    report['edits'].append({'target': itm, 'change': n, 'storage': st})

    gda = 'Adv_Shadow.GDA'
    raw = herf.read(gda)
    notes = []
    for row, value in ((1, 200), (2, 490)):
        raw, n = set_int_cell(raw, row, 'xp', value, col_names)
        notes.append(n)
    st = herf.replace(gda, raw)
    print(f"  [4] {gda}: {'; '.join(notes)}  [{st}]")
    report['edits'].append({'target': gda, 'change': '; '.join(notes), 'storage': st})

    probs = herf.validate()
    if probs:
        fail('stage 3', f'archive structurally invalid after edits: {probs[:3]}')
    new_archive = herf.serialize()
    print(f"  archive: {len(archive_original)} -> {len(new_archive)} bytes, validation clean")

    print()
    print("=" * 70)
    print("STAGE 4  rebuild ROM with BOTH replacements in one pass")
    print("=" * 70)
    new_rom_bytes, br = rom.build({tlk_fid: new_tlk, herf_fid: new_archive})
    out_rom = os.path.join(out_dir, 'sonic_chronicles_combined.nds')
    with open(out_rom, 'wb') as f:
        f.write(new_rom_bytes)
    tgt_crc = zlib.crc32(new_rom_bytes) & 0xFFFFFFFF
    print(f"  wrote {out_rom}")
    print(f"  {len(new_rom_bytes)} bytes, CRC32 {tgt_crc:08X}")
    print(f"  files moved: {br['moved_files']}   "
          f"total_used: {br['original_total_used']} -> {br['total_used_rom_size']}")
    report['output_rom'] = os.path.abspath(out_rom)
    report['output_crc32'] = f"{tgt_crc:08X}"
    report['files_moved'] = br['moved_files']

    print()
    print("=" * 70)
    print("STAGE 5  verify all four changes from the rebuilt ROM")
    print("=" * 70)
    rebuilt = Rom(new_rom_bytes)

    g = GFF4(rebuilt.file_bytes(rebuilt.file_id(TLK_PATH)))
    entries = g.root()[TLK_LIST]
    if len(entries) != tlk.count:
        fail('stage 5', f'TLK entry count changed: {len(entries)} != {tlk.count}')
    got = entries[idx][TLK_TEXT]
    print(f"  [1] dialogue id {DIALOGUE_ID}: {got!r}")
    if got != DIALOGUE_TEXT or entries[idx][TLK_ID] != DIALOGUE_ID:
        fail('stage 5', 'dialogue edit did not survive')
    if entries[control_idx][TLK_TEXT] != control_text:
        fail('stage 5', f'control dialogue id {control_id} corrupted')
    print(f"      control dialogue id {control_id} unchanged: OK")

    rb_herf = HerfFile(rebuilt.file_bytes(rebuilt.file_id(ARCHIVE)))
    if rb_herf.count != herf.count:
        fail('stage 5', f'resource count changed: {rb_herf.count} != {herf.count}')

    v = parse_2da(rb_herf.read(spl)).get('GRT+')['Data']
    print(f"  [2] {spl} GRT+ = {v!r}  -> {'OK' if v == '20' else 'MISMATCH'}")
    if v != '20':
        fail('stage 5', 'ability edit did not survive')

    v = parse_2da(rb_herf.read(itm)).get('DEF+')['Data']
    print(f"  [3] {itm} DEF+ = {v!r}  -> {'OK' if v == '5' else 'MISMATCH'}")
    if v != '5':
        fail('stage 5', 'item edit did not survive')

    _, rows = read_gda(GFF4(rb_herf.read(gda)))
    xp = [rows[i][10007] for i in range(4)]
    ok = xp[1] == 200 and xp[2] == 490
    print(f"  [4] {gda} xp levels 1-4 = {xp}  -> {'OK' if ok else 'MISMATCH'}")
    if not ok:
        fail('stage 5', 'XP curve edit did not survive')

    if rb_herf.read(CONTROL_RESOURCE) != control_res_before:
        fail('stage 5', f'control resource {CONTROL_RESOURCE} corrupted')
    print(f"  [5] control resource {CONTROL_RESOURCE} unchanged: OK")

    # Regression sweeps over everything that moved or was repacked.
    bad = []
    for i, name in rb_herf.names.items():
        if name.lower().endswith(('.gff', '.gda', '.dlg', '.gui', '.plo', '.are')):
            try:
                GFF4(rb_herf.read(i)).root()
            except Exception as e:
                bad.append((name, str(e)))
    print(f"  [6] all GFF4 resources in repacked archive decode: "
          f"{len(bad) == 0} ({'none failed' if not bad else bad[:3]})")
    if bad:
        fail('stage 5', f'{len(bad)} GFF4 resources broke')

    for p in ['/strings_de-de.tlk', '/strings_fr-fr.tlk', '/strings_es-es.tlk',
              '/strings_it-it.tlk']:
        n = len(GFF4(rebuilt.file_bytes(rebuilt.file_id(p))).root()[TLK_LIST])
        if n != 18845:
            fail('stage 5', f'{p} has {n} entries after the rebuild, expected 18845')
    print("  [7] all four other language TLKs still parse at 18845 entries: OK")
    report['stages']['readback_verified'] = True

    print()
    print("=" * 70)
    print("STAGE 6  generate + verify BPS patch")
    print("=" * 70)
    meta = json.dumps({'project': 'Sonic Chronicles Modding Framework',
                       'build': 'combined demonstration mod',
                       'edits': [e['target'] for e in report['edits']]}).encode()
    patch = bps.create(original, new_rom_bytes, meta)
    out_patch = os.path.join(out_dir, 'sonic_chronicles_combined.bps')
    with open(out_patch, 'wb') as f:
        f.write(patch)
    print(f"  wrote {out_patch} ({len(patch)} bytes for a {len(new_rom_bytes)} byte ROM)")
    if bps.apply(original, patch) != new_rom_bytes:
        fail('stage 6', 'patch does not reproduce the rebuilt ROM')
    print("  patch reproduces the rebuilt ROM exactly: OK")
    report['stages']['patch_verified'] = True
    report['output_patch'] = os.path.abspath(out_patch)
    report['patch_bytes'] = len(patch)

    report_path = os.path.join(out_dir, 'build_report_combined.json')
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)

    print()
    print("=" * 70)
    print("ALL STAGES PASSED")
    print("=" * 70)
    print(f"  combined ROM : {out_rom}")
    print(f"  patch        : {out_patch}  ({len(patch)} bytes)")
    print(f"  report       : {report_path}")
    print("  original ROM untouched (opened read-only)")


if __name__ == '__main__':
    main()
