"""
Writer for HERF archives — the gap that was blocking every data-driven mod.

Almost everything worth changing in this game lives inside `/test.herf`: the 219
item tables, 151 ability tables, 229 GDA tables (including the `Adv_*`
progression curves), 101 `.dlg` conversations, and all the graphics. Reading them
was solved earlier; this module writes them back.

Layout rules, confirmed against `/test.herf` (8691 resources):
    uint32 magic = 0x00F1A5C0
    uint32 resourceCount
    resourceCount x 12 bytes: uint32 nameHash (DJB2), uint32 size, uint32 offset
  * resource data begins immediately after the table (no padding): the table
    occupies bytes 8..104300 and the lowest resource offset is exactly 104300;
  * **every resource offset is 4-byte aligned** (verified for all 8691);
  * gaps between consecutive resources are 0-3 bytes of alignment padding only —
    there is no spare slack anywhere;
  * no resources overlap.

Strategy: **surgical replace, like the TLK writer.**
  * new payload fits the old slot -> written in place, only the table's `size`
    field changes, nothing moves;
  * otherwise -> appended at the (4-byte aligned) end of the archive and the
    table's `offset`/`size` repointed.
Either way the other 8690 resources stay exactly where they are, so a no-op save
is byte-identical and real edits produce a minimal diff — which matters a lot for
patch size, since this archive is 49 MB.

When a payload shrinks, the leftover bytes of the old slot are deliberately left
untouched rather than zeroed: nothing reads past a resource's recorded `size`, and
rewriting them would enlarge the diff for no benefit.

**Not supported: adding or removing resources.** That changes the resource-table
length, which shifts every resource's data and requires a full relayout (plus
rebuilding the `erf.dict` name dictionary). Replacement covers the modding cases
this project needs; adding new resources is a separate job.

Usage:
    py herf_write.py <rom.nds> --verify
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'recon'))

MAGIC = 0x00F1A5C0
ALIGN = 4


def djb2_add(s: bytes) -> int:
    h = 5381
    for b in s:
        h = (h * 33 + b) & 0xFFFFFFFF
    return h


class HerfFile:
    def __init__(self, data: bytes):
        self.data = bytearray(data)
        magic, self.count = struct.unpack_from('<II', self.data, 0)
        if magic != MAGIC:
            raise ValueError(f"not a HERF archive (magic 0x{magic:X})")
        self.table_pos = 8
        self.names = self._load_dict()
        self._by_name = {n: i for i, n in self.names.items()}

    # --- table access ---

    def entry(self, i):
        """(hash, size, offset) for resource index i."""
        return struct.unpack_from('<III', self.data, self.table_pos + i * 12)

    def _set_entry(self, i, h, size, offset):
        struct.pack_into('<III', self.data, self.table_pos + i * 12, h, size, offset)

    def _load_dict(self):
        """hash -> name, from the embedded erf.dict resource if present."""
        want = djb2_add(b'erf.dict')
        names = {}
        for i in range(self.count):
            h, size, off = self.entry(i)
            if h != want:
                continue
            _, dcount = struct.unpack_from('<II', self.data, off)
            pos = off + 8
            for _ in range(dcount):
                dh, = struct.unpack_from('<I', self.data, pos)
                nm = bytes(self.data[pos + 4:pos + 4 + 128]).split(b'\x00', 1)[0]
                names[dh] = nm.decode('ascii', 'replace')
                pos += 132
            break
        # map index -> name
        out = {}
        for i in range(self.count):
            h, _, _ = self.entry(i)
            if h in names:
                out[i] = names[h]
        return out

    def index_of(self, name):
        if name in self._by_name:
            return self._by_name[name]
        # fall back to hashing the name as given
        want = djb2_add(name.encode('ascii'))
        for i in range(self.count):
            if self.entry(i)[0] == want:
                return i
        raise KeyError(f"no resource named {name!r} in this archive")

    def read(self, name_or_index):
        i = name_or_index if isinstance(name_or_index, int) else self.index_of(name_or_index)
        _, size, off = self.entry(i)
        return bytes(self.data[off:off + size])

    # --- editing ---

    def replace(self, name_or_index, payload: bytes):
        """Replace a resource's payload. Returns a note on how it was stored."""
        i = name_or_index if isinstance(name_or_index, int) else self.index_of(name_or_index)
        h, old_size, old_off = self.entry(i)

        if len(payload) <= old_size:
            self.data[old_off:old_off + len(payload)] = payload
            self._set_entry(i, h, len(payload), old_off)
            return f"in place (slot {old_size} bytes, now {len(payload)})"

        while len(self.data) % ALIGN:
            self.data.append(0)
        new_off = len(self.data)
        self.data.extend(payload)
        while len(self.data) % ALIGN:
            self.data.append(0)
        self._set_entry(i, h, len(payload), new_off)
        return f"appended (old {old_size} -> {len(payload)} bytes, new offset {new_off})"

    def serialize(self) -> bytes:
        return bytes(self.data)

    # --- validation ---

    def validate(self):
        problems = []
        spans = []
        for i in range(self.count):
            h, size, off = self.entry(i)
            if off % ALIGN:
                problems.append(f"resource {i} ({self.names.get(i, '?')}): offset {off} not {ALIGN}-byte aligned")
            if off + size > len(self.data):
                problems.append(f"resource {i} ({self.names.get(i, '?')}): extends past end of archive")
            if size:
                spans.append((off, off + size, i))
        spans.sort()
        for (s1, e1, i1), (s2, e2, i2) in zip(spans, spans[1:]):
            if s2 < e1:
                problems.append(f"resources {i1} ({self.names.get(i1, '?')}) and "
                                f"{i2} ({self.names.get(i2, '?')}) overlap")
        return problems


