"""
End-to-end build for mods that change data **inside** `/test.herf` — items,
abilities and the GDA tables. Complements `build.py`, which handles loose ROM
files (dialogue).

Pipeline: ROM -> validate -> open archive -> edit resources -> repack archive ->
rebuild ROM -> verify by reading everything back out of the rebuilt ROM -> BPS
patch -> build report.

The demonstration mod exercises all three editable surfaces and is made of real
changes this project actually wants, not synthetic ones:
  1. ability magnitude  (plain-text 2DA in the archive)
  2. item stat          (plain-text 2DA in the archive)
  3. XP curve           (binary GDA in the archive)

Edit 3 addresses a finding from the progression work: Shadow has the most
expensive early XP curve in the game (464 to reach level 2 against Sonic's 200),
which would make him a sluggish starting character for Shadow Mode. This lowers
his level-2 and level-3 thresholds to Sonic's.

Safety: the source ROM is opened read-only and never written. Output goes to
--out-dir (default `build/`). Any verification failure aborts the build.

Usage:
    py build_mod.py <rom.nds> [--out-dir build]
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
from gda_write import set_int_cell  # noqa: E402
from twoda import parse_2da  # noqa: E402
from gff4 import GFF4, read_gda  # noqa: E402

ARCHIVE = '/test.herf'
CONTROL_RESOURCE = 'Item10.ITM'


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
    print("STAGE 2  open archive + apply edits")
    print("=" * 70)
    fid = rom.file_id(ARCHIVE)
    archive_original = rom.file_bytes(fid)
    herf = HerfFile(archive_original)
    if herf.serialize() != archive_original:
        fail('stage 2', 'no-op archive serialize differs from input')
    report['stages']['noop_archive_identical'] = True
    print(f"  {ARCHIVE}: {len(archive_original)} bytes, {herf.count} resources")
    control_before = herf.read(CONTROL_RESOURCE)

    # --- edit 1: ability magnitude (text 2DA) ---
    spl = 'Spell_Tough.spl'
    new_spl, note = set_cell(herf.read(spl), 'GRT+', 'Data', '20')
    stored = herf.replace(spl, new_spl)
    print(f"  [1] {spl}: {note}  [{stored}]")
    report['edits'].append({'resource': spl, 'change': note, 'storage': stored})

    # --- edit 2: item stat (text 2DA) ---
    itm = 'Item22.ITM'   # LightSlippers
    new_itm, note = set_cell(herf.read(itm), 'DEF+', 'Data', '5')
    stored = herf.replace(itm, new_itm)
    print(f"  [2] {itm} (LightSlippers): {note}  [{stored}]")
    report['edits'].append({'resource': itm, 'change': note, 'storage': stored})

    # --- edit 3: Shadow's XP curve (binary GDA) ---
    gda = 'Adv_Shadow.GDA'
    raw = herf.read(gda)
    notes = []
    for row, value in ((1, 200), (2, 490)):     # match Sonic's level 2 and 3
        raw, n = set_int_cell(raw, row, 'xp', value, col_names)
        notes.append(n)
    stored = herf.replace(gda, raw)
    print(f"  [3] {gda}: {'; '.join(notes)}  [{stored}]")
    report['edits'].append({'resource': gda, 'change': '; '.join(notes), 'storage': stored})

    probs = herf.validate()
    if probs:
        fail('stage 2', f'archive structurally invalid after edits: {probs[:3]}')
    new_archive = herf.serialize()
    print(f"  archive: {len(archive_original)} -> {len(new_archive)} bytes, validation clean")

    print()
    print("=" * 70)
    print("STAGE 3  repack archive into a rebuilt ROM")
    print("=" * 70)
    new_rom_bytes, br = rom.build({fid: new_archive})
    out_rom = os.path.join(out_dir, 'sonic_chronicles_datamod.nds')
    with open(out_rom, 'wb') as f:
        f.write(new_rom_bytes)
    tgt_crc = zlib.crc32(new_rom_bytes) & 0xFFFFFFFF
    print(f"  wrote {out_rom}  ({len(new_rom_bytes)} bytes, CRC32 {tgt_crc:08X})")
    print(f"  files moved: {br['moved_files']}   "
          f"total_used: {br['original_total_used']} -> {br['total_used_rom_size']}")
    report['output_rom'] = os.path.abspath(out_rom)
    report['output_crc32'] = f"{tgt_crc:08X}"
    report['files_moved'] = br['moved_files']

    print()
    print("=" * 70)
    print("STAGE 4  verify by reading back out of the rebuilt ROM")
    print("=" * 70)
    rebuilt = Rom(new_rom_bytes)
    rb_herf = HerfFile(rebuilt.file_bytes(rebuilt.file_id(ARCHIVE)))
    if rb_herf.count != herf.count:
        fail('stage 4', f'resource count changed: {rb_herf.count} != {herf.count}')
    print(f"  archive reopened: {rb_herf.count} resources, "
          f"{len(rb_herf.names)} names resolved")

    got = parse_2da(rb_herf.read(spl)).get('GRT+')['Data']
    print(f"  [1] {spl} GRT+.Data = {got!r}  -> {'OK' if got == '20' else 'MISMATCH'}")
    if got != '20':
        fail('stage 4', 'ability edit did not survive')

    got = parse_2da(rb_herf.read(itm)).get('DEF+')['Data']
    print(f"  [2] {itm} DEF+.Data = {got!r}  -> {'OK' if got == '5' else 'MISMATCH'}")
    if got != '5':
        fail('stage 4', 'item edit did not survive')

    _, rows = read_gda(GFF4(rb_herf.read(gda)))
    xp = [rows[i][10007] for i in (0, 1, 2, 3)]
    ok = xp[1] == 200 and xp[2] == 490
    print(f"  [3] {gda} xp levels 1-4 = {xp}  -> {'OK' if ok else 'MISMATCH'}")
    if not ok:
        fail('stage 4', 'XP curve edit did not survive')

    if rb_herf.read(CONTROL_RESOURCE) != control_before:
        fail('stage 4', f'control resource {CONTROL_RESOURCE} was corrupted')
    print(f"  [4] control resource {CONTROL_RESOURCE} unchanged: OK")

    # Regression sweep: every GDA table in the repacked archive must still decode.
    bad = []
    for i, name in rb_herf.names.items():
        if name.lower().endswith('.gda'):
            try:
                read_gda(GFF4(rb_herf.read(i)))
            except Exception as e:
                bad.append((name, str(e)))
    print(f"  [5] all GDA tables still decode: {len(bad) == 0} "
          f"({'none failed' if not bad else bad[:3]})")
    if bad:
        fail('stage 4', f'{len(bad)} GDA tables broke in the repacked archive')
    report['stages']['readback_verified'] = True

    print()
    print("=" * 70)
    print("STAGE 5  generate + verify BPS patch")
    print("=" * 70)
    meta = json.dumps({'project': 'Sonic Chronicles Modding Framework',
                       'edits': [e['resource'] for e in report['edits']]}).encode()
    patch = bps.create(original, new_rom_bytes, meta)
    out_patch = os.path.join(out_dir, 'sonic_chronicles_datamod.bps')
    with open(out_patch, 'wb') as f:
        f.write(patch)
    print(f"  wrote {out_patch} ({len(patch)} bytes for a {len(new_rom_bytes)} byte ROM)")
    if bps.apply(original, patch) != new_rom_bytes:
        fail('stage 5', 'patch does not reproduce the rebuilt ROM')
    print("  patch reproduces the rebuilt ROM exactly: OK")
    report['stages']['patch_verified'] = True
    report['output_patch'] = os.path.abspath(out_patch)
    report['patch_bytes'] = len(patch)

    report_path = os.path.join(out_dir, 'build_report_datamod.json')
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)

    print()
    print("=" * 70)
    print("ALL STAGES PASSED")
    print("=" * 70)
    print(f"  modded ROM : {out_rom}")
    print(f"  patch      : {out_patch}  ({len(patch)} bytes)")
    print(f"  report     : {report_path}")
    print("  original ROM untouched (opened read-only)")
    print()
    print("  Still manual: confirm in DeSmuME that Tough grants +20 Grit, that")
    print("  LightSlippers give +5 Defense, and that Shadow levels faster.")


if __name__ == '__main__':
    main()
