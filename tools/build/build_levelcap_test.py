"""
THE LEVEL CAP EXPERIMENT (roadmap Phase 6, decisive question).

The vanilla cap is 30: every `Adv_<Character>.GDA` has exactly 30 rows with a
`level` column running 1..30, and **no GDA column anywhere in the ROM holds a
constant 30**, so there is no data-driven cap value to edit. That leaves two
possibilities, and they have very different costs:

    A) the engine derives the cap from the table's ROW COUNT
       -> extending the cap is pure data editing. Phase 6 becomes cheap.
    B) the cap is a hardcoded constant in the ARM9 binary
       -> extending it needs a code patch as well as data.

This build appends a **level 31** row to all 11 playable characters' tables and
asks the game which it is.

Making the test actually runnable
--------------------------------
Reaching level 30 legitimately takes a full playthrough, so the experiment would
be untestable from a mid-game save. To fix that, every XP threshold is rewritten
to a trivially small value (`level N requires (N-1) * 100` XP, so level 31 needs
3000). Any existing save almost certainly already exceeds that, so the next XP
gain should rocket the character to the maximum the engine permits — which is
exactly what we want to measure.

    character reaches 31  => A: cap is data-driven, Phase 6 is data editing
    character stops at 30 => B: cap is hardcoded in ARM9, needs a code patch

Either outcome is a real result. This is a **test build, not a mod** — the XP
curve is deliberately destroyed.

The level-31 stats are extrapolated by repeating each column's final 29->30 delta,
so the new row is a plausible continuation rather than zeroes (zeroes could make a
"reached 31" result ambiguous, e.g. a character with 0 HP).

Usage:
    py build_levelcap_test.py <rom.nds> [--out-dir build]
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
from gda_write import set_int_cell, append_row, ROW_FIELD_BASE  # noqa: E402
from gff4 import GFF4, read_gda  # noqa: E402

ARCHIVE = '/test.herf'
XP_PER_LEVEL = 100
DEFAULT_CAP = 31
COL_ID, COL_LEVEL, COL_XP = 0, 1, 2   # positional: id, level, xp
# Column 11 (hash #441910439) is the cumulative bonus-point count: in vanilla it
# runs 1,2,3..20 then plateaus at 20 by level 20. Extrapolating its final delta
# (zero) freezes it, so extended levels award no bonus points -- confirmed in game
# at level 99 with only 1 point. Give it +1 per level instead.
COL_BONUS = 11


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
    NEW_CAP = DEFAULT_CAP
    BONUS_PER_LEVEL = '--no-bonus' not in sys.argv
    if '--cap' in sys.argv:
        NEW_CAP = int(sys.argv[sys.argv.index('--cap') + 1])
    if NEW_CAP <= 30:
        fail('args', f'--cap must exceed the vanilla cap of 30 (got {NEW_CAP})')
    suffix = '' if NEW_CAP == DEFAULT_CAP else f'{NEW_CAP}'
    os.makedirs(out_dir, exist_ok=True)
    col_names = load_column_names()

    print("=" * 70)
    print("STAGE 1  validate")
    print("=" * 70)
    with open(rom_path, 'rb') as f:
        original = f.read()
    rom = Rom(original)
    print(f"  source CRC32 {zlib.crc32(original) & 0xFFFFFFFF:08X}")
    if not verify_noop(rom_path):
        fail('stage 1', 'no-op rebuild is not byte-identical')

    fid = rom.file_id(ARCHIVE)
    herf = HerfFile(rom.file_bytes(fid))
    if herf.serialize() != rom.file_bytes(fid):
        fail('stage 1', 'no-op archive serialize differs')

    targets = sorted(n for n in herf.names.values()
                     if n.startswith('Adv_') and n.endswith('.GDA')
                     and 'VFXTester' not in n)
    print(f"  progression tables to extend: {len(targets)}")

    print()
    print("=" * 70)
    print(f"STAGE 2  append level {NEW_CAP} + flatten XP to {XP_PER_LEVEL}/level")
    print("=" * 70)
    details = []
    for name in targets:
        raw = herf.read(name)
        cols, rows = read_gda(GFF4(raw))
        ncols = len(cols)
        last = [rows[-1][ROW_FIELD_BASE + i] for i in range(ncols)]
        prev = [rows[-2][ROW_FIELD_BASE + i] for i in range(ncols)]
        delta = [last[i] - prev[i] for i in range(ncols)]

        # Extrapolate by repeating the final 29->30 delta for each column, once
        # per added level, so the curve continues plausibly instead of flatlining.
        note = None
        cur = list(last)
        for lvl in range(len(rows) + 1, NEW_CAP + 1):
            cur = [cur[i] + delta[i] for i in range(ncols)]
            cur[COL_ID] = lvl - 1
            cur[COL_LEVEL] = lvl
            cur[COL_XP] = (lvl - 1) * XP_PER_LEVEL
            if BONUS_PER_LEVEL:
                cur[COL_BONUS] = last[COL_BONUS] + (lvl - len(rows))
            raw, note = append_row(raw, cur)
        new_row = cur

        # Flatten every XP threshold so the cap is reachable from any save.
        for r in range(NEW_CAP):
            raw, _ = set_int_cell(raw, r, COL_XP, r * XP_PER_LEVEL, col_names)

        storage = herf.replace(name, raw)
        cols2, rows2 = read_gda(GFF4(herf.read(name)))
        lv = [rows2[i][ROW_FIELD_BASE + COL_LEVEL] for i in range(len(rows2))]
        if len(rows2) != NEW_CAP or lv[-1] != NEW_CAP:
            fail('stage 2', f'{name}: expected {NEW_CAP} rows ending at level {NEW_CAP}, got {len(rows2)} / {lv[-1]}')
        details.append({'table': name, 'rows': len(rows2), 'bonus_per_level': BONUS_PER_LEVEL,
                        'level31_stats': new_row, 'storage': storage})
        print(f"  {name:20} {note}; levels now {lv[0]}..{lv[-1]}  [{storage}]")

    probs = herf.validate()
    if probs:
        fail('stage 2', f'archive invalid: {probs[:3]}')
    new_archive = herf.serialize()
    print(f"  archive: {len(rom.file_bytes(fid))} -> {len(new_archive)} bytes, validation clean")

    print()
    print("=" * 70)
    print("STAGE 3  rebuild + verify from the rebuilt ROM")
    print("=" * 70)
    new_rom, br = rom.build({fid: new_archive})
    out_rom = os.path.join(out_dir, f'sonic_chronicles_levelcap{suffix}.nds')
    with open(out_rom, 'wb') as f:
        f.write(new_rom)
    print(f"  wrote {out_rom}  (CRC32 {zlib.crc32(new_rom) & 0xFFFFFFFF:08X}, "
          f"files moved {br['moved_files']})")

    rebuilt = Rom(new_rom)
    rb = HerfFile(rebuilt.file_bytes(rebuilt.file_id(ARCHIVE)))
    for name in targets:
        cols, rows = read_gda(GFF4(rb.read(name)))
        lv = [r[ROW_FIELD_BASE + COL_LEVEL] for r in rows]
        xp = [r[ROW_FIELD_BASE + COL_XP] for r in rows]
        if len(rows) != NEW_CAP or lv != list(range(1, NEW_CAP + 1)):
            fail('stage 3', f'{name}: level column is {lv}')
        if xp != [i * XP_PER_LEVEL for i in range(NEW_CAP)]:
            fail('stage 3', f'{name}: xp column is {xp}')
    print(f"  all {len(targets)} tables: {NEW_CAP} rows, levels 1..{NEW_CAP}, "
          f"xp 0..{(NEW_CAP - 1) * XP_PER_LEVEL}  OK")

    sonic = next(n for n in targets if 'Sonic' in n)
    cols, rows = read_gda(GFF4(rb.read(sonic)))
    hdr = [col_names.get(c['hash'], '#%d' % c['hash']) for c in cols]
    print(f"\n  {sonic} last two rows:")
    print('    ' + ' '.join('%8s' % h[:8] for h in hdr))
    for r in rows[-2:]:
        print('    ' + ' '.join('%8s' % r[ROW_FIELD_BASE + i] for i in range(len(cols))))

    bad = []
    for i, n in rb.names.items():
        if n.lower().endswith('.gda'):
            try:
                read_gda(GFF4(rb.read(i)))
            except Exception as e:
                bad.append((n, str(e)))
    print(f"\n  all GDA tables still decode: {not bad} "
          f"({'none failed' if not bad else bad[:3]})")
    if bad:
        fail('stage 3', f'{len(bad)} GDA tables broke')

    print()
    print("=" * 70)
    print("STAGE 4  patch")
    print("=" * 70)
    patch = bps.create(original, new_rom,
                       json.dumps({'kind': 'level cap experiment', 'cap': NEW_CAP}).encode())
    out_patch = os.path.join(out_dir, f'sonic_chronicles_levelcap{suffix}.bps')
    with open(out_patch, 'wb') as f:
        f.write(patch)
    if bps.apply(original, patch) != new_rom:
        fail('stage 4', 'patch does not reproduce the ROM')
    print(f"  wrote {out_patch} ({len(patch)} bytes), verified")

    with open(os.path.join(out_dir, f'build_report_levelcap{suffix}.json'), 'w', encoding='utf-8') as f:
        json.dump({'generated': time.strftime('%Y-%m-%d %H:%M:%S'),
                   'experiment': 'is the level cap data-driven (row count) or hardcoded?',
                   'new_cap': NEW_CAP, 'xp_per_level': XP_PER_LEVEL,
                   'tables': details, 'output_rom': os.path.abspath(out_rom),
                   'patch_bytes': len(patch)}, f, indent=2)

    print()
    print("=" * 70)
    print("ALL STAGES PASSED")
    print("=" * 70)
    print(f"  level cap test ROM: {out_rom}")
    print(f"  reaches 31 -> cap is data-driven; stops at 30 -> hardcoded in ARM9")


if __name__ == '__main__':
    main()
