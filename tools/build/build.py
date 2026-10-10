"""
End-to-end build pipeline driver — Phase 1, exercised by the Phase 2 proof of
concept (change one dialogue string and prove it survives a full round trip).

Pipeline: original ROM -> validate -> extract -> edit -> rebuild -> verify ->
patch -> build report.

Safety: the original ROM is opened **read-only** and never written to. All output
goes to the directory given by --out-dir (default `build/`).

Verification is not optional here — each stage is checked, and a failure at any
stage aborts rather than producing a plausible-looking ROM:
  1. no-op rebuild of the untouched ROM is byte-identical (the rebuilder is sound)
  2. no-op TLK serialize is byte-identical (the editor is sound)
  3. the edited string reads back correctly **from the rebuilt ROM**, via the
     independent GFF4 reader
  4. a control string elsewhere in the table is unchanged
  5. the BPS patch applied to the original reproduces the rebuilt ROM exactly

Usage:
    py build.py <rom.nds> [--out-dir build] [--set <stringId>=<text>]
    (with no --set, a default demonstration edit is applied)
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
from gff4 import GFF4  # noqa: E402

TLK_PATH = '/strings.tlk'
TLK_ENTRY_LIST_FIELD = 19001
TLK_ID_FIELD = 19002
TLK_TEXT_FIELD = 19003


def fail(stage, msg):
    print(f"\n!! ABORTED at {stage}: {msg}")
    sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    rom_path = sys.argv[1]
    out_dir = 'build'
    edits = []
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == '--out-dir':
            out_dir = args[i + 1]; i += 2
        elif args[i] == '--set':
            sid, text = args[i + 1].split('=', 1)
            edits.append((int(sid), text)); i += 2
        else:
            i += 1
    os.makedirs(out_dir, exist_ok=True)

    report = {'generated': time.strftime('%Y-%m-%d %H:%M:%S'),
              'source_rom': os.path.abspath(rom_path), 'stages': {}}

    print("=" * 68)
    print("STAGE 1  validate source + no-op rebuild")
    print("=" * 68)
    with open(rom_path, 'rb') as f:
        original = f.read()
    rom = Rom(original)
    src_crc = zlib.crc32(original) & 0xFFFFFFFF
    print(f"  source: {len(original)} bytes, CRC32 {src_crc:08X}, {rom.num_files} files")
    if not verify_noop(rom_path):
        fail('stage 1', 'no-op rebuild is not byte-identical; rebuilder cannot be trusted')
    report['stages']['noop_rebuild_identical'] = True
    report['source_crc32'] = f"{src_crc:08X}"

    print()
    print("=" * 68)
    print("STAGE 2  extract + edit dialogue")
    print("=" * 68)
    fid = rom.file_id(TLK_PATH)
    tlk_original = rom.file_bytes(fid)
    tlk = TlkFile(tlk_original)
    if tlk.serialize() != tlk_original:
        fail('stage 2', 'no-op TLK serialize differs from input; editor cannot be trusted')
    report['stages']['noop_tlk_identical'] = True
    print(f"  {TLK_PATH}: {len(tlk_original)} bytes, {tlk.count} entries")

    if not edits:
        # Default demonstration: retarget a known line to prove the pipeline.
        edits = [(6676, "Don't worry. Those are just drones. They won't fight. [MODDED]")]

    applied = []
    for sid, text in edits:
        idx = tlk.index_of_id(sid)
        before = tlk.get_string(idx)
        note = tlk.set_string(idx, text)
        print(f"  id {sid} (index {idx}):")
        print(f"     before: {before!r}")
        print(f"     after : {text!r}")
        print(f"     stored: {note}")
        applied.append({'string_id': sid, 'index': idx, 'before': before,
                        'after': text, 'storage': note})
    report['edits'] = applied

    # A control entry we did NOT touch, to catch collateral damage.
    control_idx = next(i for i in range(tlk.count)
                       if tlk.entry_offset(i) != NO_STRING
                       and i not in {e['index'] for e in applied}
                       and tlk.get_string(i))
    control_id = tlk.entry_id(control_idx)
    control_text = tlk.get_string(control_idx)

    new_tlk = tlk.serialize()
    print(f"  rebuilt TLK: {len(tlk_original)} -> {len(new_tlk)} bytes")

    print()
    print("=" * 68)
    print("STAGE 3  rebuild ROM")
    print("=" * 68)
    new_rom_bytes, build_report = rom.build({fid: new_tlk})
    out_rom = os.path.join(out_dir, 'sonic_chronicles_modded.nds')
    with open(out_rom, 'wb') as f:
        f.write(new_rom_bytes)
    tgt_crc = zlib.crc32(new_rom_bytes) & 0xFFFFFFFF
    print(f"  wrote {out_rom}")
    print(f"  size {len(new_rom_bytes)} bytes, CRC32 {tgt_crc:08X}")
    print(f"  files moved by the size change: {build_report['moved_files']}")
    print(f"  total_used_rom_size: {build_report['original_total_used']} -> "
          f"{build_report['total_used_rom_size']}")
    report['stages']['rebuilt'] = True
    report['output_rom'] = os.path.abspath(out_rom)
    report['output_crc32'] = f"{tgt_crc:08X}"
    report['files_moved'] = build_report['moved_files']

    print()
    print("=" * 68)
    print("STAGE 4  verify the REBUILT ROM by reading it back")
    print("=" * 68)
    rebuilt = Rom(new_rom_bytes)
    g = GFF4(rebuilt.file_bytes(rebuilt.file_id(TLK_PATH)))
    entries = g.root()[TLK_ENTRY_LIST_FIELD]
    if len(entries) != tlk.count:
        fail('stage 4', f'entry count changed: {len(entries)} != {tlk.count}')
    for e in applied:
        got = entries[e['index']][TLK_TEXT_FIELD]
        got_id = entries[e['index']][TLK_ID_FIELD]
        ok = got == e['after'] and got_id == e['string_id']
        print(f"  id {e['string_id']}: read back {got!r}  -> {'OK' if ok else 'MISMATCH'}")
        if not ok:
            fail('stage 4', f"edited string {e['string_id']} did not survive the rebuild")
    got_control = entries[control_idx][TLK_TEXT_FIELD]
    if got_control != control_text:
        fail('stage 4', f'control string (id {control_id}) was corrupted: '
                        f'{got_control!r} != {control_text!r}')
    print(f"  control id {control_id} unchanged: OK")
    intact = sum(1 for e in entries if e[TLK_TEXT_FIELD])
    print(f"  entries still carrying text: {intact}")
    report['stages']['readback_verified'] = True
    report['control_string_id'] = control_id
    report['entries_with_text'] = intact

    print()
    print("=" * 68)
    print("STAGE 5  generate + verify BPS patch")
    print("=" * 68)
    meta = json.dumps({'project': 'Sonic Chronicles Modding Framework',
                       'edits': [e['string_id'] for e in applied]}).encode('utf-8')
    patch = bps.create(original, new_rom_bytes, meta)
    out_patch = os.path.join(out_dir, 'sonic_chronicles_modded.bps')
    with open(out_patch, 'wb') as f:
        f.write(patch)
    print(f"  wrote {out_patch} ({len(patch)} bytes "
          f"for a {len(new_rom_bytes)} byte ROM)")
    reapplied = bps.apply(original, patch)
    if reapplied != new_rom_bytes:
        fail('stage 5', 'patch does not reproduce the rebuilt ROM')
    print("  patch applied to the original reproduces the rebuilt ROM exactly: OK")
    report['stages']['patch_verified'] = True
    report['output_patch'] = os.path.abspath(out_patch)
    report['patch_bytes'] = len(patch)

    report_path = os.path.join(out_dir, 'build_report.json')
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)

    print()
    print("=" * 68)
    print("ALL STAGES PASSED")
    print("=" * 68)
    print(f"  modded ROM : {out_rom}")
    print(f"  patch      : {out_patch}  ({len(patch)} bytes)")
    print(f"  report     : {report_path}")
    print(f"  original ROM was not modified (opened read-only)")
    print()
    print("  Remaining manual step: load the modded ROM in DeSmuME and confirm the")
    print("  changed line appears in game. Tooling cannot verify on-screen output.")


if __name__ == '__main__':
    main()
