"""Resolve the game's plot flags to their authored names.

Sonic Chronicles ships no scripts, but it does ship a **flag registry**, and the flags
carry the names the designers gave them: `MARAUDER_SCOUT_TRIGGER_APPEAR`,
`PROJECTOR_QUEST_GIVEN`, `FROGGY_QUEST_ACCEPTED`, `CH10_BEGIN`. Anything in an area file
that references a flag can therefore be read in plain English, which is how the `kind == 4`
objects in area list 40002 were finally identified (see the 2026-10-10 log entry).

Three files make the chain:

* **`plotflags.GDA`** — 657 rows of `(global id, plot index, ?, flag index)`. This is the
  numbering that area files use.
* **`plots.GDA`** — 102 rows mapping a plot index to a `.plo` filename. Several indices
  share one file.
* **the `.plo` itself** — GFF4 of type `PLTS`. Its root holds one list of plot *headers*
  (name, GUID, category, a TLK description), and each header holds a nested list of flag
  entries whose **field 13002 is the flag's name**. The nesting is why a plain read of
  the root list shows a single entry and no flags.

649 of the 657 flags resolve to a name; the remainder point past the end of their plot's
list and are presumably cut content.
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from gff4 import GFF4, FLAG_LIST, read_gda  # noqa: E402

PLOTFLAGS, PLOTS = 'plotflags.GDA', 'plots.GDA'
#: within a .plo flag entry: the authored name
F_FLAG_NAME = 13002
#: within a .plo flag entry: a TLK strref for the journal line this flag writes
F_FLAG_TEXT = 13004


def _struct_list(g, raw, ptr_at, tmpl):
    """Read a GFF4 inline struct array whose relative offset sits at `ptr_at`."""
    rel, = struct.unpack_from('<I', raw, ptr_at)
    if rel == 0xFFFFFFFF:
        return []
    count_pos = g.data_offset + rel
    count, = struct.unpack_from('<I', raw, count_pos)
    out = []
    for i in range(count):
        base = count_pos + 4 + i * tmpl.size
        entry = {'__base__': base}
        for f in tmpl.fields:
            if f.flags & FLAG_LIST:
                continue
            try:
                entry[f.label] = g._read_value(f.type, base + f.offset)
            except Exception:
                entry[f.label] = None
        out.append(entry)
    return out


def plot_flags(raw: bytes):
    """[{field label: value}] for every flag in one `.plo`, in index order."""
    g = GFF4(raw)
    root = g.templates[0].fields[0]
    header_t = g.templates[root.type]
    nested = next(f for f in header_t.fields if f.flags & FLAG_LIST)
    flag_t = g.templates[nested.type]
    out = []
    for header in _struct_list(g, raw, g.data_offset + root.offset, header_t):
        out.extend(_struct_list(g, raw, header['__base__'] + nested.offset, flag_t))
    return out


def flag_names(read_resource):
    """{global flag id: (plo filename, flag name or None)}.

    `read_resource(name)` returns a resource's bytes — pass `build.herf.read` composed
    with `build.resource`, or anything else that can fetch by name.
    """
    _, frows = read_gda(GFF4(read_resource(PLOTFLAGS)))
    _, prows = read_gda(GFF4(read_resource(PLOTS)))
    FK, PK = sorted(frows[0].keys()), sorted(prows[0].keys())
    plo_of = {r[PK[0]]: r[PK[1]] for r in prows}

    cache, out = {}, {}
    for r in frows:
        gid, plot, _, index = (r[FK[i]] for i in range(4))
        name = plo_of.get(plot)
        if not name:
            continue
        if name not in cache:
            try:
                cache[name] = plot_flags(read_resource(name))
            except Exception:
                cache[name] = []
        entries = cache[name]
        flag = entries[index].get(F_FLAG_NAME) if 0 <= index < len(entries) else None
        out[gid] = (name, flag)
    return out
