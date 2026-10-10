"""
In-place integer-cell editor for ARE (area) files.

An area file is GFF4 with type `ARE`. Its root struct holds several LIST|STRUCT fields,
each pointing at a `uint32` count followed by that many fixed-size structs laid out
inline, exactly like a GDA's row array. Two of those lists are what modding wants:

  * **label 40002** — placed objects, as a (kind, id) pair at fields 40008/40009.
    `kind == 4` is an **item placement**: 39 across the 79 areas, every id valid in
    `Items.GDA`. This is where a chest's contents actually come from.
  * **label 40003** — squad placements, with the **squad id at field 40005** plus
    position, facing and a patrol waypoint list. This is where an encounter *is*.

Editing either is far cheaper than the GDA row cloning in `gda_write`, because nothing
changes size: the value is a fixed-width integer at a known offset inside an inline
array, so it is overwritten in place with no offsets to fix and no array to relocate.
That is the same reason `set_int_cell` is cheap for GDA tables.

What this module deliberately does **not** do is add or remove objects. Growing a list
would mean relocating it and repointing the root, and unlike a GDA row array there may be
several lists in one file whose relative order the engine could care about. Randomizing
what is already placed needs no growth, so that stays unbuilt until something needs it.
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'recon'))

from gff4 import GFF4, FLAG_LIST, FLAG_STRUCT, UNPACK  # noqa: E402

#: root list labels worth naming
L_OBJECTS, L_SQUADS = 40002, 40003
#: within L_OBJECTS: the object kind and its payload id
F_KIND, F_PAYLOAD = 40008, 40009
#: within L_SQUADS: which squad spawns here
F_SQUAD = 40005
#: within L_SQUADS: a script tag. Non-zero means a plot references this spawn point by
#: name — 13 of the 54 in the opening area alone, including the tutorial fight. Moving
#: the squad out of a tagged point breaks the script that drives it: the battle starts
#: with no enemy in it and the player stands there waiting. Leave tagged points alone.
F_TAG = 40006
#: object kinds seen across the 79 area files, by frequency
KIND_ITEM = 4


def _lists(g):
    """{label: (field, template)} for every LIST|STRUCT field on the root struct."""
    out = {}
    for f in g.templates[0].fields:
        if (f.flags & FLAG_LIST) and (f.flags & FLAG_STRUCT):
            out[f.label] = (f, g.templates[f.type])
    return out


def _bounds(raw, g, label):
    """(count_pos, first_struct_pos, count, template) for one root list."""
    entry = _lists(g).get(label)
    if entry is None:
        raise KeyError('this area has no list %d' % label)
    field, tmpl = entry
    rel, = struct.unpack_from('<I', raw, g.data_offset + field.offset)
    if rel == 0xFFFFFFFF:
        return None, None, 0, tmpl
    count_pos = g.data_offset + rel
    count, = struct.unpack_from('<I', raw, count_pos)
    if count > 8192:
        raise ValueError('implausible count %d in list %d' % (count, label))
    return count_pos, count_pos + 4, count, tmpl


def read_list(raw: bytes, label: int):
    """[{field label: value}] for each struct in a root list, integers only."""
    g = GFF4(raw)
    _, start, count, tmpl = _bounds(raw, g, label)
    offs = [(f.label, f.offset, f.type) for f in tmpl.fields if f.type in UNPACK]
    out = []
    for i in range(count):
        base = start + i * tmpl.size
        out.append({lb: struct.unpack_from(UNPACK[tp], raw, base + off)[0]
                    for lb, off, tp in offs})
    return out


def item_placements(raw: bytes):
    """[(index, item id)] for every `kind == 4` object — i.e. the loot in this area."""
    return [(i, o[F_PAYLOAD]) for i, o in enumerate(read_list(raw, L_OBJECTS))
            if o.get(F_KIND) == KIND_ITEM]


def squad_placements(raw: bytes, include_tagged=True):
    """[(index, squad id)] for every spawn point in this area.

    `include_tagged=False` drops the script-referenced ones — see `F_TAG`.
    """
    return [(i, o[F_SQUAD]) for i, o in enumerate(read_list(raw, L_SQUADS))
            if include_tagged or not o.get(F_TAG)]


def set_field(raw: bytes, label: int, index: int, field_label: int, value: int):
    """Overwrite one integer field of one struct in a root list.

    Returns `(new_bytes, note)`. Nothing changes size, so no offsets move.
    """
    data = bytearray(raw)
    g = GFF4(raw)
    _, start, count, tmpl = _bounds(raw, g, label)
    if not 0 <= index < count:
        raise IndexError('list %d has %d entries; no index %d' % (label, count, index))
    field = next((f for f in tmpl.fields if f.label == field_label), None)
    if field is None:
        raise KeyError('list %d structs have no field %d' % (label, field_label))
    if field.type not in UNPACK:
        raise TypeError('field %d is type %d, not a fixed-size integer'
                        % (field_label, field.type))

    at = start + index * tmpl.size + field.offset
    fmt = UNPACK[field.type]
    old, = struct.unpack_from(fmt, data, at)
    if old == int(value):
        raise ValueError('list %d[%d].%d is already %r'
                         % (label, index, field_label, old))
    struct.pack_into(fmt, data, at, int(value))

    # Confirm through the reader rather than trusting the arithmetic.
    got = read_list(bytes(data), label)[index][field_label]
    if got != int(value):
        raise RuntimeError('write did not round-trip: reads back as %r' % (got,))
    return bytes(data), ('list %d[%d] field %d: %r -> %r'
                         % (label, index, field_label, old, value))
