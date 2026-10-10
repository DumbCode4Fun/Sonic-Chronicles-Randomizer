"""
The two ARM9 experiments, scripted against melonDS' GDB stub.

Both questions this project cannot answer from data come down to the same shape: *what
code touches this byte?* A watchpoint answers that in one step, and scripting it means
the answer is reproducible and pasteable into the log rather than something that happened
once in somebody's terminal.

Read `gdbstub.py` first for how to turn the stub on (and turn the JIT off).

    py tools/recon/gdb_experiments.py scaling <rom.nds> [creature-row]
    py tools/recon/gdb_experiments.py snapshot <name>
    py tools/recon/gdb_experiments.py flags <snapA> <snapB> [snapC ...]
    py tools/recon/gdb_experiments.py watch <hex addr> [len] [read|write|access]

---------------------------------------------------------------------------
Experiment 1 - `scaling`: where does combat read a creature's stats?
---------------------------------------------------------------------------
`enemy_scaling` already rewrites `creatures.GDA` at build time, which is a *static*
curve. Making enemies scale to the party needs the code that loads those stats, and the
cheap static route is already known to fail: `creatures.GDA` column names are recoverable
by hashing but none of the hashes appears in ARM9, so the binary was compiled against
fixed indices that look like any other small constant.

So find it from the data end instead. The archive is decompressed into main RAM at load,
which means the creature table **is in RAM, byte for byte as we can read it from the
ROM**. This script:

  1. reads `creatures.GDA` out of the ROM and builds a distinctive byte signature for one
     creature's row - by default a low-level one you meet early;
  2. searches the DS's 4 MB of main RAM for it;
  3. sets a **read** watchpoint on that row's HP field;
  4. waits. Start a battle with that creature.

When the watchpoint fires, the PC is an instruction inside whatever reads creature stats.
Feed that address to `disasm.py` and the function around it is the stat loader.

**What would make this fail, and what it would mean.** If the signature is not found, the
table is not held in RAM in its file form - it is parsed into some other structure at load
and the search has to be for the *parsed* values instead. If the watchpoint never fires
but the battle runs, the stats were copied out of the table earlier (at area load, say),
and the watchpoint wants setting before entering the area. Either outcome is informative
and should be recorded rather than retried blindly.

---------------------------------------------------------------------------
Experiment 2 - `snapshot` / `flags`: where does the plot-flag block live?
---------------------------------------------------------------------------
Recruitment order is readable from the plot files now (see the log), but *changing* it
needs the code that reacts to a flag. The entry point is a write watchpoint on the flag,
and for that we need the flag block's address.

It is not findable in a save file - that was tried, and an 83-byte window that only ever
gains bits matches 1,078 places in a 64 KB save, which is no answer at all. In RAM it is
findable, because we can take snapshots **around a single known event** and intersect.

  1. `snapshot before` - in the overworld, nothing happening.
  2. Trigger exactly one plot event: talk to the NPC who gives a quest, say.
  3. `snapshot after1`.
  4. Trigger one more.
  5. `snapshot after2`.
  6. `flags before after1 after2` - windows where bits only ever turn **on**, never off,
     across all three, and where only a handful turn on per event.

657 flags is 83 bytes. Monotonicity across two separate events in a row is a much
stronger filter than across one, which is exactly what the save-file attempt lacked.
"""
import os
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'build'))

from gdbstub import Stub, MAIN_RAM, WP_READ, WP_WRITE, WP_ACCESS  # noqa: E402

#: 657 plot flags, one bit each.
FLAG_COUNT = 657
FLAG_BYTES = (FLAG_COUNT + 7) // 8

SNAP_DIR = os.path.join(HERE, '..', '..', 'work', 'ramsnaps')


# ---------------------------------------------------------------- scaling

def creature_signature(rom_path, row_index):
    """(signature bytes, offset of the HP field within it) for one creature row.

    The signature is the row's raw bytes as they sit in the file. A GDA row array is a
    flat run of fixed-size structs, so a row is contiguous and unique enough to search
    for - 16 bytes of stats that no other row shares.
    """
    from modbuild import Build
    from gff4 import GFF4, read_gda, UNPACK
    import features

    b = Build(rom_path)
    raw = b.herf.read(b.resource('creatures.GDA'))
    g = GFF4(raw)
    cols, rows = read_gda(g)
    if not 0 <= row_index < len(rows):
        raise SystemExit('creatures.GDA has %d rows; no row %d' % (len(rows), row_index))

    rows_field = next(f for f in g.templates[0].fields if f.label == 10003)
    list_off, = struct.unpack_from('<I', raw, g.data_offset + rows_field.offset)
    start = g.data_offset + list_off + 4
    tmpl = g.templates[rows_field.type]
    base = start + row_index * tmpl.size
    sig = raw[base:base + tmpl.size]

    K = sorted(rows[0].keys())
    hp_label = K[features.CR_HP]
    hp_field = next(f for f in tmpl.fields if f.label == hp_label)
    name = features._text(b, rows[row_index][K[features.CR_NAME]])
    stats = {n: rows[row_index][K[c]] for n, c in
             (('level', features.CR_LEVEL), ('hp', features.CR_HP),
              ('pow', features.CR_POW), ('def', features.CR_DEF))}
    return sig, hp_field.offset, name, stats