def verify(rom_path):
    from rom_build import Rom
    from twoda import parse_2da
    from gff4 import GFF4, read_gda

    with open(rom_path, 'rb') as f:
        rom = Rom(f.read())
    fid = rom.file_id('/test.herf')
    original = rom.file_bytes(fid)

    herf = HerfFile(original)
    print(f"archive: {len(original)} bytes, {herf.count} resources, "
          f"{len(herf.names)} names resolved")
    ok_noop = herf.serialize() == original
    print(f"NO-OP SERIALIZE BYTE-IDENTICAL: {ok_noop}")
    probs = herf.validate()
    print(f"structural validation: {'clean' if not probs else probs[:3]}")

    results = [ok_noop, not probs]

    from twoda_write import set_cell

    # 1) plain-text 2DA edit, same length -> in-place path
    name = 'Spell_Tough.spl'
    grt_before = parse_2da(herf.read(name)).get('GRT+')['Data']
    edited, note = set_cell(herf.read(name), 'GRT+', 'Data', '99')
    note1 = herf.replace(name, edited)
    grt_after = parse_2da(herf.read(name)).get('GRT+')['Data']
    print(f"\n[1] text 2DA edit, {name}: {note}  [{note1}]")
    results.append(grt_before == '10' and grt_after == '99')

    # 2) plain-text edit that makes the file longer -> append path
    edited2, note2a = set_cell(herf.read(name), 'GRT+', 'Data', '1234567890123')
    note2 = herf.replace(name, edited2)
    grt3 = parse_2da(herf.read(name)).get('GRT+')['Data']
    print(f"[2] growing edit: {note2a}  [{note2}]")
    results.append(grt3 == '1234567890123' and 'append' in note2)

    # 3) binary GDA in-place integer edit (no GFF4 writer needed: fixed-size field)
    gname = 'Adv_Sonic.GDA'
    graw = bytearray(herf.read(gname))
    g = GFF4(bytes(graw))
    cols, rows = read_gda(g)
    # locate the row list and the xp field within a row struct
    root_list_off, = struct.unpack_from('<I', graw, g.data_offset)
    rows_field = next(f for f in g.templates[0].fields if f.label == 10003)
    rl_off, = struct.unpack_from('<I', graw, g.data_offset + rows_field.offset)
    rows_count_pos = g.data_offset + rl_off
    rows_start = rows_count_pos + 4
    row_tmpl = g.templates[rows_field.type]
    xp_field = next(f for f in row_tmpl.fields if f.label == 10007)  # 3rd column = xp
    last = len(rows) - 1
    pos = rows_start + last * row_tmpl.size + xp_field.offset
    xp_before, = struct.unpack_from('<i', graw, pos)
    struct.pack_into('<i', graw, pos, 1234567)
    note3 = herf.replace(gname, bytes(graw))
    g2 = GFF4(herf.read(gname))
    _, rows2 = read_gda(g2)
    xp_after = rows2[last][10007]
    print(f"[3] binary GDA edit, {gname} level-30 xp: {xp_before} -> {xp_after}  [{note3}]")
    results.append(xp_before == rows[last][10007] and xp_after == 1234567)

    # 4) an untouched resource must be bit-identical, and the archive still valid
    control = 'Item22.ITM'
    ctrl_now = herf.read(control)
    ctrl_orig = HerfFile(original).read(control)
    print(f"[4] control resource {control} unchanged: {ctrl_now == ctrl_orig}")
    results.append(ctrl_now == ctrl_orig)

    probs2 = herf.validate()
    print(f"[5] post-edit structural validation: {'clean' if not probs2 else probs2[:3]}")
    results.append(not probs2)
    print(f"    archive size {len(original)} -> {len(herf.serialize())} bytes")

    print(f"\nALL CHECKS PASSED: {all(results)}")
    return all(results)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    if '--verify' in sys.argv:
        sys.exit(0 if verify(sys.argv[1]) else 1)
    print(__doc__)


if __name__ == '__main__':
    main()
