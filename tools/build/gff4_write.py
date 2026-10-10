"""
GFF4 writer — append elements to a widget list by cloning an existing one.

The other writers only append rows to a GDA, which is the easy case: a GDA's rows are
one flat array of fixed-size structs. This handles what `.gui` files actually use.

**Why cloning rather than constructing.** A widget struct has a dozen-plus fields whose
meaning is only partly decoded. Building one from scratch means getting every field
right, including the ones nobody has identified. Copying a known-good sibling and
overriding only what must differ — name, position — is correct by construction for
everything left untouched.

**A `.gui` child list is a GENERIC list, not an inline struct array.** The uint32 at
`base + field.offset` points, relative to `dataOffset`, at a uint32 count followed by
that many **8-byte (typeAndFlags, offset) entries**, each offset locating a struct
instance elsewhere in the file. Walking it as an inline array silently finds nothing
at all, which is exactly what happened on the first attempt here.

**How an append works.** Growing anything in place is impossible because other data
follows immediately, so both the cloned struct and the one-longer list are written at
the **end** of the file and the pointers repointed. Nothing existing moves, so any
other structure referencing the old bytes still resolves; the originals become dead
space. Same append-and-repoint strategy the TLK and GDA string writers use.

Strings are out-of-line too: a uint32 offset relative to `dataOffset` pointing at a
uint32 *character* count then the characters, UTF-16LE for everything except TLK. A
new string is appended rather than edited, because GFF4 deduplicates them and editing
one in place can silently rewrite another's text.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'recon'))

from gff4 import (GFF4, FLAG_LIST, FLAG_STRUCT, T_STRING, T_ASCIISTRING,  # noqa: E402
                  T_GENERIC, T_UINT8, T_SINT8, T_UINT16, T_SINT16,
                  T_UINT32, T_SINT32)

#: pack format per integer field type, so an override is written at the field's own
#: width. Widget x/y/w/h are sint16; writing four bytes would clobber the next field.
INT_FMT = {T_UINT8: '<B', T_SINT8: '<b', T_UINT16: '<H', T_SINT16: '<h',
           T_UINT32: '<I', T_SINT32: '<i'}

NUL = chr(0)

W_NAME, W_CHILDREN = 62000, 62002


class Gff4Writer:
    def __init__(self, data: bytes):
        self.data = bytearray(data)
        self.g = GFF4(bytes(data))
        self.data_offset = self.g.data_offset

    # --- locating ---------------------------------------------------------

    def _generic_entries(self, base, field):
        """[(entry_offset, template_index, struct_base)] for a generic list field."""
        rel, = struct.unpack_from('<I', self.data, base + field.offset)
        if rel == 0xFFFFFFFF:
            return []
        lp = self.data_offset + rel
        count, = struct.unpack_from('<I', self.data, lp)
        if count > 8192:
            return []
        out = []
        for i in range(count):
            e = lp + 4 + i * 8
            taf, off = struct.unpack_from('<II', self.data, e)
            if off == 0xFFFFFFFF:
                continue
            ftype, flags = taf & 0xFFFF, (taf >> 16) & 0xFFFF
            if flags & FLAG_STRUCT:
                out.append((e, ftype, self.data_offset + off))
        return out

    def _list_field(self, ti, list_label):
        return next((f for f in self.g.templates[ti].fields
                     if f.label == list_label and f.flags & FLAG_LIST), None)

    def walk(self, visit, ti=0, base=None, depth=0, seen=None):
        """Call visit(template_index, struct_base) for every struct in the tree."""
        if base is None:
            base = self.data_offset
        seen = seen if seen is not None else set()
        if depth > 24 or (ti, base) in seen:
            return
        seen.add((ti, base))
        visit(ti, base)
        for f in self.g.templates[ti].fields:
            if (f.flags & FLAG_LIST) and f.type == T_GENERIC:
                for _, sti, sbase in self._generic_entries(base, f):
                    self.walk(visit, sti, sbase, depth + 1, seen)
            elif (f.flags & FLAG_STRUCT) and not (f.flags & FLAG_LIST):
                rel, = struct.unpack_from('<I', self.data, base + f.offset)
                if rel != 0xFFFFFFFF:
                    self.walk(visit, f.type, self.data_offset + rel, depth + 1, seen)

    def find(self, pred):
        """[(template_index, base)] for every struct where pred(ti, base) is true."""
        hits = []

        def visit(ti, base):
            if pred(ti, base):
                hits.append((ti, base))
        self.walk(visit)
        return hits

    def find_named(self, name):
        return self.find(lambda ti, b: self.read_string(ti, b, W_NAME) == name)

    def children(self, ti, base, list_label=W_CHILDREN):
        """[(index, name)] of a widget's children."""
        field = self._list_field(ti, list_label)
        if field is None:
            return []
        return [(i, self.read_string(sti, sbase, W_NAME))
                for i, (_, sti, sbase) in enumerate(self._generic_entries(base, field))]

    def read_string(self, ti, base, label):
        """Decode a string field of one struct instance, or None."""
        for f in self.g.templates[ti].fields:
            if f.label != label or f.type not in (T_STRING, T_ASCIISTRING):
                continue
            rel, = struct.unpack_from('<I', self.data, base + f.offset)
            if rel == 0xFFFFFFFF:
                return None
            p = self.data_offset + rel
            count, = struct.unpack_from('<I', self.data, p)
            if count > 4096:
                return None
            if f.type == T_ASCIISTRING:
                blob = bytes(self.data[p + 4:p + 4 + count])
                return blob.split(bytes(1))[0].decode('cp1252')
            raw = bytes(self.data[p + 4:p + 4 + count * 2])
            return raw.decode('utf-16-le', 'replace').split(NUL)[0]
        return None

    def read_int(self, ti, base, label):
        for f in self.g.templates[ti].fields:
            if f.label == label and f.type in INT_FMT:
                return struct.unpack_from(INT_FMT[f.type], self.data, base + f.offset)[0]
        return None

    # --- appending --------------------------------------------------------

    def _align(self):
        while len(self.data) % 4:
            self.data.append(0)

    def _append_string(self, text, ascii_mode=False):
        self._align()
        off = len(self.data) - self.data_offset
        if ascii_mode:
            enc = text.encode('cp1252') + bytes(1)
            self.data += struct.pack('<I', len(enc)) + enc
        else:
            self.data += struct.pack('<I', len(text) + 1)
            self.data += (text + NUL).encode('utf-16-le')
        self._align()
        return off

    def append_clone(self, owner_ti, owner_base, source_index, overrides,
                     list_label=W_CHILDREN):
        """Append a copy of child `source_index` with `overrides` applied.

        Returns the new child count.
        """
        field = self._list_field(owner_ti, list_label)
        if field is None:
            raise ValueError('template %d has no list field %s' % (owner_ti, list_label))
        entries = self._generic_entries(owner_base, field)
        if not (0 <= source_index < len(entries)):
            raise ValueError('source index %d out of range (%d children)'
                             % (source_index, len(entries)))
        src_entry, src_ti, src_base = entries[source_index]
        src_taf, _ = struct.unpack_from('<II', self.data, src_entry)
        size = self.g.templates[src_ti].size

        self._align()
        clone_at = len(self.data)
        self.data += self.data[src_base:src_base + size]
        self._align()

        for label, value in overrides.items():
            f = next((x for x in self.g.templates[src_ti].fields if x.label == label), None)
            if f is None:
                raise ValueError('template %d has no field %s' % (src_ti, label))
            at = clone_at + f.offset
            if f.type in (T_STRING, T_ASCIISTRING):
                struct.pack_into('<I', self.data, at,
                                 self._append_string(str(value), f.type == T_ASCIISTRING))
            elif isinstance(value, int):
                fmt = INT_FMT.get(f.type)
                if fmt is None:
                    raise ValueError('field %s is not an integer type (%d)' % (label, f.type))
                struct.pack_into(fmt, self.data, at, value)
            else:
                raise ValueError('unsupported override %s=%r' % (label, value))

        rel, = struct.unpack_from('<I', self.data, owner_base + field.offset)
        lp = self.data_offset + rel
        count, = struct.unpack_from('<I', self.data, lp)
        old = bytes(self.data[lp + 4: lp + 4 + count * 8])
        self._align()
        new_rel = len(self.data) - self.data_offset
        self.data += struct.pack('<I', count + 1) + old
        self.data += struct.pack('<II', src_taf, clone_at - self.data_offset)
        self._align()
        struct.pack_into('<I', self.data, owner_base + field.offset, new_rel)
        return count + 1

    def serialize(self) -> bytes:
        return bytes(self.data)
