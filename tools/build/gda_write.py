"""
In-place integer-cell editor for GDA (GFF4-wrapped 2DA) tables.

Covers the common modding need — changing a numeric value in a table such as the
`Adv_<Character>.GDA` progression curves (XP thresholds, per-level stat growth) or
`creatures.GDA` base stats. Integer columns are fixed-width fields inside
fixed-size row structs, so the new value overwrites the old with **no change to
file length and no offsets to fix**, which keeps the resulting patch tiny.

Row layout, per the GFF4 work in REVERSE_ENGINEERING_LOG.md: the root struct's
field 10003 is a LIST|STRUCT pointing at the row template; a `uint32` element
count sits at `dataOffset + listOffset`, with the row structs immediately after,
spaced by the template's `size`. Row fields are labelled sequentially from 10005
and map positionally onto the column list.

`append_rows_clone` adds rows to tables `append_row` refuses, by copying an existing
row rather than building one: a clone keeps the source's string *offsets*, so no new
string data is written, and it relocates the whole row array to the end of the file
instead of growing it in place. That covers `creatures.GDA`, which fails both of
`append_row`'s preconditions at once. Clones are batched so the array relocates once.

`append_row` adds a row, which is what the level-cap experiment needs. It is only
safe under two preconditions, both of which it **checks and refuses** otherwise:

  1. every row field is a fixed-size inline value (no list/reference/struct
     flags, no out-of-line strings), and
  2. the row array is the **last thing in the file**, so nothing after it needs
     its offsets corrected.

Both hold for the `Adv_<Character>.GDA` progression tables: all 16 columns are
`sint32`, and the row array ends exactly at EOF. Under those conditions appending
is just "bump the count, append the bytes" — no offset fixups anywhere. Tables
with string columns (e.g. `Levels.GDA`) fail precondition 1 and would need a full
re-serializer.

`set_string_cell` handles **string** columns, which are stored differently: the
row field holds a `uint32` offset (relative to `dataOffset`, REFERENCE-flagged)
pointing at a `uint32` character count — **including the trailing NUL** — followed
by CP-1252 text. Those live in a region after the row array (in `creatures.GDA`,
rows end at `0x7950` and strings run to EOF).

It follows the same append-and-repoint strategy proven in `tlk_write.py` and
`herf_write.py`: a replacement that fits the existing slot is written in place,
otherwise it is appended at the 4-byte-aligned end of the file and the row's
pointer updated. Other rows are never disturbed.

**Ordering note:** appending a string puts data after the row array, which breaks
`append_row`'s precondition that rows are last. Do any row appends *before* any
string appends on the same table. (In practice the two do not overlap: the tables
with string columns, like `creatures.GDA`, already have string data after the rows
and so cannot take `append_row` at all.)

**Limitations (deliberate):** row *removal* is unsupported.

Usage as a library:
    from gda_write import set_int_cell, set_string_cell, append_row
    new_bytes, note = set_int_cell(raw, row_index=29, column='xp', value=1234567)
    new_bytes, note = set_string_cell(raw, row_index=0, column='portrait',
                                      value='PRT_SP_SDW.ncgr')
    new_bytes, note = append_row(raw, [0, 31, 3000, ...])
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'recon'))

from gff4 import (GFF4, read_gda, T_NDSFIXED, T_SINT32, T_UINT32, T_SINT16, T_UINT16,  # noqa: E402
                  T_SINT8, T_UINT8, T_STRING, T_ASCIISTRING)

#: GFF4 `ndsfixed`: a signed 32-bit integer scaled by 2**12. The reader in
#: `gff4.py` divides by this; the writer multiplies back.
NDS_FIXED_ONE = 4096.0

GDA_ROWS_FIELD = 10003
ROW_FIELD_BASE = 10005

PACK = {T_SINT32: '<i', T_UINT32: '<I', T_SINT16: '<h', T_UINT16: '<H',
        T_SINT8: '<b', T_UINT8: '<B'}

#: NDS fixed-point: 32 bits, 12 fractional (1.19.12), the same convention `gff4._read_value`
#: decodes with. It is fixed-size and inline like the integers above, so a row carrying one
#: can still be appended - `creatures.GDA` column 3 is the only such column in the tables we
#: write, and without this the whole table is unappendable.
FIXED_ONE = 4096


def _resolve_column(g: GFF4, column, column_names):
    """Return the row-struct field label for a column given by name or index."""
    cols, _ = read_gda(g)
    if isinstance(column, int):
        idx = column
    else:
        idx = None
        for i, c in enumerate(cols):
            if column_names.get(c['hash']) == column:
                idx = i
                break
        if idx is None:
            known = [column_names.get(c['hash'], '#%d' % c['hash']) for c in cols]
            raise KeyError(f"no column named {column!r}; columns are {known}")
    if not (0 <= idx < len(cols)):
        raise KeyError(f"column index {idx} out of range (table has {len(cols)})")
    return ROW_FIELD_BASE + idx


def set_int_cell(raw: bytes, row_index: int, column, value, column_names=None):
    """Return (new_bytes, note). `column` is a recovered column name or an index.

    Handles any fixed-width numeric column: the integer types, `float32`, and GFF4's
    **`ndsfixed`** (type 18) - a signed 32-bit fixed-point number with 12 fractional
    bits, which is what the DS hardware wants and what `combo.GDA` uses for a move's
    per-tier status chances. A fractional value is only accepted into a fractional
    column: silently truncating 0.3 to 0 in an integer cell is exactly the sort of edit
    that looks applied and is not.
    """
    column_names = column_names or {}
    data = bytearray(raw)
    g = GFF4(bytes(data))
    _, rows = read_gda(g)
    if not (0 <= row_index < len(rows)):
        raise IndexError(f"row {row_index} out of range (table has {len(rows)} rows)")

    label = _resolve_column(g, column, column_names)

    rows_field = next(f for f in g.templates[0].fields if f.label == GDA_ROWS_FIELD)
    list_off, = struct.unpack_from('<I', data, g.data_offset + rows_field.offset)
    rows_start = g.data_offset + list_off + 4
    row_tmpl = g.templates[rows_field.type]
    field = next((f for f in row_tmpl.fields if f.label == label), None)
    if field is None:
        raise KeyError(f"row struct has no field {label}")
    if field.is_list or field.is_ref or field.is_struct or (
            field.type not in PACK and field.type != T_NDSFIXED):
        raise TypeError(f"column maps to field type {field.type} "
                        f"(flags 0x{field.flags:04X}), which is not a plain number")

    fixed = field.type == T_NDSFIXED
    fmt = '<i' if fixed else PACK[field.type]
    fractional = fixed or fmt in ('<f', '<d')
    if isinstance(value, float) and not fractional:
        raise TypeError(f"column {column} is an integer column; refusing to truncate "
                        f"{value!r}")

    pos = rows_start + row_index * row_tmpl.size + field.offset
    stored, = struct.unpack_from(fmt, data, pos)
    old = stored / NDS_FIXED_ONE if fixed else stored
    if fixed:
        struct.pack_into(fmt, data, pos, int(round(float(value) * NDS_FIXED_ONE)))
    else:
        struct.pack_into(fmt, data, pos, float(value) if fractional else int(value))

    # Confirm through the reader rather than trusting the arithmetic.
    _, rows2 = read_gda(GFF4(bytes(data)))
    got = rows2[row_index][label]
    # Neither float32 nor 1.19.12 fixed point holds every double, so compare at the
    # precision the cell actually stores rather than demanding exact equality.
    if not fractional:
        same = got == value
    elif fixed:
        same = int(round(got * NDS_FIXED_ONE)) == int(round(float(value) * NDS_FIXED_ONE))
    else:
        same = struct.pack(fmt, got) == struct.pack(fmt, float(value))
    if not same:
        raise RuntimeError(f"edit did not round-trip: reads back as {got!r}")
    if len(data) != len(raw):
        raise RuntimeError("in-place edit changed file length")

    return bytes(data), f"row {row_index} col {column}: {old} -> {value}"


STR_ENCODING = 'cp1252'


def set_string_cell(raw: bytes, row_index: int, column, value: str, column_names=None):
    """Set a string cell. Returns (new_bytes, note).

    Writes in place when the new text fits the existing slot, otherwise appends at
    the aligned end of file and repoints the row's pointer.
    """
    column_names = column_names or {}
    data = bytearray(raw)
    g = GFF4(bytes(data))
    _, rows = read_gda(g)
    if not (0 <= row_index < len(rows)):
        raise IndexError(f"row {row_index} out of range (table has {len(rows)} rows)")

    label = _resolve_column(g, column, column_names)
    rows_field = next(f for f in g.templates[0].fields if f.label == GDA_ROWS_FIELD)
    list_off, = struct.unpack_from('<I', data, g.data_offset + rows_field.offset)
    rows_start = g.data_offset + list_off + 4
    row_tmpl = g.templates[rows_field.type]
    field = next((f for f in row_tmpl.fields if f.label == label), None)
    if field is None:
        raise KeyError(f"row struct has no field {label}")
    if field.type not in (T_STRING, T_ASCIISTRING):
        raise TypeError(f"column maps to field type {field.type}, which is not a string; "
                        f"use set_int_cell for integer columns")
    if not field.is_ref:
        raise TypeError(f"string field {label} is not REFERENCE-flagged "
                        f"(flags 0x{field.flags:04X}); unhandled layout")

    ptr_at = rows_start + row_index * row_tmpl.size + field.offset
    old_ptr, = struct.unpack_from('<I', data, ptr_at)
    old_pos = g.data_offset + old_ptr
    old_count, = struct.unpack_from('<I', data, old_pos)
    old_text = bytes(data[old_pos + 4:old_pos + 4 + old_count]).split(b'\x00', 1)[0]

    # GDA string data is DEDUPLICATED: several rows (and columns) can point at the
    # same string. Writing in place would silently rewrite every one of them, so a
    # shared string is never edited in place -- it is appended and only this row
    # repointed. (Same trap as the TLK writer; found by a test that checked which
    # rows changed, not merely that the target row did.)
    sharers = 0
    for f2 in row_tmpl.fields:
        if f2.type not in (T_STRING, T_ASCIISTRING) or not f2.is_ref:
            continue
        for ri in range(len(rows)):
            at = rows_start + ri * row_tmpl.size + f2.offset
            if struct.unpack_from('<I', data, at)[0] == old_ptr:
                sharers += 1
                if sharers > 1:
                    break
        if sharers > 1:
            break

    encoded = value.encode(STR_ENCODING) + b'\x00'
    if sharers <= 1 and len(encoded) <= old_count:
        # Reuse the slot. Keep the allocation; shrink only the recorded count.
        data[old_pos + 4:old_pos + 4 + len(encoded)] = encoded
        struct.pack_into('<I', data, old_pos, len(encoded))
        how = f"in place ({old_count} byte slot, {len(encoded)} used)"
    else:
        while len(data) % 4:
            data.append(0)
        new_pos = len(data)
        data.extend(struct.pack('<I', len(encoded)))
        data.extend(encoded)
        while len(data) % 4:
            data.append(0)
        struct.pack_into('<I', data, ptr_at, new_pos - g.data_offset)
        why = 'shared string, repointed' if sharers > 1 else 'too long for slot'
        how = f"appended ({why}, {len(encoded)} bytes at 0x{new_pos:X})"

    # Confirm through the reader rather than trusting the arithmetic.
    _, rows2 = read_gda(GFF4(bytes(data)))
    got = rows2[row_index][label]
    if got != value:
        raise RuntimeError(f"edit did not round-trip: reads back as {got!r}")

    return bytes(data), (f"row {row_index} col {column}: "
                         f"{old_text.decode(STR_ENCODING)!r} -> {value!r} [{how}]")


def _row_array_bounds(g: GFF4, data):
    """(count_pos, rows_start, row_template, count) for the row list."""
    rows_field = next(f for f in g.templates[0].fields if f.label == GDA_ROWS_FIELD)
    list_off, = struct.unpack_from('<I', data, g.data_offset + rows_field.offset)
    count_pos = g.data_offset + list_off
    count, = struct.unpack_from('<I', data, count_pos)
    return count_pos, count_pos + 4, g.templates[rows_field.type], count


def append_row(raw: bytes, values):
    """Append a row whose cells are `values` (one int per column, in order).

    Refuses unless every row field is a fixed-size inline integer and the row
    array is the last thing in the file — see the module docstring.
    """
    data = bytearray(raw)
    g = GFF4(bytes(data))
    count_pos, rows_start, row_tmpl, count = _row_array_bounds(g, data)

    # Precondition 1: all row fields must be fixed-size inline values.
    for f in row_tmpl.fields:
        if (f.is_list or f.is_ref or f.is_struct
                or (f.type not in PACK and f.type != T_NDSFIXED)):
            raise TypeError(
                f"cannot append: row field {f.label} has type {f.type} / flags "
                f"0x{f.flags:04X}, which is not a fixed-size inline integer. "
                f"This table needs a full re-serializer.")

    # Precondition 2: nothing may follow the row array, or its offsets would shift.
    rows_end = rows_start + count * row_tmpl.size
    if rows_end != len(data):
        raise ValueError(
            f"cannot append: row array ends at 0x{rows_end:X} but the file is "
            f"0x{len(data):X} bytes — {len(data) - rows_end} bytes follow it and "
            f"their offsets would need correcting. This table needs a full "
            f"re-serializer.")

    if len(values) != len(row_tmpl.fields):
        raise ValueError(f"expected {len(row_tmpl.fields)} values, got {len(values)}")

    # Build the new row by placing each field at its own offset within the struct.
    row = bytearray(row_tmpl.size)
    by_label = {f.label: f for f in row_tmpl.fields}
    for i, value in enumerate(values):
        f = by_label.get(ROW_FIELD_BASE + i)
        if f is None:
            raise KeyError(f"row struct has no field {ROW_FIELD_BASE + i}")
        if f.type == T_NDSFIXED:
            struct.pack_into('<i', row, f.offset, int(round(float(value) * FIXED_ONE)))
        else:
            struct.pack_into(PACK[f.type], row, f.offset, int(value))

    data.extend(row)
    struct.pack_into('<I', data, count_pos, count + 1)

    # Confirm through the reader rather than trusting the arithmetic.
    cols2, rows2 = read_gda(GFF4(bytes(data)))
    if len(rows2) != count + 1:
        raise RuntimeError(f"append did not round-trip: {len(rows2)} rows, expected {count + 1}")
    got = [rows2[-1][ROW_FIELD_BASE + i] for i in range(len(values))]
    # Fixed-point cells come back as floats and lose anything below 1/4096, so they are
    # compared to that tolerance rather than for equality.
    for i, (g_, v) in enumerate(zip(got, values)):
        f = by_label[ROW_FIELD_BASE + i]
        ok = (abs(float(g_) - float(v)) <= 1.0 / FIXED_ONE
              if f.type == T_NDSFIXED else g_ == int(v))
        if not ok:
            raise RuntimeError(
                f"appended row cell {i} reads back as {g_!r}, expected {v!r}")

    return bytes(data), f"appended row {count} -> {count + 1} rows ({row_tmpl.size} bytes)"


def append_rows_clone(raw: bytes, specs):
    """Append a copy of row `source_index`, with `overrides` applied by field label.

    This is the counterpart to `append_row` for tables it refuses, and `creatures.GDA`
    is refused on both of its preconditions at once:

      * **Out-of-line strings.** Creature rows carry nine `asciistring` cells (portrait
        resources). `append_row` wants every cell to be a fixed-size inline integer.
        Cloning sidesteps this entirely: a string cell *is* four inline bytes — an offset
        relative to `dataOffset` — and a copy of an existing row can keep the source's
        offsets verbatim, because it points at the same portraits. No new string data is
        written and no re-serializer is needed. The cost is that a clone cannot be given
        a *new* string; overriding a string cell is refused rather than half-supported.
      * **The row array is not last in the file.** 4,443 bytes of string pool follow it
        in `creatures.GDA`, so growing it in place would shift every one of those strings
        and invalidate every offset pointing at them.

    So the whole array is rewritten at the **end** of the file, one row longer, and the
    root's list offset is repointed at the copy. Nothing that already exists moves, so
    every string offset stays valid; the old array becomes dead space. This is the same
    append-and-repoint strategy `gff4_write.append_clone` uses for widget lists and the
    TLK/GDA string writers use for strings.

    `overrides` maps field label -> value for integer and fixed-point cells. Returns
    `(new_bytes, note)`; the new row's index is the old count.
    """
    specs = [(int(i), dict(o or {})) for i, o in specs]
    data = bytearray(raw)
    g = GFF4(bytes(data))

    rows_field = next(f for f in g.templates[0].fields if f.label == GDA_ROWS_FIELD)
    list_rel, = struct.unpack_from('<I', data, g.data_offset + rows_field.offset)
    count_pos = g.data_offset + list_rel
    count, = struct.unpack_from('<I', data, count_pos)
    tmpl = g.templates[rows_field.type]

    by_label = {f.label: f for f in tmpl.fields}
    built = []
    for source_index, overrides in specs:
        if not 0 <= source_index < count:
            raise IndexError(f"source row {source_index} out of range ({count} rows)")
        for label in overrides:
            f = by_label.get(label)
            if f is None:
                raise KeyError(f"row struct has no field {label}")
            if f.type in (T_STRING, T_ASCIISTRING):
                raise TypeError(
                    f"field {label} is a string; a clone reuses the source's string "
                    f"offsets and cannot introduce new text. Clone from a row that "
                    f"already has the string you want.")
            if f.type not in PACK and f.type != T_NDSFIXED:
                raise TypeError(f"field {label} has type {f.type}, which cannot be written")
        src = count_pos + 4 + source_index * tmpl.size
        row = bytearray(data[src:src + tmpl.size])
        for label, value in overrides.items():
            f = by_label[label]
            if f.type == T_NDSFIXED:
                struct.pack_into('<i', row, f.offset, int(round(float(value) * FIXED_ONE)))
            else:
                struct.pack_into(PACK[f.type], row, f.offset, int(value))
        built.append(bytes(row))

    old_array = bytes(data[count_pos + 4: count_pos + 4 + count * tmpl.size])

    # One relocation for the whole batch. Relocating per row would re-copy the array
    # every time: creatures.GDA is ~30 KB, so fifty clones would add 1.5 MB and push the
    # ROM past its declared cartridge size for no reason.
    while len(data) % 4:                      # keep the new array 4-byte aligned
        data.append(0)
    new_count_pos = len(data)
    data += struct.pack('<I', count + len(built)) + old_array + b''.join(built)
    struct.pack_into('<I', data, g.data_offset + rows_field.offset,
                     new_count_pos - g.data_offset)

    # Confirm through the reader rather than trusting the arithmetic.
    want = count + len(built)
    cols2, rows2 = read_gda(GFF4(bytes(data)))
    if len(rows2) != want:
        raise RuntimeError(f"clone did not round-trip: {len(rows2)} rows, expected {want}")
    original = read_gda(GFF4(raw))[1]
    for n, (source_index, overrides) in enumerate(specs):
        before, after = original[source_index], rows2[count + n]
        for label, f in by_label.items():
            if label in overrides or f.type in (T_STRING, T_ASCIISTRING):
                continue
            if before.get(label) != after.get(label):
                raise RuntimeError(
                    f"clone of row {source_index} differs from its source at field "
                    f"{label}: {before.get(label)!r} -> {after.get(label)!r}")
        for label, value in overrides.items():
            got = after.get(label)
            ok = (abs(float(got) - float(value)) <= 1.0 / FIXED_ONE
                  if by_label[label].type == T_NDSFIXED else got == int(value))
            if not ok:
                raise RuntimeError(f"override {label}={value!r} reads back as {got!r}")

    return bytes(data), (f"cloned {len(built)} row(s) -> rows {count}..{want - 1} "
                         f"(array relocated, {len(data) - len(raw)} bytes added)")


def append_row_clone(raw: bytes, source_index: int, overrides=None):
    """Single-row convenience wrapper around `append_rows_clone`."""
    return append_rows_clone(raw, [(source_index, overrides)])