def run_scaling(rom_path, row_index=0, port=3333):
    sig, hp_off, name, stats = creature_signature(rom_path, row_index)
    print('creature row %d: %r  %s' % (row_index, name, stats))
    print('row is %d bytes; HP field at +0x%X' % (len(sig), hp_off))
    print()

    with Stub(port=port) as g:
        print('attached. searching %d MB of main RAM for the row...'
              % ((MAIN_RAM[1] - MAIN_RAM[0]) // (1 << 20)))
        t0 = time.time()
        hits = g.search(sig, progress=lambda a, e, n: print(
            '\r  0x%08X  %d hit(s)' % (a, n), end='', file=sys.stderr))
        print('\r  searched in %.1fs, %d hit(s)%s' % (time.time() - t0, len(hits), ' ' * 20))
        if not hits:
            print('\nNOT FOUND. The table is not held in RAM in its file form - it is\n'
                  'parsed into another structure at load. Search for the parsed values\n'
                  '(HP %s, POW %s as separate words) instead, and record this result.'
                  % (stats['hp'], stats['pow']))
            return
        for h in hits:
            print('  candidate table row at 0x%08X' % h)
        addr = hits[0] + hp_off
        print('\nsetting a READ watchpoint on the HP field at 0x%08X' % addr)
        try:
            g.set_watch(addr, 4, WP_READ)
        except Exception as exc:
            print('  read watchpoints refused (%s); trying access' % exc)
            g.set_watch(addr, 4, WP_ACCESS)
        print('\n>>> Now start a battle with %r. Waiting...' % name)
        stop = g.cont(timeout=600)
        pc = g.pc()
        print('\nSTOPPED: %s' % stop['raw'])
        print('  pc  = 0x%08X   <-- the instruction that read it' % (pc or 0))
        regs = g.registers() or []
        for i, r in enumerate(regs[:13]):
            print('  r%-2d = 0x%08X' % (i, r))
        print('\nNext: py tools/recon/disasm.py around 0x%08X' % (pc or 0))


# ------------------------------------------------------- snapshots / flags

def run_snapshot(name, port=3333):
    os.makedirs(SNAP_DIR, exist_ok=True)
    path = os.path.join(SNAP_DIR, name + '.bin')
    with Stub(port=port) as g:
        g.interrupt()
        print('reading main RAM...')
        t0 = time.time()
        data = g.read(MAIN_RAM[0], MAIN_RAM[1] - MAIN_RAM[0])
        with open(path, 'wb') as f:
            f.write(data)
        print('wrote %s (%d bytes, %.1fs)' % (path, len(data), time.time() - t0))
        print('the game is left halted; continue it in melonDS, or run another snapshot')


def run_flags(names):
    snaps = []
    for n in names:
        p = n if os.path.exists(n) else os.path.join(SNAP_DIR, n + '.bin')
        with open(p, 'rb') as f:
            snaps.append((os.path.basename(p), f.read()))
    size = min(len(d) for _, d in snaps)
    print('%d snapshots, %d bytes each' % (len(snaps), size))

    cands = []
    for start in range(0, size - FLAG_BYTES):
        windows = [d[start:start + FLAG_BYTES] for _, d in snaps]
        gained = 0
        ok = True
        for a, b in zip(windows, windows[1:]):
            if any(x & ~y for x, y in zip(a, b)):     # a bit turned off
                ok = False
                break
            g = sum(bin(y).count('1') for y in b) - sum(bin(x).count('1') for x in a)
            if not 1 <= g <= 40:      # one plot event sets a handful of flags
                ok = False
                break
            gained += g
        if ok:
            cands.append((gained, start))
    cands.sort(reverse=True)
    print('\nwindows where bits only ever turn ON, 1-40 per event:')
    if not cands:
        print('  none. Either a snapshot was taken mid-event, or the flags are not a\n'
              '  bitfield - try one byte per flag (657 bytes) instead.')
        return
    for gained, start in cands[:20]:
        counts = [sum(bin(x).count('1') for x in d[start:start + FLAG_BYTES])
                  for _, d in snaps]
        print('  0x%08X  bits %s  (+%d total)'
              % (MAIN_RAM[0] + start, ' -> '.join(str(c) for c in counts), gained))
    print('\n%d candidate(s). If more than a couple survive, take another snapshot after\n'
          'one more plot event and re-run: each event roughly squares the filter.'
          % len(cands))


def run_watch(addr, length=1, kind='write', port=3333):
    kinds = {'read': WP_READ, 'write': WP_WRITE, 'access': WP_ACCESS}
    with Stub(port=port) as g:
        g.set_watch(addr, length, kinds[kind])
        print('%s watchpoint on 0x%08X+%d. Trigger the event...' % (kind, addr, length))
        stop = g.cont(timeout=600)
        print('STOPPED: %s' % stop['raw'])
        print('  pc = 0x%08X' % (g.pc() or 0))


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return
    if a[0] == 'scaling':
        if len(a) < 2:
            raise SystemExit('scaling needs the ROM path')
        run_scaling(a[1], int(a[2]) if len(a) > 2 else 0)
    elif a[0] == 'snapshot':
        run_snapshot(a[1] if len(a) > 1 else 'snap')
    elif a[0] == 'flags':
        run_flags(a[1:])
    elif a[0] == 'watch':
        run_watch(int(a[1], 16), int(a[2]) if len(a) > 2 else 1,
                  a[3] if len(a) > 3 else 'write')
    else:
        print('unknown command %r' % a[0])


if __name__ == '__main__':
    main()
